"""Mode jeu automatique : quand un jeu tourne, Jarvis se fait tout petit pour ne jamais te faire ramer.

Ce qu'il fait dès qu'il voit ton jeu (CS2, Valorant, Fortnite...) :
  - vide la mémoire de la carte graphique : IA locale (Ollama) et Whisper déchargés
    (Whisper passe sur un petit modèle processeur le temps de la partie) ;
  - passe Jarvis en priorité « basse » : Windows donne toujours la priorité à ton jeu ;
  - la sphère s'affiche moins souvent (elle est de toute façon derrière le jeu) ;
  - le plan de travail mesure la carte graphique moins souvent.
Tout revient à la normale quand tu quittes le jeu. Jarvis t'écoute toujours pendant la partie.

Réglages dans .env :
  JARVIS_MODE_JEU=non                  désactive le mode jeu
  JARVIS_JEUX=monjeu.exe,autre.exe     jeux en plus de la liste ci-dessous
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
import time
import urllib.request

log = logging.getLogger("jarvis")

GAMES = {"cs2.exe", "csgo.exe", "valorant-win64-shipping.exe", "valorant.exe", "fortniteclient-win64-shipping.exe",
         "r5apex.exe", "r5apex_dx12.exe", "leagueoflegends.exe", "league of legends.exe", "rocketleague.exe",
         "overwatch.exe", "cod.exe", "gta5.exe", "gta5_enhanced.exe", "eldenring.exe", "minecraft.exe",
         "javaw.exe", "rainbowsix.exe", "pubg.exe", "tslgame.exe", "dota2.exe", "deadlock.exe",
         "marvel-win64-shipping.exe", "fc25.exe", "fc26.exe", "eafc25.exe", "eafc26.exe", "bf6.exe", "cs2_launcher.exe"}

ACTIF = threading.Event()                 # un jeu tourne en ce moment
NOM: dict[str, str | None] = {"jeu": None}
_started = threading.Event()
_enter: list = []
_leave: list = []


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def games() -> set[str]:
    extra = {g.strip().lower() for g in _env("JARVIS_JEUX").split(",") if g.strip()}
    return GAMES | {g if g.endswith(".exe") else g + ".exe" for g in extra}


def detect() -> str | None:
    """Nom du jeu lancé, sinon None (lecture légère de la liste des programmes, sans fenêtre)."""
    wanted = games()
    try:
        import psutil

        for p in psutil.process_iter(["name"]):
            n = (p.info.get("name") or "").lower()
            if n in wanted:
                return n
        return None
    except ImportError:
        pass
    try:
        out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, timeout=5,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
        for line in out.decode("utf-8", "replace").lower().splitlines():
            n = line.split('","')[0].strip('"')
            if n in wanted:
                return n
    except Exception:  # noqa: BLE001
        pass
    return None


def current() -> str | None:
    """Le jeu en cours si la surveillance tourne (aucun coût), sinon une détection directe."""
    if _started.is_set():
        return NOM["jeu"] if ACTIF.is_set() else None
    return detect()


def free_ollama() -> None:
    """Décharge tous les modèles de l'IA locale de la carte graphique (s'il y en a)."""
    host = (_env("OLLAMA_HOST") or "http://127.0.0.1:11434").rstrip("/")
    if not host.startswith("http"):
        host = "http://" + host
    try:
        with urllib.request.urlopen(host + "/api/ps", timeout=2) as r:
            models = [m.get("name") or m.get("model") for m in json.loads(r.read().decode()).get("models", [])]
    except Exception:  # noqa: BLE001
        return                                            # Ollama éteint : rien à libérer
    for m in filter(None, models):
        try:
            req = urllib.request.Request(host + "/api/generate", method="POST",
                                         data=json.dumps({"model": m, "keep_alive": 0}).encode(),
                                         headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=10).read()
            log.info("Mode jeu : IA locale %s retirée de la carte graphique.", m)
        except Exception:  # noqa: BLE001
            pass


def _priority(low: bool) -> None:
    if os.name != "nt":
        return
    try:
        import psutil

        psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS if low else psutil.NORMAL_PRIORITY_CLASS)
    except Exception:  # noqa: BLE001
        try:
            import ctypes

            k = ctypes.windll.kernel32
            k.SetPriorityClass(k.GetCurrentProcess(), 0x4000 if low else 0x20)   # BELOW_NORMAL / NORMAL
        except Exception:  # noqa: BLE001
            pass


def _run_hooks(hooks: list) -> None:
    for fn in hooks:
        try:
            fn()
        except Exception:  # noqa: BLE001
            log.debug("Mode jeu : action impossible", exc_info=True)


def _loop() -> None:
    while True:
        g = detect()
        if g and not ACTIF.is_set():
            NOM["jeu"] = g
            ACTIF.set()
            log.info("Mode jeu : %s détecté. Je libère la carte graphique et je passe en priorité basse.", g)
            _priority(True)
            free_ollama()
            _run_hooks(_enter)
        elif not g and ACTIF.is_set():
            ACTIF.clear()
            log.info("Mode jeu terminé (%s fermé) : retour à la normale.", NOM["jeu"])
            NOM["jeu"] = None
            _priority(False)
            _run_hooks(_leave)
        elif g and ACTIF.is_set():
            free_ollama()                                 # au cas où l'IA locale aurait servi pendant la partie
        time.sleep(10)


def start(on_enter=None, on_leave=None) -> None:
    """Lance la surveillance (une seule fois). on_enter / on_leave : actions en plus, à l'entrée / la sortie."""
    if on_enter:
        _enter.append(on_enter)
    if on_leave:
        _leave.append(on_leave)
    if _started.is_set() or _env("JARVIS_MODE_JEU").lower() in ("non", "0", "off", "false"):
        return
    _started.set()
    threading.Thread(target=_loop, name="mode-jeu", daemon=True).start()
