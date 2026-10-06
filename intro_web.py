"""Nouvelle intro de Jarvis : la page intro.html affichée en plein écran par le navigateur, sur chaque écran.

Pourquoi le navigateur : il dessine des traits lisses, des lueurs et des flous, à 60 images/s, ce que
l'ancienne interface (Tkinter) ne sait pas faire (traits pixelisés).

Fonctionnement :
  1. un petit serveur local sert intro.html et donne l'heure de départ commune (t0) ;
  2. une fenêtre plein écran par écran (Chrome, sinon Edge), avec un profil à part (ne touche pas à ton Chrome) ;
  3. quand toutes les pages sont prêtes, départ synchronisé : Jarvis joue le son de démarrage au même instant ;
  4. à la fin, fondu des fenêtres puis fermeture.
Si quelque chose échoue, jarvis.py repasse automatiquement sur l'ancienne intro.

Réglages (.env) :  JARVIS_INTRO=classique (ancienne intro)   JARVIS_INTRO_NAVIGATEUR=edge (forcer Edge)
"""
from __future__ import annotations

import ctypes
import http.server
import json
import logging
import os
import subprocess
import threading
import time
import urllib.parse
from ctypes import wintypes
from pathlib import Path

log = logging.getLogger("jarvis")
BASE = Path(__file__).resolve().parent
PAGE = BASE / "intro.html"
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def find_browser() -> tuple[str, str] | None:
    """(chemin, « chrome » ou « edge »)."""
    pref = (os.environ.get("JARVIS_INTRO_NAVIGATEUR") or "").strip().lower()
    bases = [os.environ.get("ProgramFiles", r"C:\Program Files"),
             os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), os.environ.get("LOCALAPPDATA", "")]
    found = {}
    for b in bases:
        if not b:
            continue
        for kind, rel in (("chrome", ("Google", "Chrome", "Application", "chrome.exe")),
                          ("edge", ("Microsoft", "Edge", "Application", "msedge.exe"))):
            p = os.path.join(b, *rel)
            if kind not in found and os.path.isfile(p):
                found[kind] = p
    order = ["edge", "chrome"] if pref == "edge" else ["chrome", "edge"]
    for kind in order:
        if kind in found:
            return found[kind], kind
    return None


class _Sync:
    """Attend que chaque écran soit prêt, puis fixe l'heure de départ commune."""

    def __init__(self, roles: list[str]) -> None:
        self.roles = set(roles)
        self.ready: set[str] = set()
        self.first: float | None = None
        self.t0: float | None = None
        self.lock = threading.Lock()
        self.event = threading.Event()

    def poll(self, role: str) -> float | None:
        with self.lock:
            now = time.time()
            if role in self.roles:
                self.ready.add(role)
                self.first = self.first or now
            if self.t0 is None and self.ready and (self.ready >= self.roles or now - self.first > 4.0):
                self.t0 = now + 0.35                 # petite marge : tout le monde démarre ensemble
                self.event.set()
            return self.t0


