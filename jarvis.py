#!/usr/bin/env python3
"""Jarvis : dis « Jarvis » (ou double clap) pour réveiller le bureau (Windows).

Au mot de lancement : la voix te salue, puis FACEIT s'ouvre sur
l'écran principal, Discord et ton profil FACEIT s'ouvrent sur l'écran de gauche.
Ensuite Jarvis reste à l'écoute : « Jarvis, ouvre Spotify » (voir assistant.py).
Assistant seul, sans le réveil : jarvis.py --assistant (parler_a_jarvis.bat).

Mode debug : définir JARVIS_DEBUG=1 (voir lancer_debug.bat).
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import logging
import os
import subprocess
import sys
import threading
import time
import urllib.request
import wave
import webbrowser
from ctypes import wintypes
from pathlib import Path

import numpy as np
import sounddevice as sd
from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent
load_dotenv(BASE / ".env")

# --- Tes réglages -----------------------------------------------------------
MUSIC_URL = "https://www.youtube.com/watch?v=zi60ZrJj34M"
YOUTUBE_HOME_URL = "https://www.youtube.com"
FACEIT_URL = "https://www.faceit.com/fr/players/KlyppTTV"
WELCOME_PHRASE = "Enfin te revoilà Klypp"
USER_NAME = "Klypp"   # affiché dans l'interface
FACEIT_NICK = FACEIT_URL.rstrip("/").split("/")[-1]   # pseudo FACEIT (tiré du lien du profil)
FACEIT_DATA: dict = {}                                # elo, niveau... (rempli en tâche de fond)
MUSIC_HEAD_START_S = 8.0   # secondes avant d'ouvrir l'accueil YouTube par-dessus la musique
MUSIC_LEAD_S = 1.0         # la musique se prépare ce temps AVANT la fin de l'intro (JARVIS_MUSIQUE_AVANCE)

# --- Détection du clap ------------------------------------------------------
BLOCK_MS = 10                 # taille d'analyse (précis, léger)
SPIKE_RATIO = 7.0             # un pic doit dépasser 7x le bruit de fond
MIN_GAP_S = 0.12              # écart minimum entre les deux claps
MAX_GAP_S = 0.35              # écart maximum entre les deux claps
DECAY_CHECK_S = 0.10          # un clap doit s'effondrer en moins de 100 ms...
DECAY_RATIO = 0.35            # ...sous 35 % de son pic (sinon voix / musique)
NOISE_ALPHA = 0.995           # vitesse d'adaptation au bruit de fond


def _env_float(name: str, default: float) -> float:
    try:
        return float((os.environ.get(name) or "").strip() or default)
    except ValueError:
        return default


MIN_RMS = _env_float("JARVIS_MIN_RMS", 0.12)   # plancher absolu de volume
MUSIC_LEAD_S = _env_float("JARVIS_MUSIQUE_AVANCE", MUSIC_LEAD_S)
# décalage du départ de la musique par rapport à la fin de l'intro (0 = pile ; -0.3 = un poil avant)
MUSIC_DELAY_S = _env_float("JARVIS_MUSIQUE_DECALAGE", 0.0)
MUSIC_MINIMIZE_AFTER_S = _env_float("JARVIS_MUSIQUE_REDUIRE_APRES", 3.0)   # délai de secours si le son ne peut pas être mesuré
DEBUG = (os.environ.get("JARVIS_DEBUG") or "").strip().lower() in ("1", "true", "yes", "on")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("jarvis")


# ============================================================================
# Détection : double clap, filtré par la FORME du son
# ============================================================================
def rms(block: np.ndarray) -> float:
    if block.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(block.astype(np.float64) ** 2)))


class ClapDetector:
    """Reçoit le niveau (RMS) de chaque bloc de 10 ms ; feed() renvoie True au double clap.

    Quand un pic dépasse le seuil, on n'agit pas tout de suite : on attend 100 ms
    et on vérifie que le niveau est retombé sous 35 % du pic. Un clap retombe
    presque instantanément ; une voix ou de la musique reste forte.
    """

    def __init__(self) -> None:
        self.noise = 1e-4
        self.first: float | None = None
        self.verify: dict | None = None
        self.n = 0
        self.block_s = BLOCK_MS / 1000.0
        self.n_decay = max(2, round(DECAY_CHECK_S / self.block_s))
        self._last_low_log = -10.0

    @property
    def threshold(self) -> float:
        return max(MIN_RMS, self.noise * SPIKE_RATIO)

    def feed(self, level: float) -> bool:
        self.n += 1
        now = self.n * self.block_s

        if self.verify is not None:
            v = self.verify
            v["peak"] = max(v["peak"], level)
            v["tail"].append(level)
            if len(v["tail"]) < self.n_decay:
                return False
            self.verify = None
            after = max(v["tail"][-2:])
            is_clap = after < DECAY_RATIO * v["peak"]
            if DEBUG:
                log.info(
                    "pic : niveau=%.3f  seuil=%.3f  après 100ms=%.3f (%.0f%% du pic)  -> %s",
                    v["peak"], v["thr"], after, 100 * after / max(v["peak"], 1e-9),
                    "CLAP" if is_clap else "ignoré (voix ou musique)",
                )
            if not is_clap:
                return False
            if self.first is not None and MIN_GAP_S <= v["t"] - self.first <= MAX_GAP_S:
                self.first = None
                return True
            self.first = v["t"]
            return False

        thr = self.threshold
        if level >= thr:
            self.verify = {"t": now, "peak": level, "tail": [], "thr": thr}
            return False

        # Silence relatif : on adapte le bruit de fond et on oublie un 1er clap trop ancien
        if level < thr * 0.5:
            self.noise = NOISE_ALPHA * self.noise + (1 - NOISE_ALPHA) * level
            self.noise = max(self.noise, 1e-7)
        if self.first is not None and now - self.first > MAX_GAP_S:
            self.first = None
        if DEBUG and level >= thr * 0.5 and now - self._last_low_log > 0.3:
            self._last_low_log = now
            log.info("bruit : niveau=%.3f  seuil=%.3f  (trop faible pour un clap)", level, thr)
        return False


def _hostapi_name(dev: dict) -> str:
    try:
        return sd.query_hostapis(dev["hostapi"])["name"]
    except Exception:  # noqa: BLE001
        return ""


def _usable_inputs() -> list[int]:
    """Micros utilisables (on écarte les pilotes WDM-KS, incompatibles). MME / DirectSound / WASAPI."""
    return [
        i for i, d in enumerate(sd.query_devices())
        if d["max_input_channels"] >= 1 and "WDM-KS" not in _hostapi_name(d)
    ]


def _compatible_twin(idx: int) -> int | None:
    """Pour un micro WDM-KS, retrouve le même micro dans une API compatible (nom tronqué par Windows)."""
    base = sd.query_devices(idx)["name"].lower()[:20]
    for i in _usable_inputs():
        if base and base in sd.query_devices(i)["name"].lower():
            return i
    return None


def pick_input_device() -> tuple[int, int]:
    """Renvoie (index du micro, fréquence d'échantillonnage native du micro)."""
    if DEBUG:
        log.info("Périphériques audio :\n%s", sd.query_devices())
    override = (os.environ.get("JARVIS_INPUT_DEVICE") or "").strip()
    idx = None
    if override:
        if override.isdigit():
            idx = int(override)
            if "WDM-KS" in _hostapi_name(sd.query_devices(idx)):
                twin = _compatible_twin(idx)
                if twin is not None:
                    log.info("Le micro [%d] est incompatible (WDM-KS) : j'utilise son équivalent [%d].", idx, twin)
                    idx = twin
                else:
                    log.warning("Le micro [%d] est incompatible (WDM-KS) : j'utilise le micro par défaut de Windows.", idx)
                    idx = None
        else:
            for i in _usable_inputs():
                if override.lower() in sd.query_devices(i)["name"].lower():
                    idx = i
                    break
        if idx is None and not override.isdigit():
            log.warning("Micro %r introuvable : j'utilise le micro par défaut de Windows.", override)
    if idx is None:
        idx = sd.default.device[0]
        if idx is None or idx < 0:
            log.error("Aucun micro par défaut trouvé dans Windows.")
            raise SystemExit(1)
    dev = sd.query_devices(idx)
    rate = int(dev["default_samplerate"])  # on s'aligne sur le micro (44100, 48000...)
    log.info("Micro : [%d] %s (%d Hz, %s)", idx, dev["name"], rate, _hostapi_name(dev))
    return idx, rate


def wait_for_launch() -> bool:
    """Lancement : « salut Jarvis » (défaut) ou double clap (JARVIS_LANCEMENT=clap dans .env).
    Renvoie False si on a dit « fin de programme »."""
    if (os.environ.get("JARVIS_LANCEMENT") or "mot").strip().lower() != "clap":
        try:
            import assistant

            idx, rate = pick_input_device()
            return assistant.wait_launch_word(idx, rate)
        except (ImportError, FileNotFoundError) as e:
            log.warning("Lancement à la voix impossible (%s) : je repasse au double clap.", e)
    wait_for_double_clap()
    return True


def wait_for_double_clap() -> None:
    idx, rate = pick_input_device()
    block = max(1, int(rate * BLOCK_MS / 1000))
    det = ClapDetector()
    log.info(
        "J'écoute. Claque deux fois des mains. (seuil mini %.2f%s) Ctrl+C pour arrêter.",
        MIN_RMS, ", mode debug ACTIVÉ" if DEBUG else "",
    )
    with sd.InputStream(
        device=idx, samplerate=rate, channels=1, dtype="float32", blocksize=block
    ) as stream:
        while True:
            data, _ = stream.read(block)
            if det.feed(rms(data)):
                log.info("Double clap détecté !")
                return


# ============================================================================
# Voix ElevenLabs (avec cache : la voix part instantanément ensuite)
# ============================================================================
def _voice_config() -> tuple[str, str, str, int]:
    voice = (os.environ.get("ELEVENLABS_VOICE_ID") or "").strip()
    model = (os.environ.get("ELEVENLABS_MODEL_ID") or "eleven_multilingual_v2").strip()
    fmt = "pcm_24000"
    return voice, model, fmt, 24000


def _cache_path(voice: str, model: str, fmt: str) -> Path:
    key = f"{WELCOME_PHRASE}|{voice}|{model}|{fmt}".encode()
    return BASE / ".cache" / "jarvis_welcome" / f"{hashlib.sha256(key).hexdigest()[:24]}.wav"


_voice_lock = threading.Lock()


def ensure_voice_audio() -> Path | None:
    """S'assure que la phrase est en cache (appel API seulement la 1re fois)."""
    with _voice_lock:
        return _ensure_voice_audio()


def _ensure_voice_audio() -> Path | None:
    voice, model, fmt, rate = _voice_config()
    if not voice:
        log.warning("ELEVENLABS_VOICE_ID manquant : lance configurer_voix.bat.")
        return None
    path = _cache_path(voice, model, fmt)
    if path.is_file():
        return path
    api_key = (os.environ.get("ELEVENLABS_API_KEY") or "").strip()
    if not api_key:
        log.warning("ELEVENLABS_API_KEY manquante : lance configurer_voix.bat.")
        return None
    try:
        from elevenlabs.client import ElevenLabs

        client = ElevenLabs(api_key=api_key)
        chunks = client.text_to_speech.convert(
            voice_id=voice, text=WELCOME_PHRASE, model_id=model, output_format=fmt
        )
        raw = b"".join(chunks)
    except Exception as e:  # noqa: BLE001
        if getattr(e, "status_code", None) == 402 or "402" in str(e):
            log.warning(
                "ElevenLabs refuse cette voix (erreur 402). Sur le plan gratuit, les voix de la "
                "Voice Library sont refusées : choisis une voix native (My Voices / Default)."
            )
        else:
            log.warning("ElevenLabs a échoué : %s", e)
        return None
    if not raw:
        log.warning("ElevenLabs a renvoyé un audio vide.")
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with wave.open(str(tmp), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(raw)
    tmp.replace(path)
    log.info("Voix mise en cache : %s", path.name)
    return path


def say_welcome() -> None:
    path = ensure_voice_audio()
    if path is None:
        return
    try:
        with wave.open(str(path), "rb") as wf:
            rate = wf.getframerate()
            raw = wf.readframes(wf.getnframes())
        pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        sd.play(pcm, rate)
        sd.wait()
    except Exception as e:  # noqa: BLE001
        log.warning("Lecture de la voix impossible : %s", e)


# ============================================================================
# Son futuriste (synthétisé : montée en puissance + carillon), joué avant la musique
# ============================================================================
def make_boot_sound(rate: int = 44100) -> np.ndarray:
    dur, sweep = 2.6, 1.3
    t = np.linspace(0, dur, int(rate * dur), endpoint=False)
    f0, f1 = 90.0, 1500.0
    k = np.log(f1 / f0) / sweep
    phase = 2 * np.pi * f0 * (np.exp(k * np.minimum(t, sweep)) - 1) / k
    rise = np.clip(t / sweep, 0, 1) ** 1.6
    fall = np.where(t > sweep, np.exp(-(t - sweep) * 6), 1.0)
    wave_ = (np.sin(phase) + 0.45 * np.sin(2.01 * phase) + 0.25 * np.sin(3.02 * phase)) * rise * fall
    sub = 0.6 * np.sin(2 * np.pi * 55 * t) * rise * np.where(t > sweep, np.exp(-(t - sweep) * 3), 1.0)
    chime = np.zeros_like(t)
    for i, f in enumerate((880.0, 1318.5, 1760.0)):
        t0 = sweep - 0.05 + i * 0.07
        tt = np.clip(t - t0, 0, None)
        chime += np.where(t >= t0, np.sin(2 * np.pi * f * tt) * np.exp(-tt * 4.5), 0.0) * (0.55 - 0.1 * i)
    dry = wave_ * 0.5 + sub + chime
    out = dry.copy()
    for delay, gain in ((0.17, 0.35), (0.34, 0.22), (0.51, 0.12)):  # petit écho « spatial »
        d = int(delay * rate)
        out[d:] += dry[:-d] * gain
    out *= np.minimum(1.0, t / 0.01) * np.minimum(1.0, (dur - t) / 0.2)
    out = out / max(1e-9, float(np.max(np.abs(out)))) * 0.6
    return out.astype(np.float32)


_boot_sound: np.ndarray | None = None


def warm_boot_sound() -> None:
    """Calcule le son à l'avance pour qu'il parte instantanément au double clap."""
    global _boot_sound
    if _boot_sound is None:
        _boot_sound = make_boot_sound()


def play_boot_sound() -> None:
    try:
        warm_boot_sound()
        sd.play(_boot_sound, 44100)
        sd.wait()
    except Exception as e:  # noqa: BLE001
        log.warning("Son de démarrage impossible : %s", e)


# ============================================================================
# Elo FACEIT (API officielle ; nécessite FACEIT_API_KEY dans .env)
# ============================================================================
def fetch_faceit_stats() -> None:
    cache = BASE / ".cache" / "faceit.json"
    try:                                           # dernière valeur connue : affichée tout de suite
        FACEIT_DATA.update(json.loads(cache.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    key = (os.environ.get("FACEIT_API_KEY") or "").strip()
    if not key:
        if not FACEIT_DATA.get("elo"):
            FACEIT_DATA["note"] = "CLÉ FACEIT À CONFIGURER"
        return

    def call(url: str) -> dict:
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {key}", "Accept": "application/json", "User-Agent": "Mozilla/5.0 Jarvis"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read().decode("utf-8"))

    try:
        player = call(f"https://open.faceit.com/data/v4/players?nickname={FACEIT_NICK}")
        games = player.get("games") or {}
        game_id = "cs2" if "cs2" in games else ("csgo" if "csgo" in games else "")
        g = games.get(game_id) or {}
        data = {"elo": g.get("faceit_elo"), "level": g.get("skill_level")}
        try:
            life = call(f"https://open.faceit.com/data/v4/players/{player['player_id']}/stats/{game_id}").get("lifetime") or {}
            data.update(kd=life.get("Average K/D Ratio"), winrate=life.get("Win Rate %"), matches=life.get("Matches"))
        except Exception as e:  # noqa: BLE001 - les stats détaillées sont facultatives
            log.info("Stats FACEIT détaillées indisponibles : %s", e)
        if not data["elo"]:
            raise ValueError("elo introuvable (profil sans partie CS2 ?)")
        FACEIT_DATA.clear()
        FACEIT_DATA.update(data)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(data), encoding="utf-8")
        log.info("FACEIT : %s elo, niveau %s", data["elo"], data["level"])
    except Exception as e:  # noqa: BLE001
        log.warning("FACEIT indisponible : %s", e)
        if not FACEIT_DATA.get("elo"):
            FACEIT_DATA["note"] = "FACEIT INDISPONIBLE"


# ============================================================================
# Écrans et fenêtres (Windows)
# ============================================================================
def _monitors() -> list[tuple[int, int, int, int]]:
    rects: list[tuple[int, int, int, int]] = []

    @ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC,
        ctypes.POINTER(wintypes.RECT), wintypes.LPARAM,
    )
    def cb(_hm, _hdc, lprc, _lp):
        r = lprc.contents
        rects.append((int(r.left), int(r.top), int(r.right), int(r.bottom)))
        return True

    ctypes.windll.user32.EnumDisplayMonitors(None, None, cb, 0)
    return rects


def get_screens() -> tuple[tuple[int, int, int, int], tuple[int, int, int, int]]:
    """(écran principal, deuxième écran). Le principal est celui qui contient (0,0).
    Le deuxième écran peut être à gauche, à droite, au-dessus... (le plus à gauche s'il y en a plusieurs)."""
    rects = _monitors() or [(0, 0, 1920, 1080)]
    main = next((r for r in rects if r[0] == 0 and r[1] == 0), rects[0])
    others = [r for r in rects if r != main]
    if not others:
        log.warning("Je ne vois qu'un seul écran : tout ira dessus.")
        return main, main
    return main, min(others, key=lambda r: r[0])


def _windows_of(exe_name: str, min_w: int = 80, min_h: int = 80) -> dict[int, int]:
    """Fenêtres principales d'un programme : {hwnd: surface}."""
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD),
    ]
    user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    found: dict[int, int] = {}
    wanted = exe_name.lower()

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def enum(hwnd, _lp):
        if user32.GetWindow(hwnd, 4):                      # fenêtre « possédée »
            return True
        if user32.GetWindowLongW(hwnd, -20) & 0x80:         # fenêtre outil
            return True
        if not user32.IsWindowVisible(hwnd) and not user32.IsIconic(hwnd):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return True
        hproc = kernel32.OpenProcess(0x1000, False, pid.value)
        if not hproc:
            return True
        try:
            buf = ctypes.create_unicode_buffer(4096)
            size = wintypes.DWORD(len(buf))
            if not kernel32.QueryFullProcessImageNameW(hproc, 0, buf, ctypes.byref(size)):
                return True
            exe = buf.value
        finally:
            kernel32.CloseHandle(hproc)
        if os.path.basename(exe).lower() != wanted:
            return True
        r = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(r)):
            return True
        w, h = r.right - r.left, r.bottom - r.top
        if w >= min_w and h >= min_h:
            found[int(hwnd)] = w * h
        return True

    user32.EnumWindows(enum, 0)
    return found


