"""Le visage de Jarvis : la sphère bleue, fondue dans ton écran.

- Invisible au repos. Quand tu dis « Jarvis », elle apparaît en fondu au milieu de l'écran, par-dessus
  tout, mais SANS fond : son noir est transparent, seule la lumière bleue se mélange à ton fond d'écran.
- Elle est toujours vivante : elle respire, tourne, ses bords ondulent, des particules gravitent.
- Quand elle t'écoute : elle s'illumine. Quand Jarvis réfléchit : elle tourne vite et pulse.
- Quand il parle : elle vibre au rythme EXACT de sa voix, avec ses paroles en sous-titre.
- Puis elle s'efface en fondu. Les clics de souris passent au travers : elle ne gêne jamais.

Réglages dans .env :
  JARVIS_SPHERE=non            désactive la sphère
  JARVIS_SPHERE_ECRAN=gauche   l'affiche sur l'écran de gauche (défaut : principal)
  JARVIS_SPHERE_TAILLE=0.45    taille (part de la hauteur de l'écran)
  JARVIS_SPHERE_POSITION=fond    juste au-dessus du bureau, derrière tes fenêtres (défaut)
                        =devant  par-dessus tout
  JARVIS_FOND_NOIR=ecran       le bureau se fond au noir quand Jarvis s'allume (défaut)
                  =bureau      seul le fond d'écran Windows devient noir (les fenêtres restent visibles)
                  =non         pas de fond noir
  JARVIS_FOND_NOIR_OPACITE=100 noir total ; 85 = on devine encore l'écran derrière
"""
from __future__ import annotations

import ctypes
import logging
import math
import os
import random
import threading
import time
from ctypes import wintypes
from pathlib import Path

import numpy as np
from PIL import Image

log = logging.getLogger("jarvis")
BASE = Path(__file__).resolve().parent
IMAGE = BASE / "jarvis_orb.png"
FPS = 30


