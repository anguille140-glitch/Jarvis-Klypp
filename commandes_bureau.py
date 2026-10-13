"""Lancer / éteindre Jarvis SANS la voix : icônes du bureau et raccourcis clavier.

  Icône « JARVIS » (ou Ctrl + Alt + J)            -> lance Jarvis (l'intro démarre comme avec « salut Jarvis »)
  Icône « Éteindre JARVIS » (ou Ctrl + Alt + Fin) -> fin de programme (animation de sortie, Jarvis se met en veille)

Fonctionnement : l'icône dépose un petit « mot » dans .cache/commandes ; Jarvis le lit en moins d'une demi-seconde.
Si Jarvis ne tourne pas du tout (superviseur arrêté), l'icône « JARVIS » relance le superviseur.

Utilisé seul :  pythonw jarvis_bureau.py lancer | fermer      (c'est ce que font les icônes)
"""
from __future__ import annotations

import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
DIR = BASE / ".cache" / "commandes"
MAX_AGE = 45.0                                         # un mot plus vieux que ça est ignoré


def request(kind: str) -> None:
    """Dépose la demande (« lancer » ou « fermer »)."""
    DIR.mkdir(parents=True, exist_ok=True)
    (DIR / f"{kind}.flag").write_text(str(time.time()), encoding="utf-8")


def take(kind: str) -> bool:
    """True (une seule fois) si la demande a été déposée récemment."""
    f = DIR / f"{kind}.flag"
    try:
        if not f.is_file():
            return False
        age = time.time() - f.stat().st_mtime
        f.unlink(missing_ok=True)
        return age < MAX_AGE
    except OSError:
        return False


def clear() -> None:
    for kind in ("lancer", "fermer"):
        try:
            (DIR / f"{kind}.flag").unlink(missing_ok=True)
        except OSError:
            pass