def _wait_window(exe: str, before: set[int], timeout: float, min_w=80, min_h=80,
                 accept_existing_after: float | None = None) -> int | None:
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        time.sleep(0.15)
        now = _windows_of(exe, min_w, min_h)
        new = {h: a for h, a in now.items() if h not in before}
        if new:
            return max(new, key=new.get)
        if accept_existing_after is not None and now and time.monotonic() - start > accept_existing_after:
            return max(now, key=now.get)
    return None


def _place(hwnd: int, rect: tuple[int, int, int, int], maximize: bool) -> None:
    user32 = ctypes.windll.user32
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetWindowPos.argtypes = [
        wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, wintypes.UINT,
    ]
    l, t, r, b = rect
    user32.ShowWindow(hwnd, 9)                                   # restaurer
    user32.SetWindowPos(hwnd, None, l, t, r - l, b - t, 0x0040)  # placer sur l'écran
    if maximize:
        user32.ShowWindow(hwnd, 3)                               # plein écran de l'écran


def _chrome_exe() -> str | None:
    for base in (
        os.environ.get("ProgramFiles", r"C:\Program Files"),
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        os.environ.get("LOCALAPPDATA", ""),
    ):
        if base:
            p = os.path.join(base, "Google", "Chrome", "Application", "chrome.exe")
            if os.path.isfile(p):
                return p
    return None