# ============================================================================
# Moteur de rendu (indépendant de l'affichage)
# ============================================================================
class OrbRenderer:
    """Déforme l'image de la sphère à chaque image : rotation, respiration, ondulation, éclat."""

    SRC_RADIUS = 0.47          # rayon de la sphère dans l'image d'origine (part de la largeur)

    def __init__(self, image_path: Path = IMAGE, n: int = 460) -> None:
        img = Image.open(image_path).convert("RGB")
        w, h = img.size
        side = min(w, h)
        img = img.crop(((w - side) // 2, (h - side) // 2, (w - side) // 2 + side, (h - side) // 2 + side))
        self.S = 640
        self.src = np.asarray(img.resize((self.S, self.S), Image.LANCZOS), dtype=np.float32)
        self.src_r = self.SRC_RADIUS * self.S
        self.src_flat = np.vstack([self.src.reshape(-1, 3), np.zeros((1, 3), np.float32)])
        self.black = self.S * self.S
        self.N = n                                   # taille de calcul (agrandie ensuite à l'affichage)
        self.margin = 1.35                           # place autour de la sphère (pour qu'elle grossisse)
        c = (n - 1) / 2
        yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
        dx, dy = xx - c, yy - c
        self.r = np.hypot(dx, dy) / (n / 2 / self.margin)          # 1.0 = bord de la sphère
        th = np.arctan2(dy, dx)
        self.th = th
        self.bins = 1024
        self.th_idx = ((th + np.pi) / (2 * np.pi) * self.bins).astype(np.int32) % self.bins
        self.th_tab = np.linspace(-np.pi, np.pi, self.bins, endpoint=False, dtype=np.float32)
        self.inner = np.clip(1 - self.r, 0, 1) ** 1.5                 # pour le tourbillon intérieur
        ring = np.exp(-((self.r - 1.0) / 0.10) ** 2) + 0.35 * np.exp(-((self.r - 1.0) / 0.30) ** 2)
        ring *= np.clip((self.margin - self.r) / 0.25, 0, 1) ** 2          # s'éteint avant le bord du cadre
        core = np.exp(-(self.r / 0.55) ** 2)
        color = np.array([30, 110, 255], np.float32) / 255
        self.ring = ring[..., None] * color
        self.core = core[..., None] * np.array([20, 70, 255], np.float32) / 255
        self.rot = 0.0
        self.last_t: float | None = None

    def render(self, t: float, level: float = 0.0, mode: str = "idle") -> np.ndarray:
        """Image (N, N, 3) uint8 de la sphère à l'instant t. level = intensité de la voix (0 à 1)."""
        dt = 0.0 if self.last_t is None else min(0.1, t - self.last_t)
        self.last_t = t
        listening = mode == "listening"
        thinking = mode == "thinking"
        # rotation : lente au repos, rapide en réflexion, poussée par la voix
        self.rot += dt * (0.06 + (0.9 if thinking else 0) + 0.35 * level)
        breathe = 0.018 * math.sin(t * 1.15) + 0.008 * math.sin(t * 2.7 + 1)
        scale = 1.0 + breathe + 0.13 * level + (0.05 if listening else 0) + (0.025 * math.sin(t * 6) if thinking else 0)

        # ondulation du bord (calculée sur 1024 angles puis appliquée : très rapide)
        a = 0.010 + 0.06 * level + (0.012 if thinking else 0) + (0.008 if listening else 0)
        tt = self.th_tab
        wob = a * (np.sin(5 * tt + 1.3 * t) + 0.6 * np.sin(9 * tt - 2.1 * t + 1.0)
                   + 0.45 * np.sin(3 * tt + 0.7 * t) + 0.8 * level * np.sin(14 * tt + 9.0 * t))
        w = wob[self.th_idx]

        swirl = (0.25 * math.sin(t * 0.37) + 0.6 * level * math.sin(t * 3.1)) * self.inner
        rs = self.r / (scale * (1.0 + w))
        ths = self.th - self.rot + swirl
        sx = (self.S - 1) / 2 + rs * self.src_r * np.cos(ths)
        sy = (self.S - 1) / 2 + rs * self.src_r * np.sin(ths)
        ix = sx.astype(np.int32)
        iy = sy.astype(np.int32)
        bad = (ix < 0) | (ix >= self.S) | (iy < 0) | (iy >= self.S)
        idx = np.clip(iy, 0, self.S - 1) * self.S + np.clip(ix, 0, self.S - 1)
        idx[bad] = self.black                         # pixel noir réservé
        out = np.take(self.src_flat, idx, axis=0)

        # éclat : scintillement lent + voix ; halo autour
        gain = 0.88 + 0.10 * math.sin(t * 0.9) + 0.9 * level + (0.25 if listening else 0) + (0.12 if thinking else 0)
        out *= gain
        halo = 0.10 + 0.08 * math.sin(t * 1.15) + 0.85 * level + (0.3 if listening else 0) + (0.15 if thinking else 0)
        out += self.ring * (255 * halo)
        out += self.core * (255 * (0.04 + 0.35 * level))
        if listening:
            out[..., 1] *= 1.12                       # un peu plus cyan quand il écoute
        return np.clip(out, 0, 255).astype(np.uint8)


def speech_envelope(pcm: np.ndarray, rate: int, fps: int = 60) -> np.ndarray:
    """Intensité de la voix image par image (0 à 1)."""
    x = np.asarray(pcm, dtype=np.float32).ravel()
    if x.size == 0:
        return np.zeros(1, np.float32)
    hop = max(1, rate // fps)
    n = x.size // hop
    if n == 0:
        return np.zeros(1, np.float32)
    rms = np.sqrt(np.mean(x[: n * hop].reshape(n, hop) ** 2, axis=1))
    ref = float(np.percentile(rms, 95)) or 1.0
    env = np.clip(rms / ref, 0, 1.2) ** 0.8
    return env.astype(np.float32)


# ============================================================================
# État partagé avec l'assistant (appelé depuis d'autres fils)
# ============================================================================
class Presence:
    def __init__(self) -> None:
        self.mode = "idle"
        self.status = "EN LIGNE"
        self.subtitle = ""
        self.env: np.ndarray | None = None
        self.env_t0 = 0.0
        self.fake_speech = False
        self.pinned = False                  # démo : toujours visible
        self.pinned_until = 0.0              # visible un instant après un changement de réglage
        self.last_active = 0.0               # dernier moment où Jarvis écoutait / parlait
        self.lock = threading.Lock()
        self.style = _load_style()           # taille, taille quand il parle, fond noir (réglables à la voix)

    def set_style(self, action: str, valeur: str = "") -> str:
        """« Jarvis, réduis ton orbe quand tu me parles », « fais-toi plus grand », « enlève le fond noir »..."""
        with self.lock:
            st = dict(self.style)
            if action == "reinitialiser":
                st = {}
            elif action == "etat":
                pass
            elif action in ("taille", "taille_parole"):
                cur = st.get(action) or st.get("taille") or BASE_SIZE
                v = _size_value(valeur, cur)
                if v is None:
                    return "ÉCHEC : valeur de taille incomprise (petite, grande, plus_petite, ou un pourcentage)"
                st[action] = v
            elif action == "fond_noir":
                v = _percent(valeur, st.get("fond_noir", 100))
                if v is None:
                    return "ÉCHEC : valeur incomprise (0 à 100, ou aucun / leger / moyen / total)"
                st["fond_noir"] = v
            else:
                return f"ÉCHEC : action inconnue {action}"
            self.style = st
            _save_style(st)
            self.pinned_until = time.monotonic() + 4.0          # se montre un instant pour voir le résultat
            self.last_active = time.monotonic()
        t = st.get("taille") or BASE_SIZE
        tp = st.get("taille_parole")
        return (f"OK : sphère {round(t * 100)} % de l'écran"
                + (f", {round(tp * 100)} % quand je parle" if tp else "")
                + f", fond noir {st.get('fond_noir', 100)} %")

    def set_state(self, mode: str, status: str | None = None) -> None:
        with self.lock:
            self.mode = mode
            self.last_active = time.monotonic()
            if mode != "speaking":
                self.env, self.fake_speech = None, False
            self.status = status if status is not None else {
                "idle": "EN LIGNE", "listening": "J'ÉCOUTE", "thinking": "ANALYSE", "speaking": "",
            }.get(mode, "")
            if mode in ("listening", "thinking"):
                self.subtitle = ""

    def speak(self, pcm: np.ndarray, rate: int, text: str = "") -> None:
        """Juste avant de jouer la voix : la sphère suivra son volume."""
        env = speech_envelope(pcm, rate)
        with self.lock:
            self.last_active = time.monotonic()
            self.mode, self.status = "speaking", ""
            self.env, self.env_t0, self.fake_speech = env, time.monotonic(), False
            if text:
                self.subtitle = text

    def speak_unknown(self, text: str = "") -> None:
        """Voix de Windows (on n'a pas le son) : animation de parole imitée."""
        with self.lock:
            self.last_active = time.monotonic()
            self.mode, self.status, self.env, self.fake_speech = "speaking", "", None, True
            if text:
                self.subtitle = text

    def say_text(self, text: str) -> None:
        with self.lock:
            self.subtitle = text

    def level(self, now: float) -> tuple[str, float]:
        with self.lock:
            mode = self.mode
            if mode != "speaking":
                return mode, 0.0
            if self.env is not None:
                i = int((now - self.env_t0) * 60)
                return mode, float(self.env[i]) if 0 <= i < self.env.size else 0.0
            if self.fake_speech:
                syll = abs(math.sin(now * 8.3)) * (0.6 + 0.4 * math.sin(now * 2.1))
                return mode, 0.25 + 0.6 * syll * (0.7 + 0.3 * random.random())
            return mode, 0.0


# ============================================================================
# Fenêtre Windows transparente (vraie transparence pixel par pixel)
# ============================================================================
STYLE_FILE = BASE / ".cache" / "sphere.json"
SIZE_MIN, SIZE_MAX = 0.10, 0.70          # part de la hauteur de l'écran
try:
    BASE_SIZE = max(SIZE_MIN, min(SIZE_MAX, float(os.environ.get("JARVIS_SPHERE_TAILLE") or 0.45)))
except ValueError:
    BASE_SIZE = 0.45
_WORDS = {"tres_petite": 0.15, "minuscule": 0.12, "petite": 0.25, "moyenne": 0.40, "normale": 0.45,
          "grande": 0.58, "tres_grande": 0.70, "geante": 0.70}


def _load_style() -> dict:
    try:
        import json
        return json.loads(STYLE_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _save_style(st: dict) -> None:
    try:
        import json
        STYLE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STYLE_FILE.write_text(json.dumps(st), encoding="utf-8")
    except OSError:
        pass


def _size_value(v: str, cur: float) -> float | None:
    import re
    k = re.sub(r"[\s-]+", "_", (v or "").strip().lower()).replace("é", "e").replace("è", "e").replace("ê", "e")
    if k in _WORDS:
        x = _WORDS[k]
    elif k in ("plus_petite", "plus_petit", "reduire", "moins_grande"):
        x = cur * 0.7
    elif k in ("plus_grande", "plus_grand", "agrandir"):
        x = cur * 1.35
    else:
        m = re.search(r"\d+(?:[.,]\d+)?", k)
        if not m:
            return None
        n = float(m.group(0).replace(",", "."))
        x = n / 100 if n > 1 else n
    return round(max(SIZE_MIN, min(SIZE_MAX, x)), 3)


def _percent(v: str, cur: int) -> int | None:
    import re
    import unicodedata
    k = "".join(c for c in unicodedata.normalize("NFKD", (v or "").strip().lower()) if not unicodedata.combining(c))
    words = {"aucun": 0, "non": 0, "sans": 0, "enleve": 0, "leger": 40, "moyen": 70, "total": 100, "oui": 100,
             "plein": 100}
    for w, n in words.items():
        if w in k:
            return n
    m = re.search(r"\d+", k)
    return max(0, min(100, int(m.group(0)))) if m else None


LINGER_S = 7.0        # reste visible après la réponse (le temps d'enchaîner sans redire « Jarvis »)
FADE_IN_S, FADE_OUT_S = 1.0, 0.9      # apparition / disparition


def _monitor_rect(which: str) -> tuple[int, int, int, int]:
    user32 = ctypes.windll.user32
    rects: list[tuple[int, int, int, int]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC,
                        ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
    def cb(_hm, _hdc, lprc, _lp):
        r = lprc.contents
        rects.append((int(r.left), int(r.top), int(r.right), int(r.bottom)))
        return True

    user32.EnumDisplayMonitors(None, None, cb, 0)
    rects = rects or [(0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))]
    main = next((r for r in rects if r[0] == 0 and r[1] == 0), rects[0])
    if which == "gauche" and len(rects) > 1:
        return min(rects, key=lambda r: r[0])
    return main


def _font(names: list[str], size: int):
    from PIL import ImageFont

    for n in names:
        for p in (Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / n, Path(n)):
            try:
                return ImageFont.truetype(str(p), size)
            except OSError:
                continue
    try:
        return ImageFont.load_default(size)
    except TypeError:
        return ImageFont.load_default()


class Compositor:
    """Assemble une image : sphère + particules + textes, puis la transforme en BGRA « fondu »
    (le noir devient transparent, la lumière se mélange à ce qu'il y a derrière)."""

    def __init__(self, W: int, H: int, D: int, scale: float) -> None:
        self.W, self.H, self.D = W, H, D
        self.renderer = OrbRenderer()
        self.M = int(D * self.renderer.margin)
        self.cx, self.cy = W / 2, self.M / 2
        self.f_title = _font(["consolab.ttf", "consola.ttf", "DejaVuSansMono-Bold.ttf"], int(20 * scale))
        self.f_status = _font(["consola.ttf", "DejaVuSansMono.ttf"], int(13 * scale))
        self.f_sub = _font(["segoeui.ttf", "DejaVuSans.ttf"], int(19 * scale))
        self.scale = scale
        self.parts = [{"a": random.uniform(0, 2 * math.pi), "r": random.uniform(0.52, 0.80),
                       "v": random.uniform(0.05, 0.25) * random.choice((-1, 1)), "z": random.uniform(1, 3.2),
                       "ph": random.uniform(0, 6.28)} for _ in range(70)]
        self.lvl = 0.0
        self.zoom = 1.0                                          # taille actuelle / taille max de la fenêtre

    def frame(self, t: float, dt: float, mode: str, target: float, status: str, sub: str,
              appear: float = 1.0) -> Image.Image:
        """appear : 0 -> 1 pendant l'apparition (la sphère émerge de l'écran), 1 -> 0 à la disparition."""
        from PIL import ImageDraw

        k = 0.55 if target > self.lvl else 0.18             # montée rapide, descente douce
        self.lvl += (target - self.lvl) * k
        e = appear * appear * (3 - 2 * appear)                   # courbe douce
        flare = 0.9 * math.sin(math.pi * min(1.0, appear)) ** 2   # éclat au milieu de l'apparition
        z = self.zoom
        size = max(8, int(self.M * z * (0.35 + 0.65 * e)))        # elle grandit depuis le centre
        orb = Image.fromarray(self.renderer.render(t, min(1.2, self.lvl + flare * 0.6), mode))
        orb = orb.resize((size, size), Image.BILINEAR)
        img = Image.new("RGB", (self.W, self.H), "black")
        img.paste(orb, (int(self.cx - size / 2), int(self.cy - size / 2)))
        d = ImageDraw.Draw(img)
        R = self.D * z / 2
        speed = 1.0 + 3.0 * self.lvl + (2.5 if mode == "thinking" else 0) + (1.0 if mode == "listening" else 0)
        for p in self.parts:
            p["a"] += p["v"] * speed * dt
            rr = R * (p["r"] + 0.03 * math.sin(t * 1.3 + p["ph"]) + 0.10 * self.lvl * math.sin(t * 7 + p["ph"]))
            rr *= 1 + 1.6 * (1 - e) * (0.6 + 0.4 * math.sin(p["ph"] * 3))   # elles arrivent de loin
            x, y = self.cx + rr * math.cos(p["a"]), self.cy + rr * math.sin(p["a"])
            pz = p["z"] * (1 + 0.8 * self.lvl) * self.scale * (0.5 + 0.5 * z)
            d.ellipse((x - pz, y - pz, x + pz, y + pz), fill=(77, 141, 255))
        glow = 0.55 + 0.25 * math.sin(t * 1.15) + 0.4 * self.lvl
        c = int(min(255, 0x3d + 120 * glow))
        y0 = self.cy + self.D * z * 0.60
        if e < 0.6:
            return img
        d.text((self.cx, y0), "J . A . R . V . I . S", fill=(c // 3, c, 255), font=self.f_title, anchor="mm")
        if status:
            d.text((self.cx, y0 + 30 * self.scale), status, fill=(60, 120, 255), font=self.f_status, anchor="mm")
        if sub:
            d.multiline_text((self.cx, y0 + 70 * self.scale), _wrap(sub, 60), fill=(170, 205, 255),
                             font=self.f_sub, anchor="ma", align="center")
        return img

    @staticmethod
    def to_bgra(img: Image.Image, fade: float) -> bytes:
        a = np.asarray(img, dtype=np.uint16)
        alpha = np.minimum(255, a.max(axis=2) * 5 // 4)               # luminosité = opacité
        f = int(max(0.0, min(1.0, fade)) * 256)
        out = np.empty(a.shape[:2] + (4,), np.uint8)
        out[..., 0] = (a[..., 2] * f) >> 8                           # B (prémultiplié)
        out[..., 1] = (a[..., 1] * f) >> 8                           # G
        out[..., 2] = (a[..., 0] * f) >> 8                           # R
        out[..., 3] = (alpha * f) >> 8                               # transparence
        return out.tobytes()


def _wrap(text: str, width: int) -> str:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return "\n".join(lines[:3])


class Orb:
    """La fenêtre de la sphère (transparente, au-dessus de tout, traversée par la souris)."""

    def __init__(self, presence: Presence | None = None) -> None:
        if os.name != "nt":
            raise RuntimeError("la sphère ne fonctionne que sous Windows")
        self.presence = presence or Presence()
        self.stop = False
        # « fond » (défaut) : juste au-dessus du bureau, derrière tes fenêtres ; « devant » : par-dessus tout
        self.position = (os.environ.get("JARVIS_SPHERE_POSITION") or "fond").strip().lower()
        self.on_top = self.position == "devant"
        self.last_sink = 0.0
        self.full = self.position == "papier"           # une seule fenêtre plein écran (noir + sphère)
        self.attached = False
        l, t, r, b = _monitor_rect((os.environ.get("JARVIS_SPHERE_ECRAN") or "principal").strip().lower())
        sw, sh = r - l, b - t
        # fenêtre prévue pour la taille max ; la taille réelle (réglable à la voix) est un zoom dedans
        st = self.presence.style
        self.max_size = max(BASE_SIZE, st.get("taille") or 0, st.get("taille_parole") or 0,
                            float(os.environ.get("JARVIS_SPHERE_TAILLE_MAX") or 0.60))
        self.max_size = min(SIZE_MAX, self.max_size)
        D = int(sh * self.max_size)
        scale = sh / 1080
        RW = int(max(D * 1.4, 1000 * scale))
        RH = int(D * 1.35 + 190 * scale)
        rx = l + (sw - RW) // 2
        ry = t + max(0, int((sh - RH) * 0.42))
        self.comp = Compositor(RW, RH, D, scale)
        self.comp.zoom = self._target_zoom("idle")
        self.fade = 0.0
        self.shown = False
        self.screen = (l, t, sw, sh)
        # fond noir quand Jarvis s'allume : « ecran » (défaut), « bureau » (vraie image Windows), « non »
        self.black_mode = (os.environ.get("JARVIS_FOND_NOIR") or "ecran").strip().lower()
        if self.full:
            self.x, self.y, self.W, self.H = l, t, sw, sh
            self.rx, self.ry = rx - l, ry - t                     # place de la sphère dans l'image plein écran
            self.buf = np.zeros((sh, sw, 4), np.uint8)
            self.buf_alpha = -1
        else:
            self.x, self.y, self.W, self.H = rx, ry, RW, RH
        self._create_window()
        if self.full:
            try:
                self.attached = self._attach_wallpaper()
            except Exception:  # noqa: BLE001
                log.warning("Fond d'écran animé refusé par Windows", exc_info=True)
            if not self.attached:
                log.info("Je place Jarvis juste au-dessus du bureau, derrière tes fenêtres.")
            else:
                log.info("Jarvis est intégré à ton fond d'écran.")
        try:
            self.black_max = max(0, min(100, int(os.environ.get("JARVIS_FOND_NOIR_OPACITE") or 100))) / 100
        except ValueError:
            self.black_max = 1.0
        self.black_hwnd = None
        self.black_alpha = -1
        self.saved_wallpaper: tuple[str, int] | None = None
        if self.black_mode == "ecran" and not self.full:
            try:
                self._create_black()
            except Exception:  # noqa: BLE001
                log.warning("Fond noir indisponible", exc_info=True)

    def _target_zoom(self, mode: str) -> float:
        st = self.presence.style
        size = st.get("taille") or BASE_SIZE
        if mode == "speaking" and st.get("taille_parole"):
            size = st["taille_parole"]
        return max(0.1, min(1.0, size / self.max_size))

    # --- Win32
    def _create_window(self) -> None:
        user32, gdi32, kernel32 = ctypes.windll.user32, ctypes.windll.gdi32, ctypes.windll.kernel32
        self.user32, self.gdi32 = user32, gdi32
        LRESULT = ctypes.c_ssize_t
        WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
        user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.DefWindowProcW.restype = LRESULT
        self._wndproc = WNDPROC(lambda h, m, w, lp: user32.DefWindowProcW(h, m, w, lp))

        class WNDCLASSEXW(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.UINT), ("style", wintypes.UINT), ("lpfnWndProc", WNDPROC),
                        ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                        ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                        ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                        ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR),
                        ("hIconSm", wintypes.HICON)]

        kernel32.GetModuleHandleW.restype = wintypes.HMODULE
        hinst = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.lpfnWndProc = self._wndproc
        wc.hInstance = hinst
        wc.lpszClassName = "JarvisSphere"
        user32.RegisterClassExW(ctypes.byref(wc))
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                           ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                           wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
        ex = 0x00080000 | 0x00000080 | 0x00000020 | 0x08000000   # calque, outil, clic au travers, sans focus
        if self.on_top:
            ex |= 0x00000008                                     # toujours devant
        self.hwnd = user32.CreateWindowExW(ex, "JarvisSphere", "Jarvis", 0x80000000,   # WS_POPUP
                                           self.x, self.y, self.W, self.H, None, None, hinst, None)
        if not self.hwnd:
            raise OSError("création de la fenêtre impossible")

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                        ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD),
                        ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
                        ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
                        ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]

        bmi = BITMAPINFOHEADER()
        bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.biWidth, bmi.biHeight = self.W, -self.H          # de haut en bas
        bmi.biPlanes, bmi.biBitCount = 1, 32
        user32.GetDC.restype = wintypes.HDC
        user32.GetDC.argtypes = [wintypes.HWND]
        gdi32.CreateCompatibleDC.restype = wintypes.HDC
        gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
        gdi32.CreateDIBSection.restype = wintypes.HBITMAP
        gdi32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.c_void_p, wintypes.UINT,
                                           ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
        gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
        self.hdc_screen = user32.GetDC(None)
        self.hdc_mem = gdi32.CreateCompatibleDC(self.hdc_screen)
        self.bits = ctypes.c_void_p()
        self.hbmp = gdi32.CreateDIBSection(self.hdc_mem, ctypes.byref(bmi), 0, ctypes.byref(self.bits), None, 0)
        gdi32.SelectObject(self.hdc_mem, self.hbmp)

        class BLEND(ctypes.Structure):
            _fields_ = [("op", ctypes.c_ubyte), ("flags", ctypes.c_ubyte),
                        ("alpha", ctypes.c_ubyte), ("fmt", ctypes.c_ubyte)]

        self.blend = BLEND(0, 0, 255, 1)                      # AC_SRC_OVER, alpha par pixel
        self.pt_dst, self.pt_src = wintypes.POINT(self.x, self.y), wintypes.POINT(0, 0)
        self.size = wintypes.SIZE(self.W, self.H)
        user32.UpdateLayeredWindow.argtypes = [wintypes.HWND, wintypes.HDC, ctypes.POINTER(wintypes.POINT),
                                               ctypes.POINTER(wintypes.SIZE), wintypes.HDC,
                                               ctypes.POINTER(wintypes.POINT), wintypes.COLORREF,
                                               ctypes.c_void_p, wintypes.DWORD]
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                        ctypes.c_int, ctypes.c_int, wintypes.UINT]
        self.msg = wintypes.MSG()

    def _push(self, data) -> None:
        if isinstance(data, np.ndarray):
            ctypes.memmove(self.bits, data.ctypes.data, data.nbytes)
        else:
            ctypes.memmove(self.bits, data, len(data))
        self.user32.UpdateLayeredWindow(self.hwnd, self.hdc_screen, None,
                                        ctypes.byref(self.size), self.hdc_mem, ctypes.byref(self.pt_src),
                                        0, ctypes.byref(self.blend), 2)          # ULW_ALPHA

    def _full_frame(self, img: Image.Image, fade: float) -> np.ndarray:
        """Image plein écran : noir partout (opacité = fondu) + la sphère à sa place."""
        f = int(max(0.0, min(1.0, fade)) * 256)
        black = self.black_mode != "non"
        a8 = (255 * f) >> 8 if black else 0
        if a8 != self.buf_alpha:
            self.buf[..., 3] = a8                                  # le noir se fond sur ton fond d'écran
            self.buf_alpha = a8
        a = np.asarray(img, dtype=np.uint16)
        h, w = a.shape[:2]
        reg = self.buf[self.ry:self.ry + h, self.rx:self.rx + w]
        reg[..., 0] = (a[..., 2] * f) >> 8
        reg[..., 1] = (a[..., 1] * f) >> 8
        reg[..., 2] = (a[..., 0] * f) >> 8
        if black:
            reg[..., 3] = a8
        else:
            reg[..., 3] = (np.minimum(255, a.max(axis=2) * 5 // 4) * f) >> 8
        return self.buf

    def _attach_wallpaper(self) -> bool:
        """Place la fenêtre DANS le fond d'écran de Windows (derrière les icônes)."""
        user32 = self.user32
        user32.FindWindowW.restype = wintypes.HWND
        user32.FindWindowExW.restype = wintypes.HWND
        user32.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
        user32.SetParent.restype = wintypes.HWND
        user32.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
        user32.SendMessageTimeoutW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
                                               wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t)]
        user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
        progman = user32.FindWindowW("Progman", None)
        if not progman:
            return False
        res = ctypes.c_size_t()
        user32.SendMessageTimeoutW(progman, 0x052C, 0xD, 0x1, 0, 1000, ctypes.byref(res))
        user32.SendMessageTimeoutW(progman, 0x052C, 0, 0, 0, 1000, ctypes.byref(res))
        found: list[int] = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def enum(hwnd, _lp):
            if user32.FindWindowExW(hwnd, None, "SHELLDLL_DefView", None):
                w = user32.FindWindowExW(None, hwnd, "WorkerW", None)
                if w:
                    found.append(w)
            return True

        user32.EnumWindows(enum, 0)
        # style fenêtre enfant
        style = user32.GetWindowLongPtrW(self.hwnd, -16)
        user32.SetWindowLongPtrW(self.hwnd, -16, (style & ~0x80000000) | 0x40000000)   # WS_CHILD
        vl, vt = user32.GetSystemMetrics(76), user32.GetSystemMetrics(77)
        x, y = self.x - vl, self.y - vt
        if found:                                               # Windows 10 / 11 classique
            user32.SetParent(self.hwnd, found[0])
            user32.SetWindowPos(self.hwnd, None, x, y, self.W, self.H, 0x0010 | 0x0004)
        else:                                                   # Windows 11 récent (24H2)
            defview = user32.FindWindowExW(progman, None, "SHELLDLL_DefView", None)
            if not defview:
                user32.SetWindowLongPtrW(self.hwnd, -16, style)
                return False
            user32.SetParent(self.hwnd, progman)
            user32.SetWindowPos(self.hwnd, defview, x, y, self.W, self.H, 0x0010)   # juste sous les icônes
        # test : la fenêtre accepte-t-elle l'image transparente ?
        self.user32.ShowWindow(self.hwnd, 4)
        ok = self.user32.UpdateLayeredWindow(self.hwnd, self.hdc_screen, None, ctypes.byref(self.size),
                                             self.hdc_mem, ctypes.byref(self.pt_src), 0,
                                             ctypes.byref(self.blend), 2)
        self.user32.ShowWindow(self.hwnd, 0)
        if not ok:                                              # refusé : on revient à une fenêtre normale
            user32.SetParent(self.hwnd, None)
            user32.SetWindowLongPtrW(self.hwnd, -16, style)
            user32.SetWindowPos(self.hwnd, wintypes.HWND(1), self.x, self.y, self.W, self.H, 0x0010)
            return False
        return True

    def _create_black(self) -> None:
        """Voile noir plein écran (au-dessus de tout, sous la sphère, traversé par la souris)."""
        user32, gdi32, kernel32 = self.user32, self.gdi32, ctypes.windll.kernel32
        gdi32.GetStockObject.restype = wintypes.HGDIOBJ
        WNDPROC = type(self._wndproc)

        class WNDCLASSEXW(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.UINT), ("style", wintypes.UINT), ("lpfnWndProc", WNDPROC),
                        ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                        ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                        ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                        ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR),
                        ("hIconSm", wintypes.HICON)]

        hinst = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.lpfnWndProc = self._wndproc
        wc.hInstance = hinst
        wc.hbrBackground = gdi32.GetStockObject(4)                            # pinceau noir
        wc.lpszClassName = "JarvisNoir"
        user32.RegisterClassExW(ctypes.byref(wc))
        l, t, w, h = self.screen
        ex = 0x00080000 | 0x00000080 | 0x00000020 | 0x08000000 | (0x00000008 if self.on_top else 0)
        self.black_hwnd = user32.CreateWindowExW(ex, "JarvisNoir", "Jarvis fond", 0x80000000,
                                                 l, t, w, h, None, None, hinst, None)
        user32.SetLayeredWindowAttributes.argtypes = [wintypes.HWND, wintypes.COLORREF, ctypes.c_ubyte,
                                                      wintypes.DWORD]
        user32.SetLayeredWindowAttributes(self.black_hwnd, 0, 0, 2)          # LWA_ALPHA, invisible au départ

    def _set_black(self, fade: float) -> None:
        if self.full and self.black_mode != "bureau":
            return
        if self.black_mode == "bureau":
            self._desktop_black(fade > 0)
            return
        if not self.black_hwnd:
            return
        e = fade * fade * (3 - 2 * fade)
        alpha = int(255 * self.black_max * e)
        if alpha == self.black_alpha:
            return
        if alpha > 0 and self.black_alpha <= 0:
            self.user32.ShowWindow(self.black_hwnd, 4)
            self._zorder()
        self.user32.SetLayeredWindowAttributes(self.black_hwnd, 0, max(0, alpha), 2)
        if alpha <= 0:
            self.user32.ShowWindow(self.black_hwnd, 0)
        self.black_alpha = alpha

    def _desktop_black(self, on: bool) -> None:
        """Mode « bureau » : le vrai fond d'écran Windows passe au noir, puis revient."""
        user32 = self.user32
        if on and self.saved_wallpaper is None:
            buf = ctypes.create_unicode_buffer(520)
            user32.SystemParametersInfoW(0x0073, 520, buf, 0)                 # fond actuel
            self.saved_wallpaper = (buf.value, user32.GetSysColor(1))
            elems, cols = (ctypes.c_int * 1)(1), (wintypes.COLORREF * 1)(0)
            user32.SetSysColors(1, elems, cols)                              # couleur du bureau : noir
            user32.SystemParametersInfoW(0x0014, 0, "", 0x02)                # pas d'image
        elif not on and self.saved_wallpaper is not None:
            path, color = self.saved_wallpaper
            elems, cols = (ctypes.c_int * 1)(1), (wintypes.COLORREF * 1)(color)
            user32.SetSysColors(1, elems, cols)
            user32.SystemParametersInfoW(0x0014, 0, path, 0x02)
            self.saved_wallpaper = None

    def _zorder(self) -> None:
        """Mode fond : le noir tout au fond, la sphère juste au-dessus, tes fenêtres devant.
        Mode devant : le noir puis la sphère au-dessus de tout."""
        flags = 0x0001 | 0x0002 | 0x0010                                         # sans bouger, sans focus
        sw = self.user32.SetWindowPos
        if self.attached:
            self.last_sink = time.monotonic()
            return
        if self.on_top:
            if self.black_hwnd:
                sw(self.black_hwnd, wintypes.HWND(-1), 0, 0, 0, 0, flags)
            sw(self.hwnd, wintypes.HWND(-1), 0, 0, 0, 0, flags)
        else:
            sw(self.hwnd, wintypes.HWND(1), 0, 0, 0, 0, flags)                  # HWND_BOTTOM
            if self.black_hwnd:
                sw(self.black_hwnd, wintypes.HWND(1), 0, 0, 0, 0, flags)
        self.last_sink = time.monotonic()

    def _show(self, on: bool) -> None:
        if on and not self.shown:
            self.user32.ShowWindow(self.hwnd, 4)                                 # sans voler le focus
            self._zorder()
        elif not on and self.shown:
            self.user32.ShowWindow(self.hwnd, 0)
        self.shown = on

    def _pump(self) -> None:
        while self.user32.PeekMessageW(ctypes.byref(self.msg), None, 0, 0, 1):
            self.user32.TranslateMessage(ctypes.byref(self.msg))
            self.user32.DispatchMessageW(ctypes.byref(self.msg))

    # --- boucle
    def run(self) -> None:
        t0 = last = time.monotonic()
        try:
            while not self.stop:
                start = time.monotonic()
                dt, last = start - last, start
                self._pump()
                p = self.presence
                mode, target = p.level(start)
                with p.lock:
                    want = (p.pinned or mode != "idle" or (start - p.last_active) < LINGER_S
                            or start < p.pinned_until)
                    status, sub = p.status, p.subtitle
                    nb = p.style.get("fond_noir")
                if nb is not None:
                    self.black_max = nb / 100                                  # réglé à la voix
                tz = self._target_zoom(mode)
                self.comp.zoom += (tz - self.comp.zoom) * min(1.0, dt * 5)     # changement de taille en douceur
                if want:
                    self.fade = min(1.0, self.fade + dt / FADE_IN_S)
                else:
                    self.fade = max(0.0, self.fade - dt / FADE_OUT_S)
                self._set_black(self.fade)
                if self.fade <= 0.0:
                    self._show(False)
                    time.sleep(0.05)                                            # repos : ne consomme rien
                    continue
                try:
                    img = self.comp.frame(start - t0, dt, mode, target, status, sub, appear=self.fade)
                    if self.full:
                        e = self.fade * self.fade * (3 - 2 * self.fade)
                        self._push(self._full_frame(img, e))
                    else:
                        self._push(Compositor.to_bgra(img, min(1.0, self.fade * 1.6)))
                    self._show(True)
                    if not self.on_top and start - self.last_sink > 1.0:
                        self._zorder()                       # reste derrière les fenêtres, même après un clic
                except Exception:  # noqa: BLE001
                    log.exception("Erreur d'animation de la sphère")
                    time.sleep(0.5)
                time.sleep(max(0.001, 1 / FPS - (time.monotonic() - start)))
        finally:
            self._show(False)
            self._set_black(0.0)                       # on rend toujours l'écran / le fond d'origine
            if self.attached:                          # Windows redessine ton fond d'écran habituel
                try:
                    buf = ctypes.create_unicode_buffer(520)
                    self.user32.SystemParametersInfoW(0x0073, 520, buf, 0)
                    self.user32.SystemParametersInfoW(0x0014, 0, buf.value, 0)
                except Exception:  # noqa: BLE001
                    pass

    def request_close(self) -> None:
        self.stop = True
