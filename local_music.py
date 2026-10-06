"""Musique stockée sur le PC : lecture directe par Windows (aucun module à installer, aucun navigateur).

Mets tes fichiers dans le dossier « musique » de Jarvis (mp3, wav, m4a, wma). Jarvis cherche aussi dans
ton dossier Musique de Windows, et dans JARVIS_DOSSIER_MUSIQUE si tu le définis dans .env.
  - fin de l'intro : joue JARVIS_MUSIQUE_INTRO (un nom de fichier) ou, à défaut, le premier morceau du dossier
  - à la voix : « mets ma musique », « mets Ninho », « pause », « reprends », « suivante », « volume 40 »
  - quand Jarvis parle, la musique baisse puis remonte
"""
from __future__ import annotations

import ctypes
import difflib
import logging
import os
import queue
import random
import re
import threading
import time
import unicodedata
from pathlib import Path

log = logging.getLogger("jarvis")
BASE = Path(__file__).resolve().parent
EXTS = {".mp3", ".wav", ".m4a", ".wma", ".aac"}
ALIAS = "jarvis_musique"


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def folders() -> list[Path]:
    out = [BASE / "musique"]
    extra = (os.environ.get("JARVIS_DOSSIER_MUSIQUE") or "").strip()
    if extra:
        out.insert(0, Path(os.path.expandvars(os.path.expanduser(extra))))
    out.append(Path.home() / "Music")
    return [f for f in out if f.is_dir()]


def tracks() -> list[Path]:
    seen, out = set(), []
    for f in folders():
        for p in sorted(f.rglob("*")):
            if p.suffix.lower() in EXTS and p.is_file() and p not in seen:
                seen.add(p)
                out.append(p)
    return out


def find(query: str) -> Path | None:
    """Morceau dont le nom ressemble le plus à la recherche (« ninho », « la musique de l'intro »...)."""
    q = _norm(query)
    best, score = None, 0.0
    for p in tracks():
        n = _norm(p.stem)
        if not n:
            continue
        if q and (q in n or all(w in n for w in q.split())):
            s = 0.95
        else:
            s = difflib.SequenceMatcher(None, q, n).ratio()
        if s > score:
            best, score = p, s
    return best if score >= 0.6 else None