def _select_first_tab(hwnd: int) -> None:
    """Met la fenêtre au premier plan et active son premier onglet (Ctrl+1)."""
    user32 = ctypes.windll.user32
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
    fg = user32.GetForegroundWindow()
    tid_tgt = user32.GetWindowThreadProcessId(hwnd, None)
    tid_fg = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    if tid_fg and tid_tgt:
        user32.AttachThreadInput(tid_fg, tid_tgt, True)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.25)
    if user32.GetForegroundWindow() == hwnd:           # on n'envoie la touche que si Chrome est bien devant
        for vk, up in ((0x11, 0), (0x31, 0), (0x31, 2), (0x11, 2)):
            user32.keybd_event(vk, 0, up, 0)
    if tid_fg and tid_tgt:
        user32.AttachThreadInput(tid_fg, tid_tgt, False)


def open_in_chrome(urls, rect: tuple[int, int, int, int], maximize: bool, label: str,
                   first_tab_active: bool = False) -> int | None:
    """Ouvre une fenêtre Chrome ; plusieurs adresses = plusieurs onglets dans la même fenêtre."""
    urls = [urls] if isinstance(urls, str) else list(urls)
    chrome = _chrome_exe()
    if not chrome:
        log.warning("Chrome introuvable : j'ouvre %s dans le navigateur par défaut.", label)
        for u in urls:
            webbrowser.open(u)
        return None
    before = set(_windows_of("chrome.exe"))
    subprocess.Popen(
        [chrome, "--new-window", "--autoplay-policy=no-user-gesture-required", *urls],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    hwnd = _wait_window("chrome.exe", before, 25)
    if hwnd:
        _place(hwnd, rect, maximize)
        if first_tab_active and len(urls) > 1:
            time.sleep(1.5)                            # laisse les onglets s'ouvrir
            _select_first_tab(hwnd)
    else:
        log.warning("Fenêtre Chrome introuvable pour %s (je n'ai pas pu la placer).", label)
    return hwnd


class _AudioMeter:
    """Niveau du son qui sort du PC (API Windows, sans module à installer) : sert à savoir si la musique joue."""

    def __init__(self) -> None:
        import uuid

        ole32 = ctypes.windll.ole32
        ole32.CoInitializeEx(None, 0)

        def guid(s: str):
            return (ctypes.c_byte * 16).from_buffer_copy(uuid.UUID(s).bytes_le)

        self._vt = lambda obj, i, *types: ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, *types)(
            ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0][i])
        enum = ctypes.c_void_p()
        hr = ole32.CoCreateInstance(ctypes.byref(guid("BCDE0395-E52F-467C-8E3D-C4579291692E")), None, 1 | 4 | 16,
                                    ctypes.byref(guid("A95664D2-9614-4F35-A746-DE8DB63617E6")), ctypes.byref(enum))
        if hr != 0:
            raise OSError(f"MMDeviceEnumerator {hr:#x}")
        dev = ctypes.c_void_p()
        self._vt(enum, 4, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p))(enum, 0, 0, ctypes.byref(dev))
        self.meter = ctypes.c_void_p()
        hr = self._vt(dev, 3, ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))(
            dev, ctypes.byref(guid("C02216F6-8C67-4B5B-9D00-D008E73E0064")), 23, None, ctypes.byref(self.meter))
        if hr != 0:
            raise OSError(f"IAudioMeterInformation {hr:#x}")
        self._peak = self._vt(self.meter, 3, ctypes.POINTER(ctypes.c_float))

    def peak(self) -> float:
        v = ctypes.c_float()
        self._peak(self.meter, ctypes.byref(v))
        return float(v.value)

    def wait_sound(self, timeout: float, level: float = 0.01) -> bool:
        """True dès qu'on entend du son ~0,3 s d'affilée."""
        end, run = time.monotonic() + timeout, 0
        while time.monotonic() < end:
            run = run + 1 if self.peak() > level else 0
            if run >= 6:
                return True
            time.sleep(0.05)
        return False


