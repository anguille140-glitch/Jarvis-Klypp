"""Interface HUD futuriste de Jarvis sur un ou deux écrans (Tkinter).

- Fenêtres OPAQUES plein écran (une par écran) : on ne voit plus à travers.
- Un rond « noyau » quitte l'écran de gauche et traverse jusqu'à l'écran principal,
  comme un chargement : rail de progression, pourcentage, traînée, arrivée en fanfare.
- Tout s'anime en continu, puis l'ensemble s'efface en fondu à la fin du réveil.
- Pour utiliser TON rond : place un fichier  rond.png  dans le dossier du projet.
"""
from __future__ import annotations

import ctypes
import logging
import math
import os
import queue
import random
import threading
import time
import tkinter as tk
from collections import deque
from pathlib import Path

BG = "#02090d"          # fond opaque
CYAN = "#00e5ff"
CYAN_DIM = "#0b7a8c"
CYAN_DARK = "#073b44"
GRID = "#06222a"
ORANGE = "#ff9f1c"
WHITE = "#d6fbff"
TRAIL = ["#00e5ff", "#00bcd4", "#0097a7", "#00707e", "#0a4d58", "#073b44"]

# Calé sur le son de démarrage (jarvis.py, make_boot_sound) : la montée dure 1,3 s puis le carillon.
# Le chargement part avec le son et atteint 100 % pile sur le carillon.
T_DEPART = 0.0                      # le rond quitte l'écran de gauche dès le début du son
T_TRAVEL = 1.3                      # durée de la traversée = durée de la montée du son
T_ARRIVE = T_DEPART + T_TRAVEL
LABEL_HOLD_S = 0.8                  # « 100 % / NOYAU INSTALLÉ » reste ce temps, puis laisse la place au titre
try:                                # durée de l'intro (JARVIS_INTRO_DUREE dans .env, en secondes)
    INTRO_S = float(os.environ.get("JARVIS_INTRO_DUREE") or 8)
except ValueError:
    INTRO_S = 8.0
MIN_VISIBLE_S = max(T_ARRIVE + 3.0, INTRO_S)   # l'intro reste affichée au moins ce temps
LINGER_S = 1.5                      # temps gardé après la fin du réveil
FADE_S = 1.4                        # durée du fondu
MAX_S = MIN_VISIBLE_S + 12.0        # sécurité : l'intro se ferme toujours, quoi qu'il arrive
def _env_int(name: str, default: int) -> int:
    try:
        return max(10, min(144, int((os.environ.get(name) or "").strip() or default)))
    except ValueError:
        return default


FPS = _env_int("JARVIS_FPS", 60)    # images par seconde (mets JARVIS_FPS=30 dans .env si ça saccade)
RING_IMAGE = Path(__file__).resolve().parent / "rond.png"      # ton rond fixe (secours)
RING_DIR = Path(__file__).resolve().parent / "rond_anim"       # images de l'animation en vague
ANIM_FPS = 24                                                  # vitesse de la vague

TITLE = "J.A.R.V.I.S"

log = logging.getLogger("jarvis")


def _mix(c1: str, c2: str, k: float) -> str:
    k = min(1.0, max(0.0, k))
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(a[i] + (b[i] - a[i]) * k) for i in range(3))


class _Smooth:
    """Valeur qui glisse doucement vers des cibles aléatoires (jauges animées)."""

    def __init__(self, lo: float = 0.2, hi: float = 0.9) -> None:
        self.lo, self.hi = lo, hi
        self.v = random.uniform(lo, hi)
        self.tg = self.v
        self.next = 0.0

    def step(self, t: float) -> float:
        if t >= self.next:
            self.tg = random.uniform(self.lo, self.hi)
            self.next = t + random.uniform(0.6, 1.8)
        self.v += (self.tg - self.v) * 0.12
        return self.v


