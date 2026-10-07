"""« Jarvis, lance-moi une session CS » : FACEIT AC d'abord, puis Counter-Strike 2 une fois l'anti-triche prêt.

Étapes (Jarvis te parle à chacune) :
  1. CS2 déjà lancé ? rien à faire.
  2. FACEIT AC pas encore lancé : Jarvis le lance. Il demande les droits administrateur, donc Windows affiche
     sa fenêtre « Voulez-vous autoriser... » : clique sur Oui (si elle clignote dans la barre des tâches, clique dessus).
     Astuce : « Jarvis, installe le lancement FACEIT sans confirmation » crée une tâche Windows (une seule
     confirmation, une fois pour toutes) ; ensuite FACEIT AC se lance sans plus rien demander.
  3. Jarvis attend que FACEIT AC tourne vraiment (jusqu'à 90 s), laisse l'anti-triche démarrer quelques secondes,
  4. puis lance CS2 par Steam et te prévient quand le jeu est ouvert.

Réglages dans .env (facultatifs) :
  JARVIS_FACEIT_AC=C:\\chemin\\vers\\faceitclient.exe     si FACEIT AC est installé ailleurs
  JARVIS_FACEIT_ATTENTE=6                                secondes laissées à l'anti-triche avant CS2
"""
from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
from pathlib import Path

log = logging.getLogger("jarvis")
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
TASK_NAME = "Jarvis FACEIT AC"
AC_PROCESSES = {"faceitclient.exe"}
CS2_PROCESS = "cs2.exe"
_busy = threading.Lock()


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip().strip('"')


def running(names: set[str]) -> bool:
    try:
        import psutil

        return any((p.info.get("name") or "").lower() in names for p in psutil.process_iter(["name"]))
    except ImportError:
        out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, timeout=5,
                             creationflags=NO_WINDOW).stdout.decode("utf-8", "replace").lower()
        return any(f'"{n}"' in out for n in names)


def find_faceit_ac() -> str | None:
    """Le programme FACEIT AC (ou son raccourci du menu Démarrer)."""
    cands = [_env("JARVIS_FACEIT_AC")]
    for base in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramFiles(x86)", ""),
                 os.environ.get("ProgramW6432", "")):
        if base:
            cands += [os.path.join(base, "FACEIT AC", "faceitclient.exe"),
                      os.path.join(base, "FACEIT AC", "FACEITClient.exe")]
    for start in (os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), r"Microsoft\Windows\Start Menu\Programs"),
                  os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs")):
        cands += [os.path.join(start, "FACEIT AC.lnk"), os.path.join(start, "FACEIT AC", "FACEIT AC.lnk")]
        try:
            cands += [str(p) for p in Path(start).rglob("FACEIT AC*.lnk")]
        except OSError:
            pass
    for c in cands:
        if c and os.path.exists(c):
            return c
    return None


def _task_exists() -> bool:
    try:
        return subprocess.run(["schtasks", "/Query", "/TN", TASK_NAME], capture_output=True, timeout=10,
                              creationflags=NO_WINDOW).returncode == 0
    except Exception:  # noqa: BLE001
        return False


def _shell(path: str, verb: str = "open", params: str | None = None) -> int:
    """Lance comme un double-clic (Windows demande lui-même les droits administrateur si besoin)."""
    import ctypes

    sh = ctypes.windll.shell32.ShellExecuteW
    sh.restype = ctypes.c_ssize_t
    return int(sh(None, verb, path, params, None, 1))


def install_no_prompt() -> str:
    """Crée une tâche Windows « droits les plus élevés » qui lance FACEIT AC sans confirmation à chaque fois.
    Windows demande UNE confirmation (une seule fois) pour créer la tâche."""
    exe = find_faceit_ac()
    if not exe or exe.lower().endswith(".lnk"):
        return ("ÉCHEC : je ne trouve pas le programme FACEIT AC (faceitclient.exe). "
                "Ajoute JARVIS_FACEIT_AC=chemin\\faceitclient.exe dans .env")
    args = f'/Create /F /TN "{TASK_NAME}" /TR "\\"{exe}\\"" /SC ONCE /ST 00:00 /RL HIGHEST'
    rc = _shell("schtasks.exe", "runas", args)
    if rc <= 32:
        return "ÉCHEC : création refusée (la confirmation Windows a été refusée ?)"
    for _ in range(30):
        if _task_exists():
            return "OK : FACEIT AC se lancera désormais sans demander de confirmation"
        time.sleep(1)
    return "ÉCHEC : la tâche n'a pas été créée"