def _force_foreground(hwnd: int) -> None:
    """Met vraiment la fenêtre devant (Windows bloque souvent les programmes en arrière-plan)."""
    user32 = ctypes.windll.user32
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
    h = wintypes.HWND(hwnd)
    user32.ShowWindow(h, 9)                                          # restaurer si réduite
    fg = user32.GetForegroundWindow()
    t_fg = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    t_me = ctypes.windll.kernel32.GetCurrentThreadId()
    if t_fg and t_fg != t_me:
        user32.AttachThreadInput(t_me, t_fg, True)
    user32.keybd_event(0x12, 0, 0, 0)                                # Alt : débloque le premier plan
    user32.keybd_event(0x12, 0, 2, 0)
    user32.SetForegroundWindow(h)
    user32.BringWindowToTop(h)
    if t_fg and t_fg != t_me:
        user32.AttachThreadInput(t_me, t_fg, False)


def _click_video(hwnd: int) -> None:
    """Clique au centre du lecteur YouTube (comme si tu cliquais toi-même pour lancer la vidéo)."""
    user32 = ctypes.windll.user32
    r = wintypes.RECT()
    user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    x, y = r.left + int(w * 0.33), r.top + int(h * 0.38)             # lecteur : en haut à gauche de la page
    old = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(old))
    user32.SetCursorPos(x, y)
    time.sleep(0.05)
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    user32.mouse_event(0x0004, 0, 0, 0, 0)
    time.sleep(0.05)
    user32.SetCursorPos(old.x, old.y)


