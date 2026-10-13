"""Ce que lancent les icônes du bureau (et Ctrl + Alt + J / Ctrl + Alt + Fin) : voir commandes_bureau.py."""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
import commandes_bureau  # noqa: E402


def supervisor_running() -> bool:
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    h = k32.CreateMutexW(None, False, "Local\\JarvisSuperviseur")
    running = ctypes.get_last_error() == 183           # ERROR_ALREADY_EXISTS
    if h:
        k32.CloseHandle(h)
    return running


def jarvis_running() -> bool:
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    h = k32.CreateMutexW(None, False, "Local\\JarvisPrincipal")
    running = ctypes.get_last_error() == 183
    if h:
        k32.CloseHandle(h)
    return running


def main() -> int:
    kind = (sys.argv[1] if len(sys.argv) > 1 else "lancer").lower()
    kind = "fermer" if kind in ("fermer", "eteindre", "éteindre", "stop") else "lancer"
    commandes_bureau.request(kind)
    if kind == "lancer" and not supervisor_running() and not jarvis_running():
        exe = Path(sys.executable).with_name("pythonw.exe")
        subprocess.Popen([str(exe if exe.is_file() else sys.executable), "superviseur.py"], cwd=BASE,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), close_fds=True)
    return 0


if __name__ == "__main__":
    os.chdir(BASE)
    raise SystemExit(main())