def launch_faceit_ac() -> str:
    if _task_exists():                                     # lancement sans confirmation (déjà installé)
        r = subprocess.run(["schtasks", "/Run", "/TN", TASK_NAME], capture_output=True, timeout=15,
                           creationflags=NO_WINDOW)
        if r.returncode == 0:
            return "tache"
    exe = find_faceit_ac()
    if not exe:
        return "introuvable"
    rc = _shell(exe)
    return "lance" if rc > 32 else ("refuse" if rc == 5 else f"erreur {rc}")


def _wait(names: set[str], seconds: float, stop: threading.Event | None = None) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if running(names):
            return True
        if stop is not None and stop.is_set():
            return False
        time.sleep(1)
    return False


def session_cs(say=lambda t: None, stop: threading.Event | None = None) -> str:
    """Toute la séquence. say(texte) : Jarvis parle. Renvoie un résumé pour le journal."""
    if not _busy.acquire(blocking=False):
        say("Je suis déjà en train de lancer ta session.")
        return "DÉJÀ EN COURS"
    try:
        if running({CS2_PROCESS}):
            say("Counter-Strike 2 est déjà lancé, monsieur.")
            return "OK : CS2 déjà ouvert"
        if running(AC_PROCESSES):
            say("FACEIT AC est déjà actif. Je lance Counter-Strike 2.")
        else:
            say("Je lance FACEIT AC.")
            how = launch_faceit_ac()
            log.info("Session CS : FACEIT AC -> %s", how)
            if how == "introuvable":
                say("Je ne trouve pas FACEIT AC sur ce PC. Indique-moi son emplacement dans le réglage JARVIS_FACEIT_AC.")
                return "ÉCHEC : FACEIT AC introuvable"
            if how == "refuse":
                say("Windows a refusé le lancement de FACEIT AC. Il faut accepter la fenêtre de confirmation.")
                return "ÉCHEC : confirmation refusée"
            if how == "lance":
                say("Accepte la fenêtre de Windows si elle apparaît.")
            if not _wait(AC_PROCESSES, 90, stop):
                say("FACEIT AC ne s'est pas lancé. Je ne démarre pas Counter-Strike sans l'anti-triche.")
                return "ÉCHEC : FACEIT AC pas démarré en 90 s"
            try:
                pause = float(_env("JARVIS_FACEIT_ATTENTE") or 6)
            except ValueError:
                pause = 6.0
            time.sleep(max(0.0, min(30.0, pause)))         # l'anti-triche finit de s'initialiser
            say("FACEIT AC est prêt. Je lance Counter-Strike 2.")
        os.startfile("steam://rungameid/730")              # type: ignore[attr-defined]
        if _wait({CS2_PROCESS}, 120, stop):
            say("Counter-Strike 2 est lancé. Bonne partie, monsieur.")
            return "OK : FACEIT AC puis CS2 lancés"
        say("Steam n'a pas encore ouvert Counter-Strike 2. Vérifie Steam, une mise à jour est peut-être en cours.")
        return "ÉCHEC : CS2 pas ouvert après 2 minutes"
    except Exception as e:  # noqa: BLE001
        log.warning("Session CS en échec", exc_info=True)
        say("Je n'ai pas réussi à lancer la session.")
        return f"ÉCHEC : {e}"
    finally:
        _busy.release()


def start_session_cs(say) -> str:
    """Lance la séquence en arrière-plan (Jarvis reste disponible pendant l'attente)."""
    if _busy.locked():
        return "DÉJÀ EN COURS : la session CS se lance"

    def go() -> None:
        log.info("Session CS : %s", session_cs(say))

    threading.Thread(target=go, name="session-cs", daemon=True).start()
    return "EN COURS : FACEIT AC puis CS2 (je préviens à chaque étape, rien à dire de plus)"