def start_music_then_minimize(hwnd: int | None) -> None:
    """Lance VRAIMENT la musique, puis réduit sa fenêtre (FACEIT reste affiché)."""
    if not hwnd:
        return
    try:
        _start_music_then_minimize(hwnd)
    except Exception:  # noqa: BLE001
        log.warning("Contrôle de la musique en échec : délai fixe.", exc_info=True)
        _force_foreground(hwnd)
        time.sleep(MUSIC_MINIMIZE_AFTER_S)
        ctypes.windll.user32.ShowWindow(wintypes.HWND(hwnd), 6)


def _start_music_then_minimize(hwnd: int) -> None:
    try:
        meter = _AudioMeter()
    except Exception as e:  # noqa: BLE001
        log.info("Mesure du son indisponible (%s) : délai fixe.", e)
        meter = None
    _force_foreground(hwnd)
    if meter is None:
        time.sleep(MUSIC_MINIMIZE_AFTER_S)
    elif not meter.wait_sound(4.0):
        log.info("La musique ne démarre pas toute seule : je clique sur la vidéo.")
        _force_foreground(hwnd)
        time.sleep(0.3)
        _click_video(hwnd)
        if not meter.wait_sound(5.0):
            log.warning("Toujours pas de son : je laisse la fenêtre de la musique ouverte.")
            return
    time.sleep(0.4)
    ctypes.windll.user32.ShowWindow(wintypes.HWND(hwnd), 6)          # réduite : la musique continue
    log.info("Musique lancée, fenêtre réduite.")


def _local_intro_track():
    """Musique de l'intro stockée sur le PC (dossier « musique » de Jarvis), sinon None -> YouTube."""
    try:
        import local_music
        return local_music.intro_track()
    except Exception:  # noqa: BLE001
        log.warning("Musique locale indisponible", exc_info=True)
        return None


def _play_local(path) -> None:
    import local_music
    log.info("Musique de l'intro (sur le PC) : %s", local_music.player().play(path))


def _preload_local(path) -> None:
    """Charge le morceau pendant l'intro : il partira à la seconde près quand elle se termine."""
    try:
        import local_music
        local_music.player().preload(path)
    except Exception:  # noqa: BLE001
        log.warning("Préchargement de la musique impossible", exc_info=True)


def _minimize_music_later(hwnd: int | None, wait: bool = False) -> None:
    """(sans intro) Lance la musique puis réduit sa fenêtre, en arrière-plan ou tout de suite."""
    if wait:
        start_music_then_minimize(hwnd)
    else:
        threading.Thread(target=start_music_then_minimize, args=(hwnd,), daemon=True).start()


