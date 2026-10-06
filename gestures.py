"""Reconnaissance des gestes à partir des 21 repères d'une main (format MediaPipe).

Les repères sont des couples (x, y) normalisés entre 0 et 1. Ce module ne dépend ni de la
caméra ni de MediaPipe : il se teste seul.
"""
from __future__ import annotations

import math
from collections import deque

WRIST, THUMB_TIP, INDEX_TIP, MIDDLE_MCP = 0, 4, 8, 9
FINGERS = ((8, 6), (12, 10), (16, 14), (20, 18))      # (bout, articulation) index, majeur, annulaire, auriculaire


def _dist(a, b) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def hand_size(lm) -> float:
    """Taille de la main (poignet -> base du majeur) : sert d'étalon, quelle que soit la distance à la caméra."""
    return max(1e-6, _dist(lm[WRIST], lm[MIDDLE_MCP]))


def pinch_ratio(lm) -> float:
    """Écart pouce-index rapporté à la taille de la main (petit = pince)."""
    return _dist(lm[THUMB_TIP], lm[INDEX_TIP]) / hand_size(lm)


def pinch_point(lm) -> tuple[float, float]:
    """Point saisi : milieu entre le bout du pouce et le bout de l'index."""
    return ((lm[THUMB_TIP][0] + lm[INDEX_TIP][0]) / 2, (lm[THUMB_TIP][1] + lm[INDEX_TIP][1]) / 2)


def fingers_extended(lm) -> list[bool]:
    """Index, majeur, annulaire, auriculaire : doigt tendu = bout plus loin du poignet que l'articulation."""
    return [_dist(lm[tip], lm[WRIST]) > _dist(lm[pip], lm[WRIST]) * 1.1 for tip, pip in FINGERS]


def open_palm(lm) -> bool:
    return all(fingers_extended(lm))


def palm_center(lm) -> tuple[float, float]:
    return ((lm[WRIST][0] + lm[MIDDLE_MCP][0]) / 2, (lm[WRIST][1] + lm[MIDDLE_MCP][1]) / 2)


class PinchState:
    """Pince avec hystérésis (évite les clignotements) : se déclenche serrée, se relâche en s'ouvrant plus."""

    def __init__(self, on: float = 0.32, off: float = 0.50, frames: int = 2) -> None:
        self.on, self.off, self.frames = on, off, frames
        self.active = False
        self._count = 0

    def update(self, lm) -> bool:
        r = pinch_ratio(lm)
        if not self.active:
            self._count = self._count + 1 if r < self.on else 0
            if self._count >= self.frames:
                self.active = True
        elif r > self.off:
            self.active = False
            self._count = 0
        return self.active

    def reset(self) -> None:
        self.active = False
        self._count = 0


class TwoHandZoom:
    """Deux mains qui pincent : l'écart entre les deux points de pince donne le facteur de zoom."""

    def __init__(self) -> None:
        self.d0: float | None = None

    def update(self, p1, p2) -> float | None:
        """Renvoie le facteur (1.0 au début du geste), ou None si la valeur de départ vient d'être prise."""
        d = _dist(p1, p2)
        if self.d0 is None:
            self.d0 = max(d, 1e-6)
            return 1.0
        return d / self.d0

    def release(self) -> None:
        self.d0 = None


class SwipeDetector:
    """Main ouverte qui balaie l'écran : renvoie 'droite', 'gauche', 'haut' ou 'bas'."""

    def __init__(self, window_s: float = 0.45, min_move: float = 0.30, cooldown_s: float = 0.8) -> None:
        self.window_s, self.min_move, self.cooldown_s = window_s, min_move, cooldown_s
        self.hist: deque = deque()
        self.last = -10.0

    def update(self, lm, t: float) -> str | None:
        if not open_palm(lm):
            self.hist.clear()
            return None
        x, y = palm_center(lm)
        self.hist.append((t, x, y))
        while self.hist and t - self.hist[0][0] > self.window_s:
            self.hist.popleft()
        if t - self.last < self.cooldown_s or len(self.hist) < 3:
            return None
        dx, dy = x - self.hist[0][1], y - self.hist[0][2]
        if max(abs(dx), abs(dy)) < self.min_move:
            return None
        self.last = t
        self.hist.clear()
        if abs(dx) >= abs(dy):
            return "droite" if dx > 0 else "gauche"
        return "bas" if dy > 0 else "haut"
