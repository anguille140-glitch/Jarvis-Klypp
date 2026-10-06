"""Mode caméra de Jarvis : scan du visage, puis contrôle du PC à la main (façon Iron Man).

  « Jarvis, active la caméra »   -> une fenêtre holographique s'ouvre dans le coin de l'écran
  1. scan biométrique : il compare la forme de ton visage à celle enregistrée la première fois
  2. contrôle gestuel :
       main ouverte qui bouge ......... déplace le curseur
       pouce + index pincés ........... clic (garder pincé = glisser)
       pouce + majeur pincés .......... clic droit
       index + majeur tendus .......... défiler (monte / descend la main)
       les DEUX mains pincées ......... zoom (écarte = zoome, rapproche = dézoome)
       poing fermé .................... pause
  « Jarvis, coupe la caméra »    -> tout se ferme

La vision tourne dans Chrome (MediaPipe, carte graphique) : camera.html. Ce module sert la page, reçoit
les gestes et pilote la souris. La reconnaissance du visage compare la FORME du visage (distances entre
points) : c'est un filtre, pas une sécurité forte.

Réglages (.env) : JARVIS_CAMERA_ECRAN=tous (la main couvre tous les écrans ; défaut : écran principal)
                  JARVIS_VISAGE_TOLERANCE=0.09 (plus grand = plus tolérant)
"""
from __future__ import annotations

import atexit
import base64
import ctypes
import hashlib
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
PAGE = BASE / "camera.html"
FACE_FILE = BASE / ".cache" / "visage.json"
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
PANEL_W, PANEL_H = 680, 500
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or "").strip() or default


def _monitors() -> list[tuple[int, int, int, int]]:
    user32 = ctypes.windll.user32
    rects: list[tuple[int, int, int, int]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
    def cb(_h, _d, lp, _l):
        r = lp.contents
        rects.append((int(r.left), int(r.top), int(r.right), int(r.bottom)))
        return True

    user32.EnumDisplayMonitors(None, None, cb, 0)
    return rects or [(0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))]


def _main_screen() -> tuple[int, int, int, int]:
    rects = _monitors()
    return next((r for r in rects if r[0] == 0 and r[1] == 0), rects[0])


def _target_rect() -> tuple[int, int, int, int]:
    if _env("JARVIS_CAMERA_ECRAN").lower() == "tous":
        u = ctypes.windll.user32
        x, y = u.GetSystemMetrics(76), u.GetSystemMetrics(77)
        return x, y, x + u.GetSystemMetrics(78), y + u.GetSystemMetrics(79)
    return _main_screen()


# ---------------------------------------------------------------- souris
class Mouse:
    def __init__(self) -> None:
        self.u = ctypes.windll.user32
        self.u.mouse_event.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_size_t]
        self.rect = _target_rect()
        self.is_down = False

    def move(self, u: float, v: float) -> None:
        l, t, r, b = self.rect
        self.u.SetCursorPos(int(l + max(0.0, min(1.0, u)) * (r - l - 1)), int(t + max(0.0, min(1.0, v)) * (b - t - 1)))

    def down(self) -> None:
        if not self.is_down:
            self.u.mouse_event(0x0002, 0, 0, 0, 0)
            self.is_down = True

    def up(self) -> None:
        if self.is_down:
            self.u.mouse_event(0x0004, 0, 0, 0, 0)
            self.is_down = False

    def right(self) -> None:
        self.u.mouse_event(0x0008, 0, 0, 0, 0)
        self.u.mouse_event(0x0010, 0, 0, 0, 0)

    def scroll(self, n: int) -> None:
        self.u.mouse_event(0x0800, 0, 0, ctypes.c_uint32(int(n) * 120 & 0xFFFFFFFF).value, 0)

    def zoom(self, n: int) -> None:
        """Ctrl + molette : zoome dans Chrome, les images, Maps, les documents..."""
        self.u.keybd_event(0x11, 0, 0, 0)
        self.scroll(n)
        self.u.keybd_event(0x11, 0, 2, 0)


# ---------------------------------------------------------------- visage
def check_face(sig: list[float]) -> dict:
    """Compare l'empreinte du visage à celle enregistrée (la 1re fois : enregistrement)."""
    try:
        sig = [float(x) for x in sig]
    except (TypeError, ValueError):
        return {"ok": False, "score": 0}
    if not FACE_FILE.is_file():
        FACE_FILE.parent.mkdir(parents=True, exist_ok=True)
        FACE_FILE.write_text(json.dumps({"sig": sig}), encoding="utf-8")
        log.info("Visage enregistré (première utilisation).")
        return {"ok": True, "score": 1.0, "enrolled": True}
    ref = json.loads(FACE_FILE.read_text(encoding="utf-8")).get("sig") or []
    if len(ref) != len(sig):
        FACE_FILE.unlink(missing_ok=True)
        return check_face(sig)
    diff = sum(abs(a - b) / max(1e-6, abs(b)) for a, b in zip(sig, ref)) / len(ref)
    tol = float(_env("JARVIS_VISAGE_TOLERANCE", "0.09"))
    score = max(0.0, 1.0 - diff / (2 * tol))
    ok = diff <= tol
    log.info("Visage : écart %.3f (tolérance %.3f) -> %s", diff, tol, "reconnu" if ok else "refusé")
    return {"ok": ok, "score": round(score, 3), "enrolled": False}