def _bring_to_front_exe(exe: str) -> None:
    """Met la plus grande fenêtre d'un programme au premier plan."""
    try:
        wins = _windows_of(exe)
        if wins:
            _select_first_tab_free(max(wins, key=wins.get))
    except Exception:  # noqa: BLE001
        pass


def _select_first_tab_free(hwnd: int) -> None:
    user32 = ctypes.windll.user32
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow(hwnd)


def open_discord(rect: tuple[int, int, int, int], maximize: bool = True) -> None:
    before = set(_windows_of("discord.exe", 500, 400))
    update = Path(os.environ.get("LOCALAPPDATA", "")) / "Discord" / "Update.exe"
    try:
        if update.is_file():
            subprocess.Popen(
                [str(update), "--processStart", "Discord.exe"],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        else:
            os.startfile("discord://")  # type: ignore[attr-defined]
    except OSError as e:
        log.warning("Impossible d'ouvrir Discord : %s", e)
        return
    hwnd = _wait_window("discord.exe", before, 40, 500, 400, accept_existing_after=3.0)
    if not hwnd:
        log.warning("Fenêtre Discord introuvable (je n'ai pas pu la placer).")
        return
    _place(hwnd, rect, maximize)
    _keep_placed("discord.exe", rect, DISCORD_HOLD_S)


DISCORD_HOLD_S = 25.0       # Discord remet sa propre taille en fin de chargement : on le surveille ce temps


def _is_placed(hwnd: int, rect: tuple[int, int, int, int]) -> bool:
    """La fenêtre est-elle en plein écran (agrandie) sur cet écran ?"""
    user32 = ctypes.windll.user32
    user32.IsZoomed.argtypes = [wintypes.HWND]
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    r = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(r)):
        return False
    cx, cy = (r.left + r.right) // 2, (r.top + r.bottom) // 2
    l, t, rr, b = rect
    return bool(user32.IsZoomed(hwnd)) and l <= cx < rr and t <= cy < b


def _keep_placed(exe: str, rect: tuple[int, int, int, int], seconds: float) -> None:
    """Remet la plus grande fenêtre du programme en plein écran sur l'écran voulu, tant qu'elle bouge
    (pendant `seconds`). Discord, après sa mise à jour, se redimensionne tout seul."""
    end, fixes = time.monotonic() + seconds, 0
    while time.monotonic() < end:
        time.sleep(0.5)
        wins = _windows_of(exe, 500, 400)
        if not wins:
            continue
        hwnd = max(wins, key=wins.get)                       # la vraie fenêtre (pas celle de mise à jour)
        if not _is_placed(hwnd, rect):
            _place(hwnd, rect, True)
            fixes += 1
    if fixes:
        log.info("Discord replacé %d fois sur le deuxième écran.", fixes)


# ============================================================================
# Le réveil
# ============================================================================
def _no_report(label: str, status: str = "OK") -> None:
    return None


def wake_up_desk(report=_no_report, reveal: threading.Event | None = None, finish=lambda: None,
                 end_at: float | None = None) -> None:
    """Réveil du bureau.

    Écran de gauche : Discord en entier.
    Écran principal : ton profil FACEIT ; la musique (YouTube) joue, sa fenêtre est réduite.
    Avec l'interface plein écran (reveal fourni), Discord s'ouvre derrière elle ; FACEIT se charge sous
    l'intro et apparaît quand elle s'efface.
    """
    t_start = time.monotonic()                                       # = début de l'intro
    main, left = get_screens()

    report("Système")
    play_boot_sound()                                                # bruit futuriste d'abord

    voice = threading.Thread(target=say_welcome, daemon=True)
    voice.start()                                                    # puis la voix
    report("Voix")

    if reveal is None:
        # Sans interface plein écran : FACEIT, la musique (réduite une fois lancée), puis Discord.
        open_in_chrome(FACEIT_URL, main, True, "FACEIT")
        local = _local_intro_track()
        if local:
            _play_local(local)
        else:
            log.info("Pas de musique d'intro : le dossier « musique » est vide.")
        open_discord(left, maximize=True)
    else:
        # Discord s'ouvre en arrière-plan : l'intro n'attend plus sa fenêtre (mise à jour Discord = longue attente)
        threading.Thread(target=open_discord, args=(left,), kwargs={"maximize": True}, daemon=True).start()
        report("Discord")
        local = _local_intro_track()                                 # ta musique, dans le dossier « musique »
        if local:
            _preload_local(local)                                    # chargée pendant l'intro : zéro retard
        report("FACEIT", "EN FILE")
        finish()                                                     # l'interface pourra se terminer
        # FACEIT se charge SOUS l'intro, quelques secondes avant sa fin : prêt quand elle s'efface.
        try:
            from hud import MIN_VISIBLE_S as intro_s
        except Exception:  # noqa: BLE001
            intro_s = 8.0
        # Sous l'intro : FACEIT d'abord, puis la musique par-dessus (Chrome ne lance une vidéo que si elle est visible)
        time.sleep(max(0.0, intro_s - MUSIC_LEAD_S - 1.0 - (time.monotonic() - t_start)))
        open_in_chrome(FACEIT_URL, main, True, "FACEIT")
        if end_at is not None:                                       # nouvelle intro : on connaît l'heure exacte
            time.sleep(max(0.0, end_at - time.time()))
        else:
            reveal.wait(timeout=120)                                 # ancienne intro : quand elle s'efface
        if local:
            _play_local(local)                                       # pile à la fin de l'intro
        else:
            log.info("Pas de musique d'intro : le dossier « musique » est vide (plus de YouTube).")
    voice.join(timeout=30)


