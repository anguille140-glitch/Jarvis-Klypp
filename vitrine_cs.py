"""Vitrine CS2 : fond d'écran vivant avec des skins de rêve, à la voix.

« Jarvis, lance mon fond d'écran » : intro en ouverture de caisse, puis les skins (couteaux, gants, AWP, AK...)
défilent au centre de l'écran. On peut les faire tourner à la souris, zoomer, les inspecter, ouvrir des caisses,
mettre des favoris. Jarvis la pilote aussi à la voix (« skin suivant », « montre-moi la Dragon Lore »,
« ouvre une caisse », « ferme le fond d'écran »).

Les images viennent des serveurs officiels de Steam ; elles sont téléchargées une fois puis gardées dans
.cache/skins (aucune image n'est stockée dans le code). Liste des skins : skins_cs.json.
Son des bruitages : JARVIS_PLAN_SONS (le même réglage que le plan de travail).
"""
from __future__ import annotations

import ctypes
import http.server
import json
import logging
import os
import re
import secrets
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from ctypes import wintypes
from pathlib import Path

log = logging.getLogger("jarvis")
BASE = Path(__file__).resolve().parent
PAGE = BASE / "vitrine_cs.html"
DATA = BASE / "skins_cs.json"
CACHE = BASE / ".cache"
IMAGES = CACHE / "skins"
TITLE = "Vitrine CS2 JARVIS"
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Jarvis-Vitrine"


def _pixels(data: bytes) -> int:
    """Nombre de pixels d'une image (0 si illisible)."""
    try:
        from PIL import Image
        import io
        with Image.open(io.BytesIO(data)) as im:
            return im.width * im.height
    except Exception:  # noqa: BLE001
        return 0


def skins() -> list[dict]:
    try:
        return json.loads(DATA.read_text(encoding="utf-8")).get("skins", [])
    except (OSError, ValueError):
        return []


