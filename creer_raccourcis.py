"""Crée les icônes du bureau « JARVIS » et « Éteindre JARVIS » (avec Ctrl + Alt + J et Ctrl + Alt + Fin).

Lancé par installer_demarrage.bat (ou à la main : .venv\\Scripts\\python.exe creer_raccourcis.py).
"""
from __future__ import annotations

import ctypes
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent


def make_icons() -> tuple[Path, Path]:
    """Icônes à partir de l'image de la sphère : une bleue (lancer), une plus sombre avec un trait (éteindre)."""
    from PIL import Image, ImageDraw, ImageEnhance

    out_dir = BASE / ".cache" / "icones"
    out_dir.mkdir(parents=True, exist_ok=True)
    src = Image.open(BASE / "jarvis_orb.png").convert("RGBA").resize((256, 256), Image.LANCZOS)
    # le noir de l'image devient transparent (rond lumineux sur le bureau)
    px = src.load()
    for y in range(256):
        for x in range(256):
            r, g, b, _ = px[x, y]
            px[x, y] = (r, g, b, min(255, int(max(r, g, b) * 1.6)))
    on = out_dir / "jarvis.ico"
    src.save(on, sizes=[(256, 256), (64, 64), (48, 48), (32, 32), (16, 16)])
    off_img = ImageEnhance.Brightness(src).enhance(0.55)
    d = ImageDraw.Draw(off_img)
    d.ellipse((176, 176, 248, 248), fill=(20, 20, 26, 255), outline=(255, 90, 80, 255), width=6)
    d.arc((190, 190, 234, 234), 300, 240, fill=(255, 90, 80, 255), width=6)        # symbole « éteindre »
    d.line((212, 184, 212, 210), fill=(255, 90, 80, 255), width=6)
    off = out_dir / "jarvis_eteindre.ico"
    off_img.save(off, sizes=[(256, 256), (64, 64), (48, 48), (32, 32), (16, 16)])
    return on, off


def shortcut(folder_ps: str, name: str, args: str, icon: Path, hotkey: str, desc: str) -> None:
    """Raccourci .lnk (sert seulement pour les touches Ctrl+Alt+J / Ctrl+Alt+Fin, rangé dans le menu Démarrer)."""
    pyw = Path(sys.executable).with_name("pythonw.exe")
    exe = pyw if pyw.is_file() else Path(sys.executable)
    ps = (f"$d={folder_ps}; New-Item -ItemType Directory -Force -Path $d | Out-Null;"
          f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut(\"$d\\{name}.lnk\");"
          f"$s.TargetPath='{exe}';$s.Arguments='{args}';$s.WorkingDirectory='{BASE}';"
          f"$s.IconLocation='{icon},0';$s.Hotkey='{hotkey}';$s.Description='{desc}';$s.Save()")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def desktop_dir() -> Path:
    out = subprocess.run(["powershell", "-NoProfile", "-Command", "[Environment]::GetFolderPath('Desktop')"],
                         capture_output=True, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return Path(out.stdout.strip() or Path.home() / "Desktop")


def register_type(ext: str, prog: str, icon: Path, action: str, label: str) -> None:
    """Type de fichier perso (pour TON compte Windows seulement, sans droits admin) : icône + double-clic.
    Un vrai fichier (pas un raccourci) : Windows n'ajoute donc PAS la petite flèche."""
    import winreg
    pyw = Path(sys.executable).with_name("pythonw.exe")
    exe = pyw if pyw.is_file() else Path(sys.executable)
    root = r"Software\Classes"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"{root}\{ext}") as k:
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, prog)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"{root}\{prog}") as k:
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, label)
        winreg.SetValueEx(k, "NeverShowExt", 0, winreg.REG_SZ, "")          # le nom s'affiche sans extension
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"{root}\{prog}\DefaultIcon") as k:
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, f"{icon},0")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"{root}\{prog}\shell\open\command") as k:
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, f'"{exe}" "{BASE / "jarvis_bureau.py"}" {action}')


def main() -> int:
    try:
        on, off = make_icons()
    except Exception as e:  # noqa: BLE001
        print("Icônes impossibles à créer :", e)
        on = off = Path(sys.executable)
    desk = desktop_dir()
    # icônes du bureau SANS flèche : de vrais petits fichiers d'un type « Jarvis » (au lieu de raccourcis)
    register_type(".jarvis", "Jarvis.Lancer", on, "lancer", "Lancer Jarvis")
    register_type(".jarvisstop", "Jarvis.Eteindre", off, "fermer", "Éteindre Jarvis")
    for old in ("JARVIS.lnk", "Éteindre JARVIS.lnk"):                     # anciennes icônes (avec flèche)
        (desk / old).unlink(missing_ok=True)
    (desk / "JARVIS.jarvis").write_text("Double-clic : lance Jarvis.", encoding="utf-8")
    (desk / "Éteindre JARVIS.jarvisstop").write_text("Double-clic : fin de programme.", encoding="utf-8")
    try:
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)   # Windows rafraîchit les icônes
    except Exception:  # noqa: BLE001
        pass
    # les touches Ctrl+Alt+J / Ctrl+Alt+Fin : raccourcis rangés dans le menu Démarrer (invisibles sur le bureau)
    menu = "[Environment]::GetFolderPath('Programs')+'\\Jarvis'"
    shortcut(menu, "JARVIS", "jarvis_bureau.py lancer", on, "CTRL+ALT+J", "Lancer Jarvis (Ctrl+Alt+J)")
    shortcut(menu, "Éteindre JARVIS", "jarvis_bureau.py fermer", off, "CTRL+ALT+END", "Fin de programme (Ctrl+Alt+Fin)")
    print("Icônes « JARVIS » et « Éteindre JARVIS » créées sur le bureau (sans flèche).")
    print("Raccourcis clavier : Ctrl+Alt+J (lancer) et Ctrl+Alt+Fin (éteindre).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