def prepare_hud():
    """Construit l'interface (cachée) avant le clap : elle apparaîtra aussitôt après. None si impossible."""
    try:
        from hud import Hud

        main_scr, left_scr = get_screens()
        hud = Hud(main_scr, left_scr if left_scr != main_scr else None, user=USER_NAME, hidden=True)
        hud.faceit, hud.faceit_nick = FACEIT_DATA, FACEIT_NICK
        return hud
    except Exception as e:  # noqa: BLE001
        log.warning("Interface HUD indisponible (%s) : je continue sans.", e, exc_info=True)
        return None


def run_wake_sequence(prepared=None) -> threading.Thread | None:
    """Lance le réveil avec l'interface plein écran ; sans elle si elle n'est pas disponible.
    Rend la main dès que l'introduction s'efface : la musique, Chrome, Discord continuent en arrière-plan
    (fil renvoyé) pendant que la sphère de Jarvis apparaît."""
    hud = prepared
    if hud is None:
        th = threading.Thread(target=wake_up_desk, daemon=True)
        th.start()
        return th

    def worker() -> None:
        try:
            hud.started.wait(timeout=3)        # le son part pile avec la 1re image du chargement
            wake_up_desk(hud.post, hud.reveal, hud.finish)
        except Exception:  # noqa: BLE001
            log.exception("Erreur pendant le réveil")
        finally:
            hud.finish()

    th = threading.Thread(target=worker, daemon=True)
    th.start()
    hud.run()          # rend la main quand l'introduction a fini de s'effacer
    return th          # le réveil continue (musique, YouTube) en arrière-plan


def _start_web_intro():
    """Nouvelle intro (navigateur plein écran, lisse). Renvoie l'objet lancé, ou None -> ancienne intro."""
    if (os.environ.get("JARVIS_INTRO") or "").strip().lower() in ("classique", "ancienne", "tk"):
        return None
    try:
        import intro_web
        from hud import MIN_VISIBLE_S
    except Exception:  # noqa: BLE001
        log.warning("Nouvelle intro indisponible : ancienne intro.", exc_info=True)
        return None
    main_scr, side_scr = get_screens()
    fd = dict(FACEIT_DATA)
    params = {"user": USER_NAME, "nick": FACEIT_NICK}
    if fd.get("elo"):
        params.update(elo=fd.get("elo"), lvl=fd.get("level"), kd=fd.get("kd"), win=fd.get("winrate"),
                      matches=fd.get("matches"))
    try:
        intro = intro_web.WebIntro(main_scr, side_scr if side_scr != main_scr else None, params, MIN_VISIBLE_S)
        return intro if intro.start() else None
    except Exception:  # noqa: BLE001
        log.warning("Nouvelle intro en échec : ancienne intro.", exc_info=True)
        return None


def run_web_wake_sequence(intro) -> threading.Thread:
    """Réveil avec la nouvelle intro : le son part à l'instant commun t0, puis tout s'enchaîne comme avant."""
    reveal = threading.Event()

    def worker() -> None:
        time.sleep(max(0.0, intro.t0 - time.time()))
        try:
            # la musique part à l'instant exact où l'intro se termine (avant le fondu des fenêtres)
            wake_up_desk(reveal=reveal, end_at=intro.t0 + intro.duration + MUSIC_DELAY_S)
        except Exception:  # noqa: BLE001
            log.exception("Erreur pendant le réveil")

    th = threading.Thread(target=worker, daemon=True)
    th.start()
    intro.finish()                       # attend la fin de l'intro, fondu, fermeture
    reveal.set()
    return th


def run_demo() -> int:
    """Montre l'interface seule (sans claps, sans ouvrir d'applications) pour la tester."""
    intro = _start_web_intro()
    if intro is not None:
        def sound() -> None:
            time.sleep(max(0.0, intro.t0 - time.time()))
            play_boot_sound()
        threading.Thread(target=sound, daemon=True).start()
        intro.finish()
        show_orb_demo()
        return 0
    from hud import Hud

    main_scr, left_scr = get_screens()
    hud = Hud(main_scr, left_scr if left_scr != main_scr else None, user=USER_NAME)
    hud.faceit, hud.faceit_nick = FACEIT_DATA, FACEIT_NICK

    def worker() -> None:
        for label in ("Système", "Voix", "FACEIT", "Discord"):
            time.sleep(1.5)
            hud.post(label)
        hud.finish()

    threading.Thread(target=worker, daemon=True).start()
    hud.run()
    show_orb_demo()
    return 0


def show_orb_demo() -> None:
    """Après l'intro de démo : la sphère, qui passe par tous ses états (sans micro ni IA)."""
    try:
        import orb

        sphere = orb.Orb()
    except Exception:  # noqa: BLE001
        log.exception("Sphère de Jarvis indisponible")
        return
    p = sphere.presence
    p.pinned = True                                  # démo : toujours visible

    def cycle() -> None:
        steps = [("idle", None, 4), ("listening", None, 2), ("thinking", None, 2.5),
                 ("speak", "Bonsoir monsieur. Tous les systèmes sont opérationnels.", 4),
                 ("idle", "DÉMO : CTRL+C DANS LA CONSOLE POUR FERMER", 6)]
        while not sphere.stop:
            for mode, text, dur in steps:
                if mode == "speak":
                    p.speak_unknown(text)
                else:
                    p.set_state(mode, text)
                time.sleep(dur)

    import signal

    signal.signal(signal.SIGINT, lambda *_: sphere.request_close())
    threading.Thread(target=cycle, daemon=True).start()
    sphere.run()


ALREADY_RUNNING = 11
_MUTEX = None