class Vitrine:
    def __init__(self) -> None:
        self.token = secrets.token_urlsafe(12)
        self.server: http.server.ThreadingHTTPServer | None = None
        self.proc: subprocess.Popen | None = None
        self.seq = 0
        self.cmd: dict | None = None
        self.presence = None
        self._img_lock = threading.Lock()

    # --- images (téléchargées une fois depuis Steam, puis gardées)
    def image(self, sid: str) -> bytes | None:
        if not re.fullmatch(r"[a-z0-9-]{1,80}", sid or ""):
            return None
        f = IMAGES / f"{sid}.png"
        if f.is_file():
            return f.read_bytes()
        s = next((x for x in skins() if x.get("id") == sid), None)
        if not s or not str(s.get("image", "")).startswith("https://"):
            return None
        data = None
        best = 0
        for suffix in ("/1024fx1024f", ""):                # la plus grande taille que Steam veut bien donner
            try:
                req = urllib.request.Request(s["image"].rstrip("/") + suffix, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=15) as r:
                    got = r.read()
            except Exception as e:  # noqa: BLE001
                log.debug("Vitrine : %s%s indisponible (%s)", sid, suffix, e)
                continue
            px = _pixels(got)
            if len(got) > 500 and px > best:
                data, best = got, px
            if best >= 900 * 600:
                break
        if data is None:
            log.info("Vitrine : image de %s indisponible", sid)
            return None
        IMAGES.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(f)
        return data

    def _prefetch(self) -> None:
        """Télécharge toutes les images en fond (une seule fois) : le défilement reste fluide."""
        with self._img_lock:
            missing = [s["id"] for s in skins() if not (IMAGES / f"{s['id']}.png").is_file()]
            if not missing:
                return
            log.info("Vitrine : téléchargement de %d images de skins (une seule fois).", len(missing))
            for sid in missing:
                self.image(sid)
                time.sleep(0.05)

    # --- ce que la page lit
    def snapshot(self) -> dict:
        try:
            import plan_de_travail
            sons = plan_de_travail.sound_volume()
        except Exception:  # noqa: BLE001
            sons = 60
        return {"seq": self.seq, "cmd": self.cmd, "sons": sons}

    def action(self, a: dict) -> str:
        t = a.get("type")
        if t == "journal":
            log.info("Vitrine (page) : %s", str(a.get("texte", ""))[:200])
            return "ok"
        if t == "fermer":
            threading.Thread(target=self.close, daemon=True).start()
            return "ok"
        return "inconnu"

    def command(self, kind: str, valeur: str = "") -> str:
        """Commande vocale envoyée à la page (« suivant », « montrer » + nom, « caisse »...)."""
        if not self.is_open:
            return "ÉCHEC : la vitrine n'est pas ouverte"
        self.cmd = {"type": kind, "valeur": valeur}
        self.seq += 1
        return f"OK : {kind}" + (f" {valeur}" if valeur else "")

    def _serve(self) -> int:
        vt, token = self, self.token

        class H(http.server.BaseHTTPRequestHandler):
            def _send(self, code: int, body: bytes, ctype: str, cache: bool = False) -> None:
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Cache-Control", "max-age=86400" if cache else "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _path(self) -> str | None:
                url = urllib.parse.urlparse(self.path)
                prefix = f"/{token}/"
                return url.path[len(prefix):] if url.path.startswith(prefix) or url.path == prefix[:-1] else None

            def do_GET(self):  # noqa: N802
                p = self._path()
                if p is None:
                    return self._send(404, b"", "text/plain")
                if p in ("", "index.html"):
                    return self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
                if p == "skins":
                    return self._send(200, DATA.read_bytes(), "application/json; charset=utf-8")
                if p == "etat":
                    return self._send(200, json.dumps(vt.snapshot(), ensure_ascii=False).encode("utf-8"),
                                      "application/json")
                if p.startswith("web/"):                   # moteur 3D (three.js local)
                    f = (BASE / p).resolve()
                    web = (BASE / "web").resolve()
                    if web in f.parents and f.is_file() and f.suffix == ".js":
                        return self._send(200, f.read_bytes(), "text/javascript; charset=utf-8")
                    return self._send(404, b"", "text/plain")
                if p.startswith("img/"):
                    data = vt.image(p[4:])
                    return self._send(200, data, "image/png", cache=True) if data else self._send(404, b"", "text/plain")
                return self._send(404, b"", "text/plain")

            def do_POST(self):  # noqa: N802
                if self._path() != "action":
                    return self._send(404, b"", "text/plain")
                try:
                    body = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length") or 0), 20000)))
                    out = vt.action(body)
                except Exception as e:  # noqa: BLE001
                    out = f"ÉCHEC : {e}"
                return self._send(200, json.dumps({"resultat": out}, ensure_ascii=False).encode("utf-8"),
                                  "application/json")

            def log_message(self, *_a):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self.server.server_address[1]

    # --- ouverture / fermeture
    def open(self) -> str:
        if not PAGE.is_file() or not DATA.is_file():
            return "ÉCHEC : vitrine_cs.html ou skins_cs.json introuvable"
        if self.is_open:
            self.command("rejouer")                        # déjà ouverte : on rejoue l'ouverture de caisse
            threading.Thread(target=self._bring_front, args=(5,), daemon=True).start()
            return "OK : vitrine ramenée devant (intro rejouée)"
        import intro_web
        br = intro_web.find_browser()
        if br is None:
            return "ÉCHEC : il faut Chrome ou Edge pour la vitrine"
        port = self.server.server_address[1] if self.server else self._serve()
        url = f"http://127.0.0.1:{port}/{self.token}/"
        screen = (os.environ.get("JARVIS_VITRINE_ECRAN") or "principal").strip().lower()
        try:
            import assistant
            mons = assistant.monitors()
            l, t, r, b = mons[1] if (screen in ("gauche", "secondaire", "autre") and len(mons) > 1) else mons[0]
        except Exception:  # noqa: BLE001
            l, t, r, b = 0, 0, 1920, 1080
        profile = CACHE / "vitrine_navigateur"
        profile.mkdir(parents=True, exist_ok=True)
        args = [br[0], f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check",
                "--disable-extensions", "--disable-sync", "--disable-features=Translate,MediaRouter",
                "--hide-crash-restore-bubble", f"--window-position={l},{t}", f"--window-size={r - l},{b - t}",
                "--start-fullscreen", "--autoplay-policy=no-user-gesture-required", f"--app={url}"]
        threading.Thread(target=self._prefetch, daemon=True).start()
        try:
            self.proc = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                         stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW)
        except OSError as e:
            return f"ÉCHEC : {e}"
        try:
            import plan_de_travail
            self.presence = plan_de_travail.workspace().presence
        except Exception:  # noqa: BLE001
            self.presence = None
        if self.presence is not None:
            self.presence.hidden = True                    # la sphère laisse la place à la vitrine
        threading.Thread(target=self._watch, daemon=True).start()
        threading.Thread(target=self._bring_front, args=(20,), daemon=True).start()
        log.info("Vitrine CS2 ouverte.")
        return "OK : vitrine ouverte (intro ouverture de caisse puis défilé des skins)"

    def _watch(self) -> None:
        p = self.proc
        if p is not None:
            p.wait()
        if self.proc is p:
            self._closed()

    def _closed(self) -> None:
        self.proc = None
        if self.presence is not None:
            try:
                import plan_de_travail
                still_plan = plan_de_travail.workspace().is_open
            except Exception:  # noqa: BLE001
                still_plan = False
            if not still_plan:
                self.presence.hidden = False

    def _bring_front(self, wait: float) -> None:
        if os.name != "nt":
            return
        import assistant
        end = time.monotonic() + wait
        while time.monotonic() < end:
            w = next((x for x in assistant.list_windows() if x["titre"].startswith(TITLE)), None)
            if w:
                u32 = ctypes.windll.user32
                u32.ShowWindow(w["hwnd"], 9)
                u32.SetWindowPos(w["hwnd"], wintypes.HWND(-1), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)
                assistant.focus(w["hwnd"])
                time.sleep(0.4)
                u32.SetWindowPos(w["hwnd"], wintypes.HWND(-2), 0, 0, 0, 0, 0x0001 | 0x0002)
                return
            time.sleep(0.3)
        log.warning("Fenêtre de la vitrine introuvable (Chrome/Edge a-t-il démarré ?).")

    def close(self) -> str:
        p = self.proc
        if p is None or p.poll() is not None:
            self._closed()
            return "OK : la vitrine était déjà fermée"
        self.proc = None
        try:
            subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True,
                           creationflags=CREATE_NO_WINDOW, timeout=10)
        except Exception:  # noqa: BLE001
            p.kill()
        self._closed()
        log.info("Vitrine CS2 fermée.")
        return "OK : vitrine fermée"

    @property
    def is_open(self) -> bool:
        return self.proc is not None and self.proc.poll() is None


_vt: Vitrine | None = None


def vitrine() -> Vitrine:
    global _vt
    if _vt is None:
        _vt = Vitrine()
    return _vt