def reset_face() -> None:
    FACE_FILE.unlink(missing_ok=True)


# ---------------------------------------------------------------- navigateur
def _browser() -> str | None:
    for b in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
              os.environ.get("LOCALAPPDATA", "")):
        for rel in (("Google", "Chrome", "Application", "chrome.exe"), ("Microsoft", "Edge", "Application", "msedge.exe")):
            p = os.path.join(b, *rel) if b else ""
            if p and os.path.isfile(p):
                return p
    return None


class CameraMode:
    def __init__(self, say=None, user: str = "Klypp") -> None:
        self.say = say or (lambda _t: None)
        self.user = user
        self.server: http.server.ThreadingHTTPServer | None = None
        self.proc: subprocess.Popen | None = None
        self.mouse: Mouse | None = None
        self.active = False
        self.last_msg = 0.0
        atexit.register(self.stop)

    # --- serveur local : page + gestes
    def _serve(self) -> int:
        page = PAGE.read_bytes()
        me = self

        class H(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"                    # connexions réutilisées (plus d'épuisement)

            def _reply(self, body: bytes, ctype: str = "application/json") -> None:
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):  # noqa: N802
                if self.headers.get("Upgrade", "").lower() == "websocket":
                    me._websocket(self)
                    self.close_connection = True
                    return
                self._reply(page, "text/html; charset=utf-8")

            def do_POST(self):  # noqa: N802
                n = int(self.headers.get("Content-Length") or 0)
                try:
                    data = json.loads(self.rfile.read(n) or b"{}")
                except ValueError:
                    data = {}
                path = urllib.parse.urlparse(self.path).path
                out: dict = {}
                try:
                    if path.endswith("/cmd"):
                        me._command(data)
                    elif path.endswith("/face"):
                        out = check_face(data.get("sig") or [])
                    elif path.endswith("/event"):
                        me._event(data)
                except Exception:  # noqa: BLE001
                    log.exception("Mode caméra : erreur sur %s", path)
                self._reply(json.dumps(out).encode())

            def log_message(self, *_a):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self.server.server_address[1]

    # --- WebSocket : UNE connexion permanente pour tous les gestes (avant : une connexion par geste,
    #     Windows finissait par être à court de connexions et la souris se figeait)
    def _websocket(self, h) -> None:
        key = h.headers.get("Sec-WebSocket-Key", "")
        accept = base64.b64encode(hashlib.sha1((key + WS_GUID).encode()).digest()).decode()
        h.send_response(101, "Switching Protocols")
        h.send_header("Upgrade", "websocket")
        h.send_header("Connection", "Upgrade")
        h.send_header("Sec-WebSocket-Accept", accept)
        h.end_headers()
        h.wfile.flush()
        rf, wf = h.rfile, h.wfile
        log.info("Mode caméra : liaison gestes établie.")
        try:
            while self.active:
                head = rf.read(2)
                if len(head) < 2:
                    break
                op, ln = head[0] & 0x0F, head[1] & 0x7F
                if ln == 126:
                    ln = int.from_bytes(rf.read(2), "big")
                elif ln == 127:
                    ln = int.from_bytes(rf.read(8), "big")
                mask = rf.read(4) if head[1] & 0x80 else b"\0\0\0\0"
                data = bytes(b ^ mask[i % 4] for i, b in enumerate(rf.read(ln)))
                if op == 8:                                   # fermeture
                    break
                if op == 9:                                   # ping -> pong
                    wf.write(bytes([0x8A, len(data)]) + data)
                    wf.flush()
                    continue
                if op == 1:
                    try:
                        msg = json.loads(data.decode("utf-8"))
                    except ValueError:
                        continue
                    if msg.get("t") == "ping":                # mesure de latence pour l'affichage
                        out = json.dumps({"t": "pong", "id": msg.get("id")}).encode()
                        wf.write(bytes([0x81, len(out)]) + out)
                        wf.flush()
                    else:
                        self._command(msg)
        except (OSError, ValueError):
            pass
        finally:
            if self.mouse:
                self.mouse.up()                               # jamais de clic resté enfoncé
            log.info("Mode caméra : liaison gestes fermée (la page se reconnecte toute seule).")

    def _watchdog(self) -> None:
        """Relâche le clic si plus aucun geste n'arrive (main sortie du champ, page figée...)."""
        while self.active:
            time.sleep(0.5)
            if self.mouse and self.mouse.is_down and time.monotonic() - self.last_msg > 2.0:
                self.mouse.up()
                log.info("Mode caméra : clic relâché (plus de geste reçu).")

    def _command(self, d: dict) -> None:
        m = self.mouse
        if m is None:
            return
        self.last_msg = time.monotonic()
        t = d.get("t")
        if t == "move":
            m.move(float(d.get("u", 0)), float(d.get("v", 0)))
        elif t == "down":
            m.down()
        elif t == "up":
            m.up()
        elif t == "right":
            m.right()
        elif t == "scroll":
            m.scroll(int(d.get("n", 0)))
        elif t == "zoom":
            m.zoom(int(d.get("n", 0)))

    def _event(self, d: dict) -> None:
        if d.get("t") == "auth":
            if d.get("ok"):
                msg = ("Profil enregistré. Contrôle gestuel activé, monsieur." if d.get("enrolled")
                       else "Identité confirmée. Contrôle gestuel activé, monsieur.")
            else:
                msg = "Visage non reconnu. Accès refusé."
            threading.Thread(target=self.say, args=(msg,), daemon=True).start()
        elif d.get("t") == "error":
            log.warning("Mode caméra : %s", d.get("msg"))

    # --- marche / arrêt
    def start(self) -> str:
        if self.active:
            return "La caméra est déjà active."
        if not PAGE.is_file():
            return "ÉCHEC : camera.html introuvable."
        exe = _browser()
        if not exe:
            return "ÉCHEC : il faut Chrome ou Edge pour le mode caméra."
        self.mouse = Mouse()
        port = self._serve()
        l, t, r, b = _main_screen()
        x, y = r - PANEL_W - 24, b - PANEL_H - 70                 # coin en bas à droite de l'écran principal
        profile = BASE / ".cache" / "camera_navigateur"
        profile.mkdir(parents=True, exist_ok=True)
        url = f"http://127.0.0.1:{port}/camera.html?" + urllib.parse.urlencode({"user": self.user})
        args = [exe, f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check",
                "--use-fake-ui-for-media-stream",                  # autorise la caméra sans fenêtre de demande
                "--disable-backgrounding-occluded-windows", "--disable-renderer-backgrounding",
                "--disable-background-timer-throttling", "--disable-extensions",
                f"--window-position={x},{y}", f"--window-size={PANEL_W},{PANEL_H}", f"--app={url}"]
        try:
            self.proc = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                         stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW)
        except OSError as e:
            self.stop()
            return f"ÉCHEC : {e}"
        self.active = True
        threading.Thread(target=self._style_window, args=(x, y), daemon=True).start()
        threading.Thread(target=self._watchdog, daemon=True).start()
        log.info("Mode caméra lancé.")
        return "Mode caméra lancé : scan du visage en cours."

    def _style_window(self, x: int, y: int) -> None:
        """Fenêtre sans bordure, toujours devant, absente de la barre des tâches."""
        u = ctypes.windll.user32
        u.FindWindowW.restype = wintypes.HWND
        u.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        u.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
        u.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   wintypes.UINT]
        for _ in range(100):
            h = u.FindWindowW(None, "Jarvis Vision")
            if h:
                style = u.GetWindowLongW(h, -16) & ~0x00C00000 & ~0x00040000      # sans barre de titre ni bord
                u.SetWindowLongW(h, -16, style)
                u.SetWindowLongW(h, -20, (u.GetWindowLongW(h, -20) | 0x80) & ~0x40000)
                u.SetWindowPos(h, wintypes.HWND(-1), x, y, PANEL_W, PANEL_H, 0x0020 | 0x0040)
                return
            time.sleep(0.1)

    def stop(self) -> str:
        was = self.active
        self.active = False
        if self.mouse:
            self.mouse.up()
        if self.proc:
            try:
                subprocess.run(["taskkill", "/PID", str(self.proc.pid), "/T", "/F"], capture_output=True,
                               creationflags=CREATE_NO_WINDOW, timeout=10)
            except Exception:  # noqa: BLE001
                pass
            self.proc = None
        if self.server:
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            self.server = None
        return "Mode caméra coupé." if was else "La caméra n'était pas active."


if __name__ == "__main__":                          # test seul : python camera_mode.py
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:  # noqa: BLE001
        pass
    cam = CameraMode(say=lambda t: log.info("Jarvis : %s", t))
    print(cam.start())
    try:
        while cam.proc and cam.proc.poll() is None:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    print(cam.stop())