class Player:
    """Lecteur basé sur Windows (MCI). Toutes les commandes passent par un seul fil (exigence de Windows)."""

    def __init__(self) -> None:
        self.q: queue.Queue = queue.Queue()
        self.current: Path | None = None
        self.playlist: list[Path] = []
        self.volume = 80                     # 0-100
        self.ducked = False
        self.state = "stop"                  # stop | ready (chargé) | play | pause
        threading.Thread(target=self._run, daemon=True).start()

    # --- fil de lecture
    def _mci(self, cmd: str) -> str:
        buf = ctypes.create_unicode_buffer(256)
        err = ctypes.windll.winmm.mciSendStringW(cmd, buf, 255, 0)
        if err:
            ebuf = ctypes.create_unicode_buffer(256)
            ctypes.windll.winmm.mciGetErrorStringW(err, ebuf, 255)
            raise OSError(ebuf.value or f"erreur MCI {err}")
        return buf.value

    def _run(self) -> None:
        while True:
            try:
                fn, args, done = self.q.get(timeout=1.0)
            except queue.Empty:
                self._auto_next()
                continue
            try:
                done["out"] = fn(*args)
            except Exception as e:  # noqa: BLE001
                done["out"] = f"ÉCHEC : {e}"
                log.warning("Musique : %s", e)
            done["ev"].set()

    def _call(self, fn, *args, timeout: float = 8.0):
        done = {"ev": threading.Event(), "out": None}
        self.q.put((fn, args, done))
        done["ev"].wait(timeout)
        return done["out"]

    def _auto_next(self) -> None:
        """Morceau terminé -> le suivant de la liste."""
        if self.state != "play" or self.current is None:
            return
        try:
            if self._mci(f"status {ALIAS} mode") == "stopped":
                self._next()
        except OSError:
            pass

    # --- actions (exécutées dans le fil)
    def _open(self, path: Path) -> None:
        try:
            self._mci(f"close {ALIAS}")
        except OSError:
            pass
        self._mci(f'open "{path}" type mpegvideo alias {ALIAS}')
        self._apply_volume()

    def _open_play(self, path: Path) -> str:
        if not (self.state == "ready" and self.current == path):
            self._open(path)
        self._mci(f"play {ALIAS}")
        self.current, self.state = path, "play"
        log.info("Musique : %s", path.name)
        return f"Lecture : {path.stem}"

    def _apply_volume(self) -> None:
        v = self.volume * (0.3 if self.ducked else 1.0)
        try:
            self._mci(f"setaudio {ALIAS} volume to {int(v * 10)}")
        except OSError:
            pass

    def _next(self) -> str:
        if not self.playlist:
            self.playlist = tracks()
        if not self.playlist:
            self.state = "stop"
            return "ÉCHEC : aucune musique sur le PC"
        i = (self.playlist.index(self.current) + 1) % len(self.playlist) if self.current in self.playlist else 0
        return self._open_play(self.playlist[i])

    # --- interface (appelable de partout)
    def preload(self, path: Path) -> bool:
        """Ouvre le morceau à l'avance (sans le jouer) : play() démarrera ensuite instantanément."""
        def f():
            self._open(path)
            self.current, self.state = path, "ready"
            return True
        ok = self._call(f) is True
        if ok:
            self.playlist = tracks()
        return ok

    def play(self, path: Path | None = None, shuffle: bool = False) -> str:
        if path is not None and self.state == "ready" and self.current == path and not shuffle:
            return self._call(self._open_play, path)              # déjà chargé : départ immédiat
        self.playlist = tracks()
        if shuffle:
            random.shuffle(self.playlist)
        if path is None:
            if not self.playlist:
                return "ÉCHEC : aucune musique sur le PC (mets des mp3 dans le dossier musique de Jarvis)"
            path = self.playlist[0]
        return self._call(self._open_play, path)

    def pause(self) -> str:
        def f():
            self._mci(f"pause {ALIAS}")
            self.state = "pause"
            return "Musique en pause"
        return self._call(f) if self.state == "play" else "Pas de musique en cours"

    def resume(self) -> str:
        def f():
            self._mci(f"resume {ALIAS}")
            self.state = "play"
            return "Musique relancée"
        return self._call(f) if self.state == "pause" else "Pas de musique en pause"

    def stop(self) -> str:
        def f():
            try:
                self._mci(f"close {ALIAS}")
            except OSError:
                pass
            self.state, self.current = "stop", None
            return "Musique arrêtée"
        return self._call(f)

    def next(self) -> str:
        return self._call(self._next)

    def set_volume(self, v: int) -> str:
        self.volume = max(0, min(100, int(v)))
        self._call(self._apply_volume)
        return f"Volume de la musique : {self.volume} %"

    def duck(self, on: bool) -> None:
        """Baisse la musique pendant que Jarvis parle."""
        if self.state == "play" and self.ducked != on:
            self.ducked = on
            self._call(self._apply_volume, timeout=1.0)

    @property
    def active(self) -> bool:
        return self.state in ("play", "pause")


_player: Player | None = None


def player() -> Player:
    global _player
    if _player is None:
        _player = Player()
    return _player


def intro_track() -> Path | None:
    """Morceau de fin d'intro : JARVIS_MUSIQUE_INTRO (nom de fichier) ou le premier du dossier musique de Jarvis."""
    name = (os.environ.get("JARVIS_MUSIQUE_INTRO") or "").strip()
    if name:
        p = Path(name)
        if p.is_file():
            return p
        return find(Path(name).stem)
    own = BASE / "musique"
    if own.is_dir():
        files = [p for p in sorted(own.rglob("*")) if p.suffix.lower() in EXTS]
        if files:
            return files[0]
    return None