def _kill_other_instances() -> None:
    """Ferme les AUTRES Jarvis encore ouverts (ancienne version cachée, fenêtre lancer.bat oubliée...).
    Sinon : deux Jarvis écoutent, deux musiques jouent, et « coupe la musique » n'arrête que la sienne."""
    me, parent = os.getpid(), os.getppid()
    ps = ("Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
          "Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, timeout=20,
                             creationflags=subprocess.CREATE_NO_WINDOW).stdout.decode("utf-8", "replace")
        procs = json.loads(out or "[]")
        procs = [procs] if isinstance(procs, dict) else procs
    except Exception:  # noqa: BLE001
        return
    for p in procs:
        pid, cmd = int(p.get("ProcessId") or 0), (p.get("CommandLine") or "").lower()
        if pid in (me, parent, 0) or "jarvis.py" not in cmd or "--demo" in cmd:
            continue
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True,
                       creationflags=subprocess.CREATE_NO_WINDOW)
        log.info("Ancien Jarvis encore ouvert (processus %d) : fermé.", pid)
    time.sleep(0.5)


def _single_instance() -> bool:
    """Un seul Jarvis à la fois (sinon deux Jarvis écoutent le micro et répondent ensemble)."""
    global _MUTEX
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _MUTEX = k32.CreateMutexW(None, False, "Local\\JarvisPrincipal")
    return ctypes.get_last_error() != 183


def main() -> int:
    if sys.platform != "win32":
        print("Cette version de Jarvis est faite pour Windows.")
        return 1
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # coordonnées d'écran réelles
    except Exception:  # noqa: BLE001
        pass
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass
    if sys.stderr is None:  # lancé sans fenêtre (démarrage de Windows) : on écrit dans un fichier
        logging.getLogger().addHandler(logging.FileHandler(BASE / "jarvis.log", encoding="utf-8"))

    sup = os.environ.get("JARVIS_SUPERVISE") == "1"
    if "--demo" not in sys.argv and (not sup or os.environ.get("JARVIS_PREMIER_LANCEMENT") == "1"):
        _kill_other_instances()                    # lancement à la main / démarrage : le plus récent gagne
    if "--demo" not in sys.argv and not _single_instance():
        log.warning("Jarvis tourne déjà (en arrière-plan ?) : arreter_jarvis.bat pour l'arrêter.")
        return ALREADY_RUNNING
    threading.Thread(target=fetch_faceit_stats, daemon=True).start()   # elo FACEIT en tâche de fond
    if "--demo" in sys.argv:
        try:
            return run_demo()
        except Exception:  # noqa: BLE001
            log.exception("L'interface n'a pas pu démarrer")
            return 1

    if "--assistant" in sys.argv:                      # directement l'assistant vocal (sans clap ni réveil)
        return start_assistant()

    # Tout est préparé avant le clap (voix, son, interface) : le réveil démarre alors instantanément.
    threading.Thread(target=ensure_voice_audio, daemon=True).start()
    threading.Thread(target=warm_boot_sound, daemon=True).start()
    prepared = prepare_hud()
    try:
        if not wait_for_launch():
            log.info("Arrêt.")
            return 0
    except KeyboardInterrupt:
        log.info("Arrêt.")
        return 0
    except sd.PortAudioError as e:
        log.error("Problème de micro : %s", e)
        return 1
    except Exception:  # noqa: BLE001  (micro perdu pendant l'attente...)
        log.exception("Écoute du mot de lancement interrompue")
        return 1
    intro = _start_web_intro()
    if intro is not None:
        if prepared is not None:                    # l'ancienne intro préparée ne servira pas
            try:
                prepared.root.destroy()
            except Exception:  # noqa: BLE001
                pass
        wake = run_web_wake_sequence(intro)
    else:
        wake = run_wake_sequence(prepared)
    rc = start_assistant()                 # la sphère apparaît tout de suite après l'introduction
    if wake is not None:
        wake.join(timeout=60)              # (seulement si l'assistant s'arrête : on laisse finir le réveil)
    return rc


def start_assistant() -> int:
    """Après le réveil : Jarvis écoute en continu (« Jarvis, ouvre Discord »...)."""
    try:
        import assistant
    except Exception:  # noqa: BLE001
        log.exception("Assistant vocal indisponible")
        return 1
    try:
        idx, rate = pick_input_device()
    except sd.PortAudioError as e:
        log.error("Problème de micro : %s", e)
        return 1

    # La sphère de Jarvis : invisible, elle apparaît en fondu quand tu dis « Jarvis »
    sphere = None
    if (os.environ.get("JARVIS_SPHERE") or "oui").strip().lower() not in ("non", "0", "off", "false"):
        try:
            import orb

            sphere = orb.Orb()
        except Exception:  # noqa: BLE001
            log.exception("Sphère de Jarvis indisponible : je continue sans.")
            sphere = None

    result = {"rc": 1}

    def listen() -> int:
        rc = _listen()
        result["rc"] = rc
        if sphere:
            if rc == assistant.STOP_EXIT:
                time.sleep(1.0)                                  # laisse la sphère s'effacer
            sphere.request_close()                               # fin ou panne : tout s'arrête (relance auto)
        return rc

    def _listen() -> int:
        try:
            return assistant.run(idx, rate, user=USER_NAME, clap_factory=ClapDetector, rms=rms,
                                 ui=sphere.presence if sphere else None)
        except KeyboardInterrupt:
            return 0
        except sd.PortAudioError as e:
            log.error("Problème de micro : %s", e)
            if sphere:
                sphere.presence.set_state("idle", "PROBLÈME DE MICRO")
            return 1
        except Exception:  # noqa: BLE001
            log.exception("L'assistant s'est arrêté")
            return 1

    if sphere is None:
        try:
            return listen()
        except KeyboardInterrupt:
            log.info("Arrêt.")
            return 0

    import signal

    def ctrl_c(*_a) -> None:
        result["rc"] = 0
        sphere.request_close()

    signal.signal(signal.SIGINT, ctrl_c)                                # Ctrl+C ferme proprement
    threading.Thread(target=listen, daemon=True).start()
    sphere.run()                                                        # jusqu'à la fermeture
    log.info("Arrêt.")
    return result["rc"]


if __name__ == "__main__":
    raise SystemExit(main())