class _Panel:
    """Un écran : une fenêtre opaque et tous ses éléments animés."""

    def __init__(self, win, rect, origin, primary: bool, user: str, hud: "Hud") -> None:
        l, t, r, b = rect
        self.win, self.hud = win, hud
        self.w, self.h = r - l, b - t
        self.ox, self.oy = origin           # position de cet écran dans le « grand bureau »
        self.s = max(0.6, min(1.3, min(self.w / 1920, self.h / 1080)))
        self.primary, self.user = primary, user
        self.f = 0
        self.dyn: list = []
        self.logs: list[int] = []
        self.status: dict[str, tuple[int, str]] = {}

        win.overrideredirect(True)
        win.geometry(f"{self.w}x{self.h}+{l}+{t}")
        win.configure(bg=BG)
        try:
            win.attributes("-topmost", True)
        except tk.TclError:
            pass
        self.cv = tk.Canvas(win, width=self.w, height=self.h, bg=BG, highlightthickness=0)
        self.cv.pack()

        self.m = int(50 * self.s)
        self.cx, self.cy = self.w // 2, int(self.h * 0.42)
        self._grid()
        self._frame()
        if primary:
            self._build_main()
        else:
            self._build_side()
        self._build_traveler()

    # ----------------------------------------------------------------- outils
    def _every(self, n: int) -> bool:
        """Vrai une image sur n (calé sur 30 images/s, donc proportionnel au nombre d'images/s)."""
        return self.f % max(1, round(n * FPS / 30)) == 0

    def _font(self, size: float, bold: bool = False) -> tuple:
        return ("Consolas", -max(9, int(size * 1.35 * self.s)), "bold" if bold else "normal")

    @staticmethod
    def _flat(points) -> list[float]:
        return [c for p in points for c in p]

    # ------------------------------------------------------------ décor commun
    def _grid(self) -> None:
        step = max(40, int(80 * self.s))
        for x in range(0, self.w, step):
            self.cv.create_line(x, 0, x, self.h, fill=GRID)
        for y in range(0, self.h, step):
            self.cv.create_line(0, y, self.w, y, fill=GRID)

    def _frame(self) -> None:
        cv, s, m, w, h = self.cv, self.s, self.m, self.w, self.h
        ln = int(90 * s)
        for x, y, dx, dy in ((m, m, 1, 1), (w - m, m, -1, 1), (m, h - m, 1, -1), (w - m, h - m, -1, -1)):
            cv.create_line(x, y, x + dx * ln, y, fill=CYAN, width=3)
            cv.create_line(x, y, x, y + dy * ln, fill=CYAN, width=3)
        for y in (m + int(46 * s), h - m - int(40 * s)):
            cv.create_line(m, y, w - m, y, fill=CYAN_DIM)
            for x in range(m, w - m, max(20, int(40 * s))):
                cv.create_line(x, y, x, y + int(8 * s), fill=CYAN_DIM)
        left_t = "JARVIS // PROTOCOLE DE RÉVEIL" if self.primary else "SECTEUR GAUCHE // COMMUNICATIONS"
        bl = "ÉCOUTE AUDIO : ACTIVE" if self.primary else "RÉSEAU : EN LIGNE"
        br = "LIAISON : STABLE" if self.primary else "SYNCHRO : 100%"
        cv.create_text(m + 16 * s, m + 14 * s, anchor="nw", text=left_t, fill=CYAN_DIM, font=self._font(13))
        cv.create_text(m + 16 * s, h - m - 14 * s, anchor="sw", text=bl, fill=CYAN_DIM, font=self._font(13))
        cv.create_text(w - m - 16 * s, h - m - 14 * s, anchor="se", text=br, fill=CYAN_DIM, font=self._font(13))
        clock = cv.create_text(w - m - 16 * s, m + 10 * s, anchor="ne", text="", fill=CYAN, font=self._font(20, True))
        flux = cv.create_text(w // 2, m + 22 * s, text="", fill=CYAN_DIM, font=self._font(12))
        scan = cv.create_line(0, 0, w, 0, fill=CYAN_DARK, width=2)

        def upd(t: float) -> None:
            if self._every(10):
                cv.itemconfigure(clock, text=time.strftime("%H:%M:%S"))
            if self._every(6):
                cv.itemconfigure(flux, text=f"FLUX 0x{random.getrandbits(32):08X}  //  SYNC {random.randint(96, 100)}%")
            y = (t * 240 * s) % h
            cv.coords(scan, 0, y, w, y)

        self.dyn.append(upd)

    # ----------------------------------------------------- éléments réutilisables
    def _ticks(self, cx: float, cy: float, r_in: float, r_out: float) -> None:
        for i in range(72):
            a = math.radians(i * 5)
            long_tick = i % 6 == 0
            r2 = r_out + (10 * self.s if long_tick else 0)
            self.cv.create_line(
                cx + r_in * math.cos(a), cy - r_in * math.sin(a),
                cx + r2 * math.cos(a), cy - r2 * math.sin(a),
                fill=CYAN_DIM if long_tick else CYAN_DARK, width=2 if long_tick else 1,
            )

    def _rings(self, cx: float, cy: float, specs: list[tuple]) -> None:
        s = self.s
        arcs: list[tuple[int, float, float]] = []
        for radius, width, color, speed, n, ext in specs:
            rr = radius * s
            for i in range(n):
                base = i * 360 / n
                item = self.cv.create_arc(cx - rr, cy - rr, cx + rr, cy + rr, start=base, extent=ext,
                                          style="arc", outline=color, width=max(1, int(width * s)))
                arcs.append((item, base, speed))

        def upd(t: float) -> None:
            for item, base, speed in arcs:
                self.cv.itemconfigure(item, start=(base + speed * t) % 360)

        self.dyn.append(upd)

    def _spectrum(self, x0: float, x1: float, ybase: float, maxh: float, n: int) -> None:
        cv = self.cv
        step = (x1 - x0) / n
        bars = [cv.create_rectangle(x0 + i * step, ybase, x0 + i * step + step * 0.62, ybase,
                                    fill=CYAN if i % 4 else ORANGE, outline="") for i in range(n)]

        def upd(t: float) -> None:
            if not self._every(2):
                return
            for i, bar in enumerate(bars):
                v = abs(math.sin(t * 3.1 + i * 0.55) * math.cos(t * 1.7 + i * 0.31))
                v = 0.12 + 0.88 * v * (0.6 + 0.4 * math.sin(t * 0.9 + i * 0.1))
                cv.coords(bar, x0 + i * step, ybase - maxh * v, x0 + i * step + step * 0.62, ybase)

        self.dyn.append(upd)

    def _graph(self, x: float, y: float, w: float, h: float, title: str, color: str = CYAN) -> None:
        cv, s = self.cv, self.s
        w, h = w * s, h * s
        cv.create_text(x, y - 12 * s, anchor="w", text=title, fill=CYAN_DIM, font=self._font(11))
        cv.create_rectangle(x, y, x + w, y + h, outline=CYAN_DIM)
        for k in (1, 2, 3):
            cv.create_line(x, y + h * k / 4, x + w, y + h * k / 4, fill=CYAN_DARK, dash=(2, 4))
        n = 60
        vals = [0.5] * n
        line = cv.create_line(*self._flat((x + w * i / (n - 1), y + h * 0.5) for i in range(n)),
                              fill=color, width=2)
        sm = _Smooth(0.1, 0.9)

        def upd(t: float) -> None:
            vals.append(sm.step(t) + random.uniform(-0.05, 0.05))
            vals.pop(0)
            if not self._every(2):
                return
            pts = ((x + w * i / (n - 1), y + h * (1 - min(max(v, 0.03), 0.97))) for i, v in enumerate(vals))
            cv.coords(line, *self._flat(pts))

        self.dyn.append(upd)

    def _hbars(self, x: float, y: float, names: list[str], width: float) -> None:
        cv, s = self.cv, self.s
        rows = []
        for i, name in enumerate(names):
            yy = y + i * 34 * s
            cv.create_text(x, yy, anchor="w", text=name, fill=CYAN_DIM, font=self._font(12))
            bx0 = x + 140 * s
            bx1 = bx0 + width * s
            cv.create_rectangle(bx0, yy - 6 * s, bx1, yy + 6 * s, outline=CYAN_DIM)
            fill = cv.create_rectangle(bx0, yy - 6 * s, bx0, yy + 6 * s, fill=CYAN, outline="")
            pct = cv.create_text(bx1 + 10 * s, yy, anchor="w", text="", fill=CYAN, font=self._font(12))
            rows.append((bx0, bx1, yy, fill, pct, _Smooth(0.15, 0.95)))

        def upd(t: float) -> None:
            for bx0, bx1, yy, fill, pct, sm in rows:
                v = sm.step(t)
                if self._every(2):
                    cv.coords(fill, bx0, yy - 6 * s, bx0 + (bx1 - bx0) * v, yy + 6 * s)
                if self._every(8):
                    cv.itemconfigure(pct, text=f"{int(v * 100):>3}%")

        self.dyn.append(upd)

    def _gauges(self, x: float, y: float, r: float, names: list[str], spacing: float) -> None:
        cv, s = self.cv, self.s
        rr = r * s
        width = max(3, int(7 * s))
        gauges = []
        for i, name in enumerate(names):
            gx = x + i * spacing * s
            cv.create_arc(gx - rr, y - rr, gx + rr, y + rr, start=90, extent=359.9, style="arc",
                          outline=CYAN_DARK, width=width)
            fg = cv.create_arc(gx - rr, y - rr, gx + rr, y + rr, start=90, extent=-90, style="arc",
                               outline=CYAN if i % 2 == 0 else ORANGE, width=width)
            txt = cv.create_text(gx, y, text="", fill=WHITE, font=self._font(15, True))
            cv.create_text(gx, y + rr + 18 * s, text=name, fill=CYAN_DIM, font=self._font(11))
            gauges.append((fg, txt, _Smooth(0.3, 0.98)))

        def upd(t: float) -> None:
            for fg, txt, sm in gauges:
                v = sm.step(t)
                if self._every(2):
                    cv.itemconfigure(fg, extent=-max(2.0, v * 359.0))
                if self._every(8):
                    cv.itemconfigure(txt, text=f"{int(v * 100)}")

        self.dyn.append(upd)

    def _readouts(self, x: float, y: float, templates: list[str]) -> None:
        cv, s = self.cv, self.s
        items = [cv.create_text(x, y + i * 26 * s, anchor="w", text="", fill=CYAN_DIM, font=self._font(12))
                 for i in range(len(templates))]

        def upd(t: float) -> None:
            if not self._every(9):
                return
            for item, tpl in zip(items, templates):
                cv.itemconfigure(item, text=tpl.format(a=random.randint(10, 99), b=random.randint(100, 999),
                                                       c=random.random() * 9, h=random.getrandbits(24)))

        self.dyn.append(upd)

    def _faceit_block(self, x: float, y: float) -> None:
        """Affiche l'elo FACEIT (compteur animé), le niveau (10 barres) et quelques statistiques."""
        cv, s, hud = self.cv, self.s, self.hud
        head = cv.create_text(x, y, anchor="w", text="// FACEIT", fill=ORANGE, font=self._font(15, True))
        cv.create_text(x, y + 34 * s, anchor="w", text="ELO", fill=CYAN_DIM, font=self._font(13))
        elo = cv.create_text(x, y + 76 * s, anchor="w", text="----", fill=CYAN, font=self._font(46, True))
        segs = []
        for i in range(10):
            sx = x + i * 40 * s
            segs.append(cv.create_rectangle(sx, y + 126 * s, sx + 32 * s, y + 140 * s, outline=CYAN_DIM, fill=""))
        lvl = cv.create_text(x, y + 164 * s, anchor="w", text="", fill=WHITE, font=self._font(14, True))
        stats = cv.create_text(x, y + 192 * s, anchor="w", text="", fill=CYAN_DIM, font=self._font(12))
        st = {"shown": 0.0, "txt": "", "level": -1, "info": ""}

        def upd(t: float) -> None:
            d = hud.faceit or {}
            nick = (hud.faceit_nick or "").upper()
            if self._every(15):
                cv.itemconfigure(head, text=f"// FACEIT  ·  {nick}" if nick else "// FACEIT")
            target = d.get("elo")
            if target:
                st["shown"] += (target - st["shown"]) * 0.06
                if abs(target - st["shown"]) < 1:
                    st["shown"] = float(target)
                txt = f"{int(round(st['shown'])):,}".replace(",", " ")
            else:
                txt = "----"
            if txt != st["txt"]:
                st["txt"] = txt
                cv.itemconfigure(elo, text=txt)
            level = int(d.get("level") or 0)
            if level != st["level"]:
                st["level"] = level
                for i, seg in enumerate(segs):
                    cv.itemconfigure(seg, fill=(ORANGE if i < level else ""),
                                     outline=(ORANGE if i < level else CYAN_DIM))
                cv.itemconfigure(lvl, text=f"NIVEAU {level}" if level else "")
            parts = []
            if d.get("kd"):
                parts.append(f"K/D {d['kd']}")
            if d.get("winrate"):
                parts.append(f"VICTOIRES {d['winrate']}%")
            if d.get("matches"):
                parts.append(f"PARTIES {d['matches']}")
            info = "   ".join(parts) or (d.get("note") or ("CHARGEMENT..." if not target else ""))
            if info != st["info"]:
                st["info"] = info
                cv.itemconfigure(stats, text=info)

        self.dyn.append(upd)

    def _rain(self, x: float, cols: int) -> None:
        cv, s = self.cv, self.s
        top = self.m + 64 * s
        rows = max(8, int((self.h - 2 * self.m - 150 * s) / (16 * s)))
        streams = []
        for c in range(cols):
            lines = [f"{random.randrange(256):02X}" for _ in range(rows)]
            item = cv.create_text(x + c * 34 * s, top, anchor="nw", text="\n".join(lines),
                                  fill=CYAN_DARK if c % 2 == 0 else GRID, font=self._font(10))
            streams.append((lines, item))

        def upd(t: float) -> None:
            if not self._every(4):
                return
            for lines, item in streams:
                lines.insert(0, f"{random.randrange(256):02X}")
                lines.pop()
                cv.itemconfigure(item, text="\n".join(lines))

        self.dyn.append(upd)

    def _radar(self, cx: float, cy: float, radius: float) -> None:
        cv, s = self.cv, self.s
        R = radius * s
        for k, col in ((1.0, CYAN_DIM), (0.66, CYAN_DARK), (0.33, CYAN_DARK)):
            cv.create_oval(cx - R * k, cy - R * k, cx + R * k, cy + R * k, outline=col, width=2 if k == 1.0 else 1)
        cv.create_line(cx - R, cy, cx + R, cy, fill=CYAN_DARK)
        cv.create_line(cx, cy - R, cx, cy + R, fill=CYAN_DARK)
        trail = [cv.create_line(cx, cy, cx, cy - R, fill=TRAIL[i], width=3 if i == 0 else 2) for i in range(len(TRAIL))]
        blips = []
        for _ in range(8):
            a = random.uniform(0, 360)
            rad = random.uniform(0.2, 0.92) * R
            x, y = cx + rad * math.cos(math.radians(a)), cy - rad * math.sin(math.radians(a))
            blips.append((a, cv.create_oval(x - 4 * s, y - 4 * s, x + 4 * s, y + 4 * s, fill=CYAN_DARK, outline="")))

        def upd(t: float) -> None:
            ang = (t * 80) % 360
            for i, line in enumerate(trail):
                a = math.radians(ang - i * 7)
                cv.coords(line, cx, cy, cx + R * math.cos(a), cy - R * math.sin(a))
            if self._every(2):
                for a, blip in blips:
                    diff = (ang - a) % 360
                    cv.itemconfigure(blip, fill=ORANGE if diff < 40 else (CYAN_DIM if diff < 160 else CYAN_DARK))

        self.dyn.append(upd)

    def _wave(self, x0: float, x1: float, yc: float, amp: float, color: str, phase: float) -> None:
        cv = self.cv
        n = 100
        line = cv.create_line(*self._flat((x0 + (x1 - x0) * i / (n - 1), yc) for i in range(n)), fill=color, width=2)

        def upd(t: float) -> None:
            if not self._every(2):
                return
            pts = []
            for i in range(n):
                env = max(0.0, math.sin(math.pi * i / (n - 1))) ** 0.7
                v = 0.6 * math.sin(0.11 * i + t * 5 + phase) + 0.4 * math.sin(0.27 * i - t * 3.1 + phase)
                pts.append((x0 + (x1 - x0) * i / (n - 1), yc - amp * env * v))
            cv.coords(line, *self._flat(pts))

        self.dyn.append(upd)

    # --------------------------------------------------------- écran principal
    def _build_main(self) -> None:
        cv, s, m, w, h, cx, cy = self.cv, self.s, self.m, self.w, self.h, self.cx, self.cy
        self._ticks(cx, cy, 248 * s, 256 * s)
        self._rings(cx, cy, [(232, 3, CYAN, 55, 3, 70), (200, 6, CYAN_DIM, -40, 4, 48),
                             (162, 2, CYAN, 90, 2, 120), (126, 1, CYAN_DIM, -70, 6, 28),
                             (276, 1, CYAN_DIM, 25, 8, 20)])
        center_txt = cv.create_text(cx, cy + 300 * s, text="", fill=CYAN_DIM, font=self._font(13))
        title = cv.create_text(cx, cy + 336 * s, text="", fill=CYAN, font=self._font(40, True))
        sub_text = f"BIENVENUE  {self.user}"
        subtitle = cv.create_text(cx, cy + 384 * s, text="", fill=ORANGE, font=self._font(18, True))

        last_typed = [(-1, -1)]

        def upd_main(t: float) -> None:
            if t < T_ARRIVE:
                txt = "RÉCEPTION DU NOYAU..." if int(t * 2) % 2 == 0 else ""
            else:
                txt = "NOYAU EN LIGNE"
            if self._every(3):
                cv.itemconfigure(center_txt, text=txt)
            t_title = t - T_ARRIVE - LABEL_HOLD_S                 # le titre s'écrit une fois l'étiquette partie
            n = min(len(TITLE), int(max(0.0, t_title) * 9))
            k = min(len(sub_text), int(max(0.0, t_title - 1.3) * 14))
            if (n, k) != last_typed[0]:
                last_typed[0] = (n, k)
                cv.itemconfigure(title, text=" ".join(TITLE[:n]))
                cv.itemconfigure(subtitle, text=sub_text[:k])

        self.dyn.append(upd_main)

        # journal de démarrage (haut gauche) + ressources
        self.log_x = m + int(120 * s)
        self.log_y0 = int(cy - 300 * s)
        cv.create_text(self.log_x, self.log_y0 - 36 * s, anchor="w", text="// INITIALISATION",
                       fill=ORANGE, font=self._font(15, True))
        self._hbars(self.log_x, cy + 150 * s, ["PROCESSEUR", "MÉMOIRE", "RÉSEAU", "MICRO", "GRAPHIQUE"], 250)

        # colonne de droite
        rx = w - m - int(120 * s) - int(430 * s)
        self._graph(rx, cy - 300 * s, 430, 95, "FLUX DE DONNÉES")
        self._graph(rx, cy - 170 * s, 430, 95, "ACTIVITÉ SYSTÈME", ORANGE)
        self._gauges(rx + 60 * s, cy + 130 * s, 46, ["CHARGE", "TEMP.", "ÉNERGIE"], 150)
        self._faceit_block(rx, cy + 240 * s)
        # bas : spectre audio
        self._spectrum(cx - 430 * s, cx + 430 * s, h - m - 70 * s, 80 * s, 56)
        # flux de données sur les bords
        self._rain(m + 10 * s, 2)
        self._rain(w - m - 10 * s - 34 * s, 2)

    # ----------------------------------------------------------- écran de gauche
    def _build_side(self) -> None:
        cv, s, m, w, h, cx, cy = self.cv, self.s, self.m, self.w, self.h, self.cx, self.cy
        self._ticks(cx, cy, 248 * s, 256 * s)
        self._rings(cx, cy, [(232, 3, CYAN, -35, 3, 70), (200, 6, CYAN_DIM, 28, 4, 48),
                             (162, 2, CYAN, -60, 2, 120), (126, 1, CYAN_DIM, 50, 6, 28),
                             (276, 1, CYAN_DIM, -18, 8, 20)])
        cv.create_text(cx, cy + 300 * s, text="UNITÉ CENTRALE", fill=CYAN_DIM, font=self._font(13))
        state = cv.create_text(cx, cy + 336 * s, text="", fill=ORANGE, font=self._font(18, True))

        def upd_side(t: float) -> None:
            if not self._every(3):
                return
            txt = "NOYAU PRÊT" if t < T_DEPART else ("NOYAU EN TRANSIT" if t < T_ARRIVE else "NOYAU TRANSFÉRÉ")
            cv.itemconfigure(state, text=txt)

        self.dyn.append(upd_side)

        lx = m + int(120 * s)
        ly = int(cy - 300 * s)
        cv.create_text(lx, ly - 36 * s, anchor="w", text="// LIAISONS", fill=ORANGE, font=self._font(15, True))
        for i, name in enumerate(["Discord", "FACEIT"]):
            item = cv.create_text(lx, ly + i * 34 * s, anchor="w", text=f"{name.upper():<10}........ EN ATTENTE",
                                  fill=CYAN_DIM, font=self._font(14))
            self.status[name.lower()] = (item, name.upper())
        self._hbars(lx, cy + 150 * s, ["SIGNAL", "BANDE PASS.", "CHIFFREMENT", "LATENCE"], 230)
        self._radar(lx + 120 * s, cy + 400 * s, 90)

        rx = w - m - int(120 * s) - int(430 * s)
        self._graph(rx, cy - 300 * s, 430, 95, "TRAFIC ENTRANT", ORANGE)
        self._graph(rx, cy - 170 * s, 430, 95, "TRAFIC SORTANT")
        self._gauges(rx + 60 * s, cy + 130 * s, 46, ["SIGNAL", "GAIN", "BRUIT"], 150)
        self._readouts(rx, cy + 235 * s, ["CANAL      {a:02d}", "FRÉQUENCE  {c:.2f} MHz", "ADRESSE    0x{h:06X}"])

        yc = h - m - 95 * s
        self._wave(m + 450 * s, w - m - 150 * s, yc, 42 * s, CYAN, 0.0)
        self._wave(m + 450 * s, w - m - 150 * s, yc, 30 * s, ORANGE, 1.7)
        self._rain(m + 10 * s, 2)
        self._rain(w - m - 10 * s - 34 * s, 2)

    # ------------------------------------------------- le rond qui traverse les écrans
    def _build_traveler(self) -> None:
        cv, hud, s = self.cv, self.hud, self.s
        R = hud.R
        x1, y1 = hud.xs - self.ox, hud.ys - self.oy
        x2, y2 = hud.xe - self.ox, hud.ye - self.oy

        # rail de chargement qui court d'un écran à l'autre
        cv.create_line(x1, y1, x2, y2, fill=CYAN_DARK, width=3)
        n_ticks = 60
        for i in range(n_ticks + 1):
            k = i / n_ticks
            tx, ty = x1 + (x2 - x1) * k, y1 + (y2 - y1) * k
            big = i % 5 == 0
            cv.create_line(tx, ty - (14 if big else 7) * s, tx, ty + (14 if big else 7) * s,
                           fill=CYAN_DIM if big else CYAN_DARK)
        self.rail_fill = cv.create_line(x1, y1, x1 + 0.1, y1, fill=CYAN, width=3)

        # traînée (images fantômes)
        self.ghosts = [cv.create_oval(0, 0, 1, 1, outline=_mix(CYAN, BG, 0.25 + 0.14 * k), width=2)
                       for k in range(5)]
        # onde d'arrivée
        self.burst = cv.create_oval(0, 0, 1, 1, outline=CYAN, width=4, state="hidden")

        # le rond lui-même
        self.arcs: list[tuple[int, float, float, float]] = []
        self.img_item = None
        if hud.ring_img is not None:
            self.img_item = cv.create_image(0, 0, image=hud.ring_img)
        else:
            for rad, width, color, speed, n, ext in ((1.00, 4, CYAN, 120, 3, 70), (0.80, 6, CYAN_DIM, -90, 4, 48),
                                                     (0.60, 2, CYAN, 160, 2, 120)):
                for i in range(n):
                    base = i * 360 / n
                    item = cv.create_arc(0, 0, 1, 1, start=base, extent=ext, style="arc", outline=color,
                                         width=max(1, int(width * s)))
                    self.arcs.append((item, base, speed, rad))
            self.core = cv.create_oval(0, 0, 1, 1, outline=CYAN, width=2)
            self.core_in = cv.create_oval(0, 0, 1, 1, fill=CYAN, outline="")
        self.prog = cv.create_arc(0, 0, 1, 1, start=90, extent=-1, style="arc", outline=ORANGE,
                                  width=max(3, int(6 * s)))
        self.pct = cv.create_text(0, 0, text="0%", fill=WHITE, font=self._font(30, True))
        self.cap = cv.create_text(0, 0, text="CHARGEMENT", fill=CYAN_DIM, font=self._font(12))
        self.trav_items = (self.ghosts + [self.prog, self.pct, self.cap]
                           + [a[0] for a in self.arcs]
                           + ([self.img_item] if self.img_item else [])
                           + ([] if self.img_item else [self.core, self.core_in]))
        self.trav_visible: bool | None = None
        self.frame_idx = -1
        self.dyn.append(self._update_traveler)

    def _update_traveler(self, t: float) -> None:
        cv, hud, s = self.cv, self.hud, self.s
        R = hud.R
        X, Y, e = hud.position(t)
        lx, ly = X - self.ox, Y - self.oy
        # rail rempli : suit l'avancement, visible sur chaque écran même quand le rond est parti
        rx1, ry1 = hud.xs - self.ox, hud.ys - self.oy
        rx2, ry2 = hud.xe - self.ox, hud.ye - self.oy
        cv.coords(self.rail_fill, rx1, ry1, rx1 + max(0.1, (rx2 - rx1) * e), ry1 + (ry2 - ry1) * e)
        margin = R * 1.7
        visible = -margin <= lx <= self.w + margin and -margin <= ly <= self.h + margin
        if visible != self.trav_visible:
            self.trav_visible = visible
            for it in self.trav_items:
                cv.itemconfigure(it, state="normal" if visible else "hidden")
            if visible:
                cv.itemconfigure(self.burst, state="hidden")
        if not visible:
            return

        # traînée
        hist = hud.hist
        for k, g in enumerate(self.ghosts):
            idx = len(hist) - 1 - 3 * (k + 1)
            gx, gy = (hist[idx] if idx >= 0 else (X, Y))
            r = R * (1.0 - 0.09 * (k + 1))
            cv.coords(g, gx - self.ox - r, gy - self.oy - r, gx - self.ox + r, gy - self.oy + r)

        # rond
        if self.img_item is not None:
            cv.coords(self.img_item, lx, ly)
            frames = hud.ring_frames
            if len(frames) > 1:                              # la vague : on change d'image en boucle
                idx = int(t * ANIM_FPS) % len(frames)
                if idx != self.frame_idx:
                    self.frame_idx = idx
                    cv.itemconfigure(self.img_item, image=frames[idx])
        else:
            for item, base, speed, rad in self.arcs:
                rr = R * rad
                cv.coords(item, lx - rr, ly - rr, lx + rr, ly + rr)
                cv.itemconfigure(item, start=(base + speed * t) % 360)
            pulse = 1 + 0.08 * math.sin(t * 5)
            r1, r2 = R * 0.30 * pulse, R * 0.08
            cv.coords(self.core, lx - r1, ly - r1, lx + r1, ly + r1)
            cv.coords(self.core_in, lx - r2, ly - r2, lx + r2, ly + r2)
        pr = R * 1.2
        cv.coords(self.prog, lx - pr, ly - pr, lx + pr, ly + pr)
        cv.itemconfigure(self.prog, extent=-max(1.0, e * 359.0))
        cv.coords(self.pct, lx, ly if self.img_item is None else ly + R * 1.5)
        cv.coords(self.cap, lx, ly + R * (1.55 if self.img_item is None else 1.85))
        if t > T_ARRIVE + LABEL_HOLD_S:
            # le rond est arrivé : son étiquette s'efface pour laisser la place au titre (pas de texte superposé)
            if cv.itemcget(self.pct, "state") != "hidden":
                cv.itemconfigure(self.pct, state="hidden")
                cv.itemconfigure(self.cap, state="hidden")
        elif self._every(2):
            cv.itemconfigure(self.pct, text=f"{int(e * 100)}%")
            cv.itemconfigure(self.cap, text="CHARGEMENT" if t < T_ARRIVE else "NOYAU INSTALLÉ")

        # onde d'arrivée (écran principal seulement)
        if self.primary:
            b = (t - T_ARRIVE) / 1.0
            if 0.0 <= b <= 1.0:
                rr = R * (1.25 + 2.4 * b)
                cv.coords(self.burst, lx - rr, ly - rr, lx + rr, ly + rr)
                cv.itemconfigure(self.burst, state="normal", outline=_mix(CYAN, BG, b),
                                 width=max(1, int(6 * (1 - b))))
            else:
                cv.itemconfigure(self.burst, state="hidden")

    # ------------------------------------------------------------ événements
    def on_log(self, label: str, status: str = "OK") -> None:
        if self.primary:
            for old in self.logs:
                self.cv.itemconfigure(old, fill=CYAN_DIM)
            y = self.log_y0 + len(self.logs) * 30 * self.s
            text = f"> {label.upper():<14}........ [ {status} ]"
            self.logs.append(self.cv.create_text(self.log_x, y, anchor="w", text=text, fill=ORANGE,
                                                 font=self._font(14)))
        else:
            hit = self.status.get(label.lower())
            if hit:
                item, name = hit
                shown = "ACTIF" if status == "OK" else status
                self.cv.itemconfigure(item, text=f"{name:<10}........ [ {shown} ]", fill=ORANGE)

    def update(self, t: float) -> None:
        self.f += 1
        for fn in list(self.dyn):
            try:
                fn(t)
            except Exception:  # noqa: BLE001 - un élément en panne ne doit pas faire disparaître l'interface
                log.exception("Un élément de l'interface a été désactivé")
                self.dyn.remove(fn)


class Hud:
    """Gère les fenêtres (une par écran), l'animation et la fermeture en fondu."""

    def __init__(self, main_rect, side_rect=None, user: str = "KLYPP", hidden: bool = False) -> None:
        self.q: queue.Queue = queue.Queue()
        self.reveal = threading.Event()      # levé quand l'interface commence à s'effacer
        self.started = threading.Event()     # levé à la 1re image : le son de chargement part en même temps
        self.t0: float | None = None         # l'horloge démarre à la 1re image affichée, pas avant
        self.hidden = hidden
        self.done_at: float | None = None
        self.fade_start: float | None = None
        self.hist: deque = deque(maxlen=40)
        self.faceit: dict = {}          # rempli par jarvis.py (elo, niveau...)
        self.faceit_nick: str = ""
        self.root = tk.Tk()

        rects = [tuple(main_rect)]
        if side_rect and tuple(side_rect) != tuple(main_rect):
            rects.append(tuple(side_rect))
        ux0 = min(r[0] for r in rects)
        uy0 = min(r[1] for r in rects)
        mw, mh = main_rect[2] - main_rect[0], main_rect[3] - main_rect[1]
        self.s = max(0.6, min(1.3, min(mw / 1920, mh / 1080)))
        self.R = int(105 * self.s)
        self.ring_frames = self._load_ring_frames()
        self.ring_img = self.ring_frames[0] if self.ring_frames else self._load_ring_image(int(self.R * 3.3))
        if self.ring_img is not None:
            self.R = int(self.ring_img.height() / 2 * 0.875)   # tout le reste se cale sur la taille du rond

        m_ox, m_oy = main_rect[0] - ux0, main_rect[1] - uy0
        self.xe, self.ye = m_ox + mw // 2, m_oy + int(mh * 0.42)
        if len(rects) == 2:
            sr = rects[1]
            sw, sh = sr[2] - sr[0], sr[3] - sr[1]
            self.xs = (sr[0] - ux0) + sw // 2
            self.ys = (sr[1] - uy0) + int(sh * 0.42)
        else:
            self.xs, self.ys = m_ox + int(mw * 0.15), self.ye

        self.panels = [_Panel(self.root, tuple(main_rect), (m_ox, m_oy), True, user.upper(), self)]
        if len(rects) == 2:
            sr = rects[1]
            self.panels.append(_Panel(tk.Toplevel(self.root), sr, (sr[0] - ux0, sr[1] - uy0), False,
                                      user.upper(), self))
        if hidden:                           # préparée à l'avance : elle apparaîtra instantanément
            for p in self.panels:
                p.win.withdraw()

    @staticmethod
    def _load_ring_frames() -> list:
        """Images de l'animation en vague (dossier rond_anim). Liste vide si absentes."""
        frames: list = []
        try:
            files = sorted(RING_DIR.glob("rond_*.png")) if RING_DIR.is_dir() else []
            for f in files:
                frames.append(tk.PhotoImage(file=str(f)))
        except Exception:  # noqa: BLE001
            log.warning("Animation du rond illisible : je prends l'image fixe.", exc_info=True)
            return []
        return frames

    @staticmethod
    def _load_ring_image(size: int):
        """Charge rond.png s'il existe (sinon None : on dessine un rond futuriste)."""
        if not RING_IMAGE.is_file():
            return None
        try:
            from PIL import Image, ImageTk

            im = Image.open(RING_IMAGE).convert("RGBA")
            im.thumbnail((size, size), Image.LANCZOS)
            return ImageTk.PhotoImage(im)
        except Exception:  # noqa: BLE001
            try:
                return tk.PhotoImage(file=str(RING_IMAGE))
            except Exception:  # noqa: BLE001
                return None

    def position(self, t: float) -> tuple[float, float, float]:
        """Position du rond dans le grand bureau et avancement (0 à 1, accéléré puis freiné)."""
        p = min(1.0, max(0.0, (t - T_DEPART) / T_TRAVEL))
        e = p          # régulier, comme la note du son qui monte (le % suit la hauteur du son)
        x = self.xs + (self.xe - self.xs) * e
        y = self.ys + (self.ye - self.ys) * e - 70 * self.s * math.sin(math.pi * e)
        return x, y, e

    # utilisable depuis un autre thread
    def post(self, label: str, status: str = "OK") -> None:
        self.q.put(("log", label, status))

    def finish(self) -> None:
        self.q.put(("done",))

    def _show(self) -> None:
        for p in self.panels:
            p.win.deiconify()
            try:
                p.win.attributes("-topmost", True)
            except tk.TclError:
                pass
            p.win.lift()
        self.hidden = False

    def run(self) -> None:
        if self.hidden:
            self._show()
        try:
            ctypes.windll.winmm.timeBeginPeriod(1)    # minuteur précis = animation plus fluide
        except Exception:  # noqa: BLE001
            pass
        try:
            self.root.after(0, self._tick)
            self.root.mainloop()
        finally:
            self.started.set()
            self.reveal.set()
            try:
                ctypes.windll.winmm.timeEndPeriod(1)
            except Exception:  # noqa: BLE001
                pass

    def _tick(self) -> None:
        start = time.monotonic()
        try:
            if self.t0 is None:
                self.t0 = start
                self.started.set()
            t = start - self.t0
            try:
                while True:
                    msg = self.q.get_nowait()
                    if msg[0] == "log":
                        for p in self.panels:
                            p.on_log(msg[1], msg[2])
                    elif msg[0] == "done":
                        self.done_at = start
            except queue.Empty:
                pass

            X, Y, _ = self.position(t)
            self.hist.append((X, Y))
            for p in self.panels:
                p.update(t)

            if self.fade_start is None:
                finished = self.done_at is not None and start - self.done_at > LINGER_S and t > MIN_VISIBLE_S
                if finished or t > MAX_S:
                    self.fade_start = start
                    self.reveal.set()
            if self.fade_start is not None:
                alpha = 1.0 - (start - self.fade_start) / FADE_S
                if alpha <= 0:
                    self.root.destroy()
                    return
                for p in self.panels:
                    try:
                        p.win.attributes("-alpha", alpha)
                    except tk.TclError:
                        pass

            delay = max(1, int(1000 / FPS - (time.monotonic() - start) * 1000))
            self.root.after(delay, self._tick)
        except Exception:  # noqa: BLE001 - une erreur d'affichage ne doit jamais bloquer le réveil
            log.exception("Erreur d'affichage de l'interface")
            self.reveal.set()
            try:
                self.root.destroy()
            except Exception:  # noqa: BLE001
                pass
