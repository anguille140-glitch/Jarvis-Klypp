"""Installe l'IA locale de Jarvis (appelé par installer_ia_locale.bat).
Télécharge : les modèles Ollama, la voix Piper française, le modèle Whisper. Une seule fois (~12 Go)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
try:
    from dotenv import load_dotenv
    load_dotenv(BASE / ".env")
except Exception:  # noqa: BLE001
    pass
import local_ai  # noqa: E402

MODEL = local_ai._env("JARVIS_MODELE", "qwen3.5:9b")
GAME_MODEL = local_ai._env("JARVIS_MODELE_JEU", "")
VOICE = local_ai._env("JARVIS_VOIX_PIPER", "fr_FR-tom-medium")


def step(t: str) -> None:
    print(f"\n=== {t} ===", flush=True)


def ollama_exe() -> str | None:
    p = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
    return str(p) if p.is_file() else shutil.which("ollama")


def main() -> int:
    step("1/4  Ollama (le moteur de l'IA locale)")
    if not ollama_exe():
        print("Installation d'Ollama...")
        if shutil.which("winget"):
            subprocess.run(["winget", "install", "-e", "--id", "Ollama.Ollama", "--accept-source-agreements",
                            "--accept-package-agreements"])
        if not ollama_exe():
            setup = BASE / "modeles" / "OllamaSetup.exe"
            setup.parent.mkdir(parents=True, exist_ok=True)
            print("Téléchargement de l'installateur Ollama...")
            urllib.request.urlretrieve("https://ollama.com/download/OllamaSetup.exe", setup)
            print("Suis l'installation d'Ollama qui s'ouvre, puis reviens ici.")
            subprocess.run([str(setup)])
    exe = ollama_exe()
    if not exe:
        print("ÉCHEC : Ollama n'est pas installé. Installe-le depuis https://ollama.com puis relance ce fichier.")
        return 1
    if not local_ai.start_ollama(40):
        print("ÉCHEC : Ollama ne démarre pas. Redémarre le PC puis relance ce fichier.")
        return 1
    print("Ollama OK.")

    step(f"2/4  Cerveau : {MODEL} (environ 7 Go, une seule fois)")
    for m in [MODEL] + ([GAME_MODEL] if GAME_MODEL else []):
        r = subprocess.run([exe, "pull", m])
        if r.returncode != 0:
            print(f"ÉCHEC du téléchargement de {m}. Vérifie internet et relance.")
            return 1
    print("Petit essai...")
    try:
        llm = local_ai.LocalLLM()
        out = llm.generate({"contents": [{"role": "user", "parts": [{"text": "Dis juste : prêt."}]}]})
        print("Réponse du cerveau :", out["candidates"][0]["content"]["parts"][0].get("text", "?"))
    except Exception as e:  # noqa: BLE001
        print("Essai impossible :", e)

    step(f"3/4  Voix : Piper {VOICE}")
    d = BASE / "modeles" / "piper"
    d.mkdir(parents=True, exist_ok=True)
    lang, name, quality = VOICE.split("-", 2)
    url = (f"https://huggingface.co/rhasspy/piper-voices/resolve/main/{lang.split('_')[0]}/{lang}/{name}/"
           f"{quality}/{VOICE}")
    for ext in (".onnx", ".onnx.json"):
        f = d / (VOICE + ext)
        if not f.is_file():
            print("Téléchargement", f.name)
            urllib.request.urlretrieve(url + ext, f)
    try:
        v = local_ai.PiperVoice().audio("Bonjour monsieur, je suis prêt.")
        print("Voix OK." if v else "Voix : échec (Jarvis utilisera une autre voix).")
    except Exception as e:  # noqa: BLE001
        print("Voix : échec :", e)

    step("4/4  Oreilles : Whisper (transcription, ~1,6 Go la première fois)")
    t = local_ai.Transcriber()
    t0 = time.monotonic()
    m = t._load()
    print("Whisper OK." if m else "Whisper indisponible : Jarvis utilisera Vosk.", f"({time.monotonic() - t0:.0f} s)")

    envf = BASE / ".env"
    txt = envf.read_text(encoding="utf-8") if envf.is_file() else ""
    if "JARVIS_IA=" not in txt:
        with envf.open("a", encoding="utf-8") as f:
            f.write("\n# Cerveau : local (100 % sur le PC) | hybride (local + Gemini gratuit pour les gros travaux) | gemini\n"
                    f"JARVIS_IA={'hybride' if 'GEMINI_API_KEY=' in txt and 'GEMINI_API_KEY=\n' not in txt else 'local'}\n")
    print("\nTout est prêt : Jarvis utilise maintenant son IA LOCALE (gratuite, sans quota).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
