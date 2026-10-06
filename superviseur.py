"""Superviseur de Jarvis : le fait tourner caché en permanence et le relance s'il s'arrête.

Lancé (sans fenêtre) par installer_demarrage.bat, puis à chaque démarrage de Windows.
  - Jarvis tourne sans fenêtre noire ; tout est écrit dans jarvis.log
  - plantage, micro débranché, PC sorti de veille -> Jarvis redémarre tout seul (directement en écoute, sans intro)
  - « fin de programme » pendant une session -> Jarvis se remet en veille et attend « salut Jarvis »
    (JARVIS_FIN=arret dans .env pour qu'il s'arrête vraiment)
  - « fin de programme » quand il attend « salut Jarvis » -> arrêt complet (jusqu'au prochain démarrage du PC)
  - arreter_jarvis.bat : arrêt complet tout de suite
"""
from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
LOG = BASE / "jarvis.log"
PIDS = BASE / ".cache" / "superviseur.json"
CREATE_NO_WINDOW = 0x08000000
STOP_EXIT = 10          # « fin de programme » pendant une session (voir assistant.py)
ALREADY = 11            # un autre Jarvis tourne déjà (lancé à la main)


def env_value(name: str, default: str = "") -> str:
    v = os.environ.get(name)
    if v:
        return v.strip()
    try:
        for line in (BASE / ".env").read_text(encoding="utf-8-sig").splitlines():
            k, _, val = line.partition("=")
            if k.strip() == name:
                return val.strip().strip('"').strip("'") or default
    except OSError:
        pass
    return default


def note(msg: str) -> None:
    try:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%H:%M:%S} SUPERVISEUR {msg}\n")
    except OSError:
        pass


def rotate_log() -> None:
    try:
        if LOG.is_file() and LOG.stat().st_size > 5_000_000:
            old = LOG.with_name("jarvis.ancien.log")
            old.unlink(missing_ok=True)
            LOG.rename(old)
    except OSError:
        pass


def python_exe() -> str:
    """python.exe à côté de pythonw.exe (Jarvis a besoin d'une sortie pour son journal), fenêtre cachée."""
    exe = Path(sys.executable)
    cand = exe.with_name("python.exe")
    return str(cand if cand.is_file() else exe)


def single_instance():
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    h = k32.CreateMutexW(None, False, "Local\\JarvisSuperviseur")
    if ctypes.get_last_error() == 183:          # ERROR_ALREADY_EXISTS
        return None
    return h


def save_pids(child: int | None) -> None:
    try:
        PIDS.parent.mkdir(parents=True, exist_ok=True)
        PIDS.write_text(json.dumps({"superviseur": os.getpid(), "jarvis": child}), encoding="utf-8")
    except OSError:
        pass


def main() -> int:
    if sys.platform != "win32":
        print("Windows uniquement.")
        return 1
    mutex = single_instance()
    if mutex is None:
        return 0                                # déjà en route
    os.chdir(BASE)
    if "--demarrage" in sys.argv:
        time.sleep(float(env_value("JARVIS_DELAI_DEMARRAGE", "15") or 15))   # laisse Windows finir de démarrer
    stop_for_real = env_value("JARVIS_FIN", "veille").lower() in ("arret", "arrêt", "stop", "quitter")
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    args: list[str] = []                        # 1er lancement : attend « salut Jarvis » (intro)
    fails, delay = 0, 3.0
    note("démarrage (Jarvis tourne caché ; journal : jarvis.log)")
    while True:
        rotate_log()
        started = time.monotonic()
        with LOG.open("a", encoding="utf-8") as out:
            p = subprocess.Popen([python_exe(), "jarvis.py", *args], cwd=BASE, env=env, stdin=subprocess.DEVNULL,
                                 stdout=out, stderr=subprocess.STDOUT, creationflags=CREATE_NO_WINDOW)
            save_pids(p.pid)
            rc = p.wait()
        ran = time.monotonic() - started
        save_pids(None)
        if rc == 0:
            note("arrêt demandé (« fin de programme ») : je m'arrête.")
            return 0
        if rc == STOP_EXIT:
            if stop_for_real:
                note("fin de programme : arrêt (JARVIS_FIN=arret).")
                return 0
            note("fin de programme : Jarvis se remet en veille (dis « salut Jarvis »).")
            args, fails, delay = [], 0, 3.0
            time.sleep(2)
            continue
        if rc == ALREADY:
            note("un autre Jarvis tourne déjà (lancé à la main) : je réessaie dans 30 s.")
            time.sleep(30)
            continue
        # plantage / micro perdu : on relance directement l'écoute, sans refaire l'intro
        fails = fails + 1 if ran < 120 else 1
        delay = 3.0 if fails <= 1 else min(60.0, delay * 2)
        note(f"Jarvis s'est arrêté (code {rc}) : relance dans {delay:.0f} s.")
        args = ["--assistant"]
        time.sleep(delay)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:  # noqa: BLE001
        note(f"erreur du superviseur : {e!r}")
        raise