class WebIntro:
    def __init__(self, main_rect, side_rect, params: dict, duration: float) -> None:
        self.duration = float(duration)
        self.screens = {"main": main_rect, "side": side_rect} if side_rect else {"solo": main_rect}
        self.params = {k: str(v) for k, v in params.items() if v not in (None, "")}
        self.sync = _Sync(list(self.screens))
        self.procs: list[subprocess.Popen] = []
        self.server: http.server.ThreadingHTTPServer | None = None
        self.hwnds: dict[str, int] = {}
        self.t0: float | None = None

    # --- serveur local
    def _serve(self) -> int:
        page = PAGE.read_bytes()
        sync = self.sync

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                url = urllib.parse.urlparse(self.path)
                if url.path.startswith("/sync"):
                    role = urllib.parse.parse_qs(url.query).get("role", [""])[0]
                    t0 = sync.poll(role)
                    body = json.dumps({"t0": t0 * 1000 if t0 else None}).encode()
                    ctype = "application/json"
                elif url.path.endswith("/faceit_niveau.png"):
                    icon = BASE / "faceit_niveau.png"          # icône de niveau ajoutée par l'utilisateur
                    if not icon.is_file():
                        self.send_response(404)
                        self.end_headers()
                        return
                    body, ctype = icon.read_bytes(), "image/png"
                else:
                    body, ctype = page, "text/html; charset=utf-8"
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_a):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self.server.server_address[1]

    # --- lancement
    def start(self, timeout: float = 12.0) -> float | None:
        """Ouvre les fenêtres et attend le départ commun. Renvoie t0 (time.time()) ou None si échec."""
        if not PAGE.is_file():
            log.warning("intro.html introuvable : ancienne intro.")
            return None
        br = find_browser()
        if br is None:
            log.warning("Ni Chrome ni Edge trouvé : ancienne intro.")
            return None
        exe, kind = br
        port = self._serve()
        for role, (l, t, r, b) in self.screens.items():
            q = urllib.parse.urlencode({**self.params, "auto": "1", "role": role, "d": f"{self.duration:g}"})
            url = f"http://127.0.0.1:{port}/intro.html?{q}"
            profile = BASE / ".cache" / "intro_navigateur" / role
            profile.mkdir(parents=True, exist_ok=True)
            args = [exe, f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check",
                    "--disable-extensions", "--disable-sync", "--disable-features=Translate,MediaRouter",
                    "--noerrdialogs", "--disable-session-crashed-bubble", "--hide-crash-restore-bubble",
                    "--disable-pinch", "--overscroll-history-navigation=0",
                    f"--window-position={l},{t}", f"--window-size={r - l},{b - t}", "--kiosk"]
            if kind == "edge":
                args += ["--edge-kiosk-type=fullscreen", "--no-startup-window-restore"]
            args.append(url)
            try:
                self.procs.append(subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                                   stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW))
            except OSError as e:
                log.warning("Navigateur impossible à lancer (%s) : ancienne intro.", e)
                self.close()
                return None
        threading.Thread(target=self._pin_windows, args=(timeout,), daemon=True).start()
        if not self.sync.event.wait(timeout):
            log.warning("L'intro n'a pas démarré à temps : ancienne intro.")
            self.close()
            return None
        self.t0 = self.sync.t0
        log.info("Nouvelle intro lancée (%s, %d écran(s)).", kind, len(self.screens))
        return self.t0

    # --- fenêtres : devant tout, à la bonne place
    def _find(self, title: str) -> int | None:
        user32 = ctypes.windll.user32
        found: list[int] = []
        buf = ctypes.create_unicode_buffer(256)

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def enum(hwnd, _lp):
            if user32.IsWindowVisible(hwnd):
                user32.GetWindowTextW(hwnd, buf, 256)
                if buf.value.startswith(title):
                    found.append(int(hwnd))
            return True

        user32.EnumWindows(enum, 0)
        return found[0] if found else None

    def _pin_windows(self, timeout: float) -> None:
        user32 = ctypes.windll.user32
        user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                        ctypes.c_int, ctypes.c_int, wintypes.UINT]
        end = time.monotonic() + timeout + self.duration
        todo = dict(self.screens)
        while todo and time.monotonic() < end:
            for role, (l, t, r, b) in list(todo.items()):
                h = self._find(f"Intro Jarvis {role}")
                if h:
                    # au-dessus de tout (FACEIT et Discord s'ouvrent dessous) et sur le bon écran
                    user32.SetWindowPos(h, wintypes.HWND(-1), l, t, r - l, b - t, 0x0040)
                    self.hwnds[role] = h
                    del todo[role]
            time.sleep(0.1)

    # --- fin
    def finish(self) -> None:
        """Attend la fin de l'intro, fondu des fenêtres, puis fermeture."""
        if self.t0 is None:
            return
        time.sleep(max(0.0, self.t0 + self.duration - 0.1 - time.time()))
        user32 = ctypes.windll.user32
        user32.SetLayeredWindowAttributes.argtypes = [wintypes.HWND, wintypes.COLORREF, ctypes.c_ubyte,
                                                      wintypes.DWORD]
        try:
            for h in self.hwnds.values():
                user32.SetWindowLongW(h, -20, user32.GetWindowLongW(h, -20) | 0x00080000)   # calque
            steps = 20
            for i in range(steps, -1, -1):                                               # fondu ~0,6 s
                for h in self.hwnds.values():
                    user32.SetLayeredWindowAttributes(h, 0, int(255 * i / steps), 2)
                time.sleep(0.03)
        except Exception:  # noqa: BLE001
            pass
        self.close()

    def close(self) -> None:
        for p in self.procs:
            try:
                subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True,
                               creationflags=CREATE_NO_WINDOW, timeout=10)
            except Exception:  # noqa: BLE001
                try:
                    p.kill()
                except Exception:  # noqa: BLE001
                    pass
        self.procs = []
        if self.server:
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            self.server = None
