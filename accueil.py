"""Scan d'arrivée façon Iron Man : quand tu reviens au PC, la webcam te reconnaît et Jarvis t'accueille.

Comment Jarvis sait que tu « t'assois » : il regarde depuis combien de temps le clavier et la souris n'ont pas
bougé (Windows le donne sans rien espionner). Après une absence (5 min par défaut), le premier mouvement de
souris ou appui de touche lance le scan : une petite fenêtre holographique s'ouvre au centre de l'écran,
la caméra s'allume quelques secondes, ton visage est comparé à celui enregistré par le mode caméra, puis tout
se ferme tout seul (caméra coupée). Rien n'est enregistré ni envoyé : tout reste sur le PC.

Pas de scan : pendant un jeu (mode jeu), quand l'écran est verrouillé, quand le mode caméra est déjà ouvert,
et pas plus d'une fois toutes les 10 minutes.

Réglages dans .env :
  JARVIS_ACCUEIL=non              désactive le scan d'arrivée
  JARVIS_ACCUEIL_ABSENCE=5        minutes d'absence avant un nouveau scan
"""
from __future__ import annotations

import ctypes
import logging
import os
import threading
import time
from ctypes import wintypes

log = logging.getLogger("jarvis")


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or "").strip() or default


def idle_seconds() -> float:
    """Secondes depuis le dernier mouvement de souris / appui de touche."""
    info = _LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(info)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    return ((ctypes.windll.kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF) / 1000.0


def screen_locked() -> bool:
    """Écran de verrouillage affiché (on attend que tu sois connecté)."""
    u = ctypes.windll.user32
    u.OpenInputDesktop.restype = wintypes.HANDLE
    h = u.OpenInputDesktop(0, False, 0x0100)              # DESKTOP_SWITCHDESKTOP
    if not h:
        return True
    ok = u.SwitchDesktop(h)
    u.CloseDesktop(h)
    return not ok


class Accueil:
    def __init__(self, say, user: str, camera_busy=lambda: False, welcome=None, on_recognized=None) -> None:
        self.say = say
        self.user = user
        self.camera_busy = camera_busy                    # le mode caméra (gestes) est-il ouvert ?
        self.welcome = welcome                            # phrase de bienvenue (heure, météo...)
        self.absence = max(1.0, float(_env("JARVIS_ACCUEIL_ABSENCE", "5"))) * 60
        self.last_scan = time.monotonic()                 # pas de scan juste après le démarrage (il y a l'intro)
        self.cam = None
        self.on_recognized = on_recognized                # Jarvis en sommeil : visage reconnu -> on le lance
        self.recognized = False
        self.stopped = threading.Event()
        if on_recognized:
            self.last_scan = -1e9                         # en sommeil : le premier retour déclenche le scan

    def _game(self) -> bool:
        try:
            import mode_jeu
            if self.on_recognized:                        # en sommeil, la surveillance des jeux ne tourne pas
                return mode_jeu.ACTIF.is_set() or mode_jeu.detect() is not None
            return mode_jeu.ACTIF.is_set()
        except Exception:  # noqa: BLE001
            return False

    def scan(self) -> str:
        import camera_mode
        if self.cam and self.cam.active:
            return "Scan déjà en cours."
        self.recognized = False

        def auth(ok: bool) -> None:
            self.recognized = ok

        def end() -> None:
            if self.recognized and self.on_recognized and not self.stopped.is_set():
                self.on_recognized()

        self.cam = camera_mode.CameraMode(say=self.say, user=self.user, mode="accueil", on_welcome=self.welcome,
                                          on_auth=auth, on_end=end)
        self.last_scan = time.monotonic()
        return self.cam.start()

    def _loop(self) -> None:
        away = False
        while not self.stopped.is_set():
            time.sleep(1.5)
            try:
                idle = idle_seconds()
                if idle >= self.absence:
                    away = True
                    continue
                if not away or idle > 5:
                    continue
                # tu viens de revenir : premier mouvement après une absence
                if screen_locked():
                    continue                              # on attend la fin du verrouillage (away reste vrai)
                away = False
                if self._game() or self.camera_busy() or time.monotonic() - self.last_scan < 600:
                    continue
                log.info("Scan d'arrivée : retour après une absence, identification.")
                self.scan()
            except Exception:  # noqa: BLE001
                log.debug("Scan d'arrivée : erreur", exc_info=True)


def start(say, user: str, camera_busy=lambda: False, welcome=None, on_recognized=None) -> Accueil | None:
    """on_recognized : Jarvis en sommeil -> ton visage reconnu à ton retour le lance (JARVIS_LANCEMENT_VISAGE=non)."""
    if os.name != "nt" or _env("JARVIS_ACCUEIL").lower() in ("non", "0", "off", "false"):
        return None
    if on_recognized and _env("JARVIS_LANCEMENT_VISAGE").lower() in ("non", "0", "off", "false"):
        return None
    a = Accueil(say, user, camera_busy, welcome, on_recognized)
    threading.Thread(target=a._loop, name="accueil", daemon=True).start()
    log.info("Scan d'arrivée prêt (après %d min d'absence).", int(a.absence // 60))
    return a
