"""Plan de travail de Jarvis : « Jarvis, ouvre le plan de travail ».

Une interface plein écran (plan_de_travail.html, dans le navigateur en mode application) :
  - au chargement : un globe qui tourne puis zoome sur ta position ;
  - la sphère de Jarvis au centre (elle réagit quand il écoute, réfléchit, parle) ;
  - le journal de la conversation, un champ pour écrire à Jarvis, le lancement rapide de tes applis ;
  - la météo, ton agenda, les applis ouvertes, l'état du PC (processeur, mémoire, carte graphique, réseau).
Tout est local : un petit serveur sur ton PC (adresse secrète), aucune donnée envoyée ailleurs
(sauf la météo : open-meteo.com, et ta position approximative si tu ne l'as pas réglée : ip-api.com).

Réglages (.env) :
  JARVIS_ADRESSE=...                ton adresse (zoom final jusqu'à ta rue ; reste sur ton PC, jamais affichée)
  JARVIS_VILLE=...                  ou juste ta ville (sinon : position approximative d'après ta connexion)
  JARVIS_PLAN_APPS=Rocket League,Discord,Steam,Chrome,Spotify,YouTube,FACEIT,Netflix
  JARVIS_PLAN_ECRAN=principal | gauche
"""
from __future__ import annotations

import collections
import ctypes
import http.server
import json
import logging
import os
import secrets
import shutil
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from ctypes import wintypes
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger("jarvis")
BASE = Path(__file__).resolve().parent
PAGE = BASE / "plan_de_travail.html"
CACHE = BASE / ".cache"
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Jarvis"

# ============================================================================
# Journal de la conversation (rempli même quand le plan de travail est fermé)
# ============================================================================
LOG: collections.deque = collections.deque(maxlen=40)


def note(qui: str, texte: str) -> None:
    texte = (texte or "").strip()
    if texte:
        LOG.append({"qui": qui, "texte": texte[:400], "t": time.time()})


def fix_last_user(texte: str) -> None:
    """Remplace la dernière phrase « toi » (transcription rapide) par la transcription précise (Whisper)."""
    for m in reversed(LOG):
        if m["qui"] == "toi":
            m["texte"] = texte[:400]
            return


# ============================================================================
# Agenda + rappels vocaux
# ============================================================================
class Agenda:
    FILE = CACHE / "agenda.json"

    def __init__(self) -> None:
        self.lock = threading.Lock()
        try:
            self.items: list[dict] = json.loads(self.FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.items = []

    def _save(self) -> None:
        self.FILE.parent.mkdir(parents=True, exist_ok=True)
        self.FILE.write_text(json.dumps(self.items, ensure_ascii=False, indent=1), encoding="utf-8")

    @staticmethod
    def _parse(quand: str) -> datetime | None:
        q = (quand or "").strip().replace(" ", "T").replace("h", ":")
        for fmt, n in (("%Y-%m-%dT%H:%M:%S", 19), ("%Y-%m-%dT%H:%M", 16), ("%Y-%m-%d", 10)):
            try:
                d = datetime.strptime(q[:n], fmt)
                return d.replace(hour=9) if n == 10 else d          # date sans heure : 9 h
            except ValueError:
                continue
        return None

    def add(self, quand: str, quoi: str) -> str:
        d = self._parse(quand)
        if d is None:
            return "ÉCHEC : date illisible (format attendu : 2026-10-07T08:00)"
        if not (quoi or "").strip():
            return "ÉCHEC : que faut-il noter ?"
        with self.lock:
            self.items.append({"id": secrets.token_hex(4), "quand": d.isoformat(timespec="minutes"),
                               "quoi": quoi.strip(), "prevenu": []})
            self.items.sort(key=lambda e: e["quand"])
            self._save()
        return f"Noté : {quoi.strip()} le {d:%d/%m à %H:%M}"

    def remove(self, quoi: str) -> str:
        import difflib
        with self.lock:
            if not self.items:
                return "ÉCHEC : l'agenda est vide"
            best = max(self.items, key=lambda e: difflib.SequenceMatcher(None, quoi.lower(), e["quoi"].lower()).ratio()
                       + (1 if quoi[:10] and e["quand"].startswith(quoi[:10]) else 0))
            self.items.remove(best)
            self._save()
        return f"Retiré : {best['quoi']} ({best['quand'].replace('T', ' ')})"

    def upcoming(self, days: int = 14) -> list[dict]:
        now = datetime.now() - timedelta(hours=1)
        with self.lock:
            return [{"quand": e["quand"], "quoi": e["quoi"]} for e in self.items
                    if now <= (self._parse(e["quand"]) or now) <= now + timedelta(days=days)]

    def text(self) -> str:
        up = self.upcoming(30)
        return "; ".join(f"{e['quand'].replace('T', ' ')} : {e['quoi']}" for e in up) or "aucun rendez-vous"

    def reminders(self, say) -> None:
        """Toutes les 20 s : « dans dix minutes : ... » puis « c'est l'heure : ... »."""
        while True:
            time.sleep(20)
            now = datetime.now()
            changed = False
            with self.lock:
                for e in self.items:
                    d = self._parse(e["quand"])
                    if d is None:
                        continue
                    done = e.setdefault("prevenu", [])
                    if "10" not in done and timedelta(0) < d - now <= timedelta(minutes=10):
                        done.append("10")
                        changed = True
                        threading.Thread(target=say, args=(f"Monsieur, dans dix minutes : {e['quoi']}.",),
                                         daemon=True).start()
                    elif "0" not in done and timedelta(minutes=-5) <= now - d <= timedelta(minutes=5) and d <= now:
                        done.append("0")
                        changed = True
                        threading.Thread(target=say, args=(f"C'est l'heure, monsieur : {e['quoi']}.",),
                                         daemon=True).start()
                old = now - timedelta(days=2)
                keep = [e for e in self.items if (self._parse(e["quand"]) or now) >= old]
                if len(keep) != len(self.items):
                    self.items, changed = keep, True
                if changed:
                    self._save()


# ============================================================================
# Mesures du PC
# ============================================================================
class _FT(ctypes.Structure):
    _fields_ = [("lo", wintypes.DWORD), ("hi", wintypes.DWORD)]


class _MEM(ctypes.Structure):
    _fields_ = [("len", wintypes.DWORD), ("load", wintypes.DWORD), ("total", ctypes.c_ulonglong),
                ("avail", ctypes.c_ulonglong), ("pt", ctypes.c_ulonglong), ("pa", ctypes.c_ulonglong),
                ("vt", ctypes.c_ulonglong), ("va", ctypes.c_ulonglong), ("ve", ctypes.c_ulonglong)]


class Sensors:
    def __init__(self) -> None:
        self.data: dict = {}
        self._cpu_prev = None
        self._net_prev = None
        self._gpu_t = 0.0

    def _cpu(self) -> float | None:
        idle, kern, user = _FT(), _FT(), _FT()
        if not ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kern), ctypes.byref(user)):
            return None
        v = [x.hi << 32 | x.lo for x in (idle, kern, user)]
        prev, self._cpu_prev = self._cpu_prev, v
        if prev is None:
            return None
        di, dk, du = (a - b for a, b in zip(v, prev))
        total = dk + du
        return max(0.0, min(100.0, 100.0 * (total - di) / total)) if total else None

    def _ram(self) -> float | None:
        m = _MEM()
        m.len = ctypes.sizeof(_MEM)
        return float(m.load) if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)) else None

    def _net(self) -> tuple[float, float]:
        try:
            import psutil
            c = psutil.net_io_counters()
            now = (time.monotonic(), c.bytes_recv, c.bytes_sent)
        except Exception:  # noqa: BLE001
            return 0.0, 0.0
        prev, self._net_prev = self._net_prev, now
        if prev is None:
            return 0.0, 0.0
        dt = max(0.1, now[0] - prev[0])
        return (now[1] - prev[1]) * 8 / 1e6 / dt, (now[2] - prev[2]) * 8 / 1e6 / dt

    def _gpu(self) -> None:
        exe = shutil.which("nvidia-smi") or r"C:\Windows\System32\nvidia-smi.exe"
        try:
            out = subprocess.run([exe, "--query-gpu=name,utilization.gpu,temperature.gpu,memory.used,memory.total",
                                  "--format=csv,noheader,nounits"], capture_output=True, timeout=4,
                                 creationflags=CREATE_NO_WINDOW).stdout.decode("utf-8", "replace").strip()
            name, util, temp, used, total = [x.strip() for x in out.splitlines()[0].split(",")]
            self.data.update(gpu=float(util), temp=float(temp), vram=100 * float(used) / max(1.0, float(total)),
                             gpu_nom=name.replace("NVIDIA GeForce ", "").replace("NVIDIA ", ""))
        except Exception:  # noqa: BLE001
            pass

    def tick(self) -> dict:
        cpu = self._cpu()
        if cpu is not None:
            self.data["cpu"] = round(cpu, 1)
        ram = self._ram()
        if ram is not None:
            self.data["ram"] = ram
        try:
            du = shutil.disk_usage(os.environ.get("SystemDrive", "C:") + "\\")
            self.data["disk"] = round(100 * du.used / du.total)
        except OSError:
            pass
        d, u = self._net()
        self.data.update(down=round(d, 2), up=round(u, 2))
        if time.monotonic() - self._gpu_t > 2:
            self._gpu_t = time.monotonic()
            self._gpu()
        return dict(self.data)


# ============================================================================
# Position et météo
# ============================================================================
def _get_json(url: str, timeout: float = 10) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _geocode_address(addr: str) -> dict:
    """Adresse précise -> coordonnées. France : base officielle (api-adresse.data.gouv.fr), sinon OpenStreetMap."""
    try:
        r = _get_json("https://api-adresse.data.gouv.fr/search/?" + urllib.parse.urlencode({"q": addr, "limit": 1}))
        f = r["features"][0]
        if f["properties"].get("score", 0) >= 0.5:
            lon, lat = f["geometry"]["coordinates"]
            return {"ville": f["properties"].get("city", ""), "pays": "France", "lat": lat, "lon": lon}
    except Exception:  # noqa: BLE001
        pass
    r = _get_json("https://nominatim.openstreetmap.org/search?" +
                  urllib.parse.urlencode({"q": addr, "format": "json", "limit": 1, "addressdetails": 1}))[0]
    a = r.get("address", {})
    return {"ville": a.get("city") or a.get("town") or a.get("village") or "", "pays": a.get("country", ""),
            "lat": float(r["lat"]), "lon": float(r["lon"])}


def locate() -> dict:
    """Ta position : JARVIS_ADRESSE (précise, reste sur ton PC) > JARVIS_VILLE > approximation par internet."""
    f = CACHE / "lieu.json"
    addr = (os.environ.get("JARVIS_ADRESSE") or "").strip()
    city = (os.environ.get("JARVIS_VILLE") or "").strip()
    key = addr or city
    try:
        cached = json.loads(f.read_text(encoding="utf-8"))
        if (time.time() - cached.get("t", 0) < (30 * 86400 if addr else 86400)
                and cached.get("demande", "") == key):
            return cached
    except (OSError, ValueError):
        pass
    lieu = {}
    try:
        if addr:
            lieu = _geocode_address(addr)
        elif city:
            r = _get_json("https://geocoding-api.open-meteo.com/v1/search?" +
                          urllib.parse.urlencode({"name": city, "count": 1, "language": "fr"}))["results"][0]
            lieu = {"ville": r["name"], "pays": r.get("country", ""), "lat": r["latitude"], "lon": r["longitude"]}
        else:
            r = _get_json("http://ip-api.com/json/?lang=fr&fields=status,city,country,lat,lon")
            if r.get("status") == "success":
                lieu = {"ville": r["city"], "pays": r["country"], "lat": r["lat"], "lon": r["lon"]}
    except Exception as e:  # noqa: BLE001
        log.warning("Position introuvable (%s) : règle JARVIS_VILLE dans .env.", e)
    if lieu:
        lieu.update(t=time.time(), demande=key)
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps(lieu, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
    return lieu or {"ville": "", "pays": "", "lat": 46.5, "lon": 2.5}


JOURS = ["Lun.", "Mar.", "Mer.", "Jeu.", "Ven.", "Sam.", "Dim."]


def weather(lat: float, lon: float) -> dict:
    j = _get_json("https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode({
        "latitude": lat, "longitude": lon, "current": "temperature_2m,weather_code,wind_speed_10m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min", "timezone": "auto", "forecast_days": 4}))
    c, d = j.get("current", {}), j.get("daily", {})
    days = []
    for i in range(1, min(4, len(d.get("time", [])))):
        day = datetime.strptime(d["time"][i], "%Y-%m-%d")
        days.append({"j": JOURS[day.weekday()], "min": round(d["temperature_2m_min"][i]),
                     "max": round(d["temperature_2m_max"][i]), "code": d["weather_code"][i]})
    return {"temp": round(c.get("temperature_2m", 0)), "code": c.get("weather_code", 0),
            "vent": round(c.get("wind_speed_10m", 0)), "jours": days}


# ============================================================================
# Icônes des applis (celles de Windows)
# ============================================================================
class _GUID(ctypes.Structure):
    _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD), ("c", wintypes.WORD), ("d", ctypes.c_ubyte * 8)]

    def __init__(self, s: str) -> None:
        super().__init__()
        h = s.replace("-", "")
        self.a, self.b, self.c = int(h[:8], 16), int(h[8:12], 16), int(h[12:16], 16)
        for i in range(8):
            self.d[i] = int(h[16 + 2 * i:18 + 2 * i], 16)


def shell_icon_png(parsing_name: str, size: int = 64) -> bytes | None:
    """Icône Windows d'un programme / d'une appli du menu Démarrer, en PNG."""
    from PIL import Image
    import io
    ole32, shell32, gdi32, user32 = ctypes.windll.ole32, ctypes.windll.shell32, ctypes.windll.gdi32, ctypes.windll.user32
    ole32.CoInitializeEx(None, 2)
    shell32.SHCreateItemFromParsingName.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p, ctypes.POINTER(_GUID),
                                                    ctypes.POINTER(ctypes.c_void_p)]
    iid = _GUID("bcc18b79-ba16-442f-80c4-8a59c30c463b")          # IShellItemImageFactory
    ptr = ctypes.c_void_p()
    if shell32.SHCreateItemFromParsingName(parsing_name, None, ctypes.byref(iid), ctypes.byref(ptr)) != 0 or not ptr:
        return None
    vt = ctypes.cast(ctypes.cast(ptr, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))
    get_image = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, wintypes.SIZE, ctypes.c_int,
                                   ctypes.POINTER(wintypes.HBITMAP))(vt[3])
    release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vt[2])
    hbmp = wintypes.HBITMAP()
    try:
        if get_image(ptr, wintypes.SIZE(size, size), 0x4, ctypes.byref(hbmp)) != 0 or not hbmp:   # icône seule
            return None

        class BMIH(ctypes.Structure):
            _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                        ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                        ("biSizeImage", wintypes.DWORD), ("x", wintypes.LONG), ("y", wintypes.LONG),
                        ("u", wintypes.DWORD), ("i", wintypes.DWORD)]

        class BM(ctypes.Structure):
            _fields_ = [("t", wintypes.LONG), ("w", wintypes.LONG), ("h", wintypes.LONG), ("wb", wintypes.LONG),
                        ("p", wintypes.WORD), ("bpp", wintypes.WORD), ("bits", ctypes.c_void_p)]

        bm = BM()
        gdi32.GetObjectW(hbmp, ctypes.sizeof(BM), ctypes.byref(bm))
        w, h = bm.w, abs(bm.h)
        bi = BMIH(ctypes.sizeof(BMIH), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        buf = ctypes.create_string_buffer(w * h * 4)
        hdc = user32.GetDC(None)
        gdi32.GetDIBits(hdc, hbmp, 0, h, buf, ctypes.byref(bi), 0)
        user32.ReleaseDC(None, hdc)
        img = Image.frombuffer("RGBA", (w, h), buf.raw, "raw", "BGRA", 0, 1)
        if img.getextrema()[3][1] == 0:                       # icône sans transparence
            img.putalpha(255)
        out = io.BytesIO()
        img.save(out, "PNG")
        return out.getvalue()
    except Exception:  # noqa: BLE001
        return None
    finally:
        if hbmp:
            gdi32.DeleteObject(hbmp)
        release(ptr)


def favicon_png(domain: str) -> bytes | None:
    try:
        req = urllib.request.Request(f"https://www.google.com/s2/favicons?sz=64&domain={domain}",
                                     headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.read()
    except Exception:  # noqa: BLE001
        return None


FRIENDLY = {"discord": "Discord", "chrome": "Chrome", "msedge": "Edge", "firefox": "Firefox", "steam": "Steam",
            "steamwebhelper": "Steam", "spotify": "Spotify", "rocketleague": "Rocket League", "cs2": "Counter-Strike 2",
            "explorer": "Explorateur", "code": "VS Code", "obs64": "OBS Studio", "valorant-win64-shipping": "VALORANT",
            "riotclientux": "Riot Client", "epicgameslauncher": "Epic Games", "battle.net": "Battle.net",
            "winword": "Word", "excel": "Excel", "powerpnt": "PowerPoint", "notepad": "Bloc-notes",
            "faceit": "FACEIT", "faceitclient": "FACEIT", "teams": "Teams", "ms-teams": "Teams", "whatsapp": "WhatsApp",
            "vlc": "VLC", "medal": "Medal", "nvidia app": "NVIDIA App", "applicationframehost": ""}
GAMES = {"rocketleague", "cs2", "valorant-win64-shipping", "r5apex", "fortniteclient-win64-shipping", "leagueoflegends"}
SKIP = {"python", "pythonw", "py", "cmd", "conhost", "windowsterminal", "openconsole", "powershell", "textinputhost",
        "shellexperiencehost", "searchhost", "startmenuexperiencehost", "systemsettings", "lockapp"}


# ============================================================================
# Le plan de travail
# ============================================================================
class Workspace:
    def __init__(self) -> None:
        self.presence = None
        self.actions = None
        self.brain = None
        self.ask = None
        self.agenda = Agenda()
        self.sensors = Sensors()
        self.token = secrets.token_urlsafe(12)
        self.server: http.server.ThreadingHTTPServer | None = None
        self.proc: subprocess.Popen | None = None
        self.open_flag = threading.Event()
        self.state: dict = {"sys": {}, "actifs": [], "meteo": {}, "lieu": {}, "rapide": []}
        self.icons: dict[str, bytes | None] = {}
        self.icon_lock = threading.Lock()
        self.app_paths: dict[str, str] = {}
        self.boot_seq = 0                                  # +1 = la page rejoue l'animation du globe

    # --- branchement
    def attach(self, presence, actions, brain, ask, say) -> None:
        self.presence, self.actions, self.brain, self.ask = presence, actions, brain, ask
        threading.Thread(target=self.agenda.reminders, args=(say,), daemon=True).start()

    # --- données
    def _quick_apps(self) -> list[dict]:
        import assistant
        names = [n.strip() for n in (os.environ.get("JARVIS_PLAN_APPS") or
                                     "Rocket League,Discord,Steam,Chrome,Spotify,YouTube,FACEIT,Netflix").split(",")
                 if n.strip()]
        out = []
        apps = {}
        if self.actions is not None:
            with self.actions.apps.lock:
                apps = dict(self.actions.apps.items)
        for n in names:
            if n.lower() in assistant.SITES:
                out.append({"nom": n, "site": assistant.SITES[n.lower()]})
                continue
            best, score, _ = assistant.best_match_scored(n, list(apps)) if apps else (None, 0, [])
            if best and score >= 0.75:
                out.append({"nom": n, "appli": best, "id": apps[best]})
            elif not apps:
                out.append({"nom": n})
        return out

    def _active(self) -> list[dict]:
        import assistant
        fg = int(ctypes.windll.user32.GetForegroundWindow() or 0)
        seen: dict[str, dict] = {}
        for w in assistant.list_windows():
            stem = Path(w["exe"]).stem.lower()
            if stem in SKIP or w["titre"].startswith(("Plan de travail JARVIS", "Jarvis", "Intro Jarvis")):
                continue
            name = FRIENDLY.get(stem, stem.capitalize())
            if not name:
                continue
            if w.get("chemin"):
                self.app_paths[name] = w["chemin"]
            e = seen.setdefault(name, {"nom": name, "titre": "", "etat": "En ligne", "premier": False})
            if w["hwnd"] == fg or stem in GAMES:
                e.update(etat="En cours", premier=True, titre=w["titre"][:40])
        items = list(seen.values())
        items.sort(key=lambda e: not e["premier"])
        return items[:8]

    def _collect(self) -> None:
        """Tant que le plan de travail est ouvert : mesures (1 s), applis (2 s), météo (15 min)."""
        n, last_wx = 0, 0.0
        if not self.state.get("lieu"):
            self.state["lieu"] = locate()
        self.state["rapide"] = self._quick_apps()
        while self.open_flag.is_set():
            try:
                self.state["sys"] = self.sensors.tick()
                if n % 2 == 0:
                    self.state["actifs"] = self._active()
                if n % 30 == 0:
                    self.state["rapide"] = self._quick_apps()
                if time.time() - last_wx > 900:
                    last_wx = time.time()
                    lieu = self.state["lieu"]
                    try:
                        self.state["meteo"] = weather(lieu["lat"], lieu["lon"])
                    except Exception as e:  # noqa: BLE001
                        log.info("Météo indisponible : %s", e)
                        last_wx -= 840                         # on réessaie dans une minute
            except Exception:  # noqa: BLE001
                log.debug("Plan de travail : mesure impossible", exc_info=True)
            n += 1
            time.sleep(1)

    def snapshot(self) -> dict:
        p = self.presence
        mode, level, status, sub = "idle", 0.0, "", ""
        if p is not None:
            mode, level = p.level(time.monotonic())
            with p.lock:
                status, sub = p.status, p.subtitle
        llm = getattr(self.brain, "gemini", None)
        model = getattr(llm, "last_model", "") or getattr(llm, "model", "")
        local = getattr(llm, "local", False)
        hybrid = getattr(self.brain, "strong", None) is not None
        ia = (f"{model.split(':')[0].upper().replace('QWEN', 'QWEN ')} · {'HYBRIDE' if hybrid else 'LOCAL'}" if local
              else f"{(model or 'gemini').replace('gemini-', 'GEMINI ').replace('-latest', '').upper()}"
                   f"{' · HYBRIDE' if hybrid else ''}")
        user = getattr(self.brain, "user", "") or "Monsieur"
        return {**self.state, "boot": self.boot_seq, "mode": mode, "level": round(float(level), 3), "status": status, "sub": sub,
                "log": list(LOG)[-30:], "agenda": self.agenda.upcoming(), "user": user, "ia": ia,
                "latence": round(getattr(llm, "last_time", 0.0) or 0.0, 1), "micro": "ACTIF", "prudent": True}

    def icon(self, name: str) -> bytes | None:
        with self.icon_lock:
            if name in self.icons:
                return self.icons[name]
        data = None
        f = CACHE / "icones" / (urllib.parse.quote(name, safe="") + ".png")
        if f.is_file():
            data = f.read_bytes()
        else:
            q = next((a for a in self.state.get("rapide", []) if a["nom"] == name), None)
            try:
                if q and q.get("site"):
                    data = favicon_png(urllib.parse.urlparse(q["site"]).netloc)
                elif q and q.get("id"):
                    data = shell_icon_png("shell:AppsFolder\\" + q["id"])
                elif name in self.app_paths:
                    data = shell_icon_png(self.app_paths[name])
            except Exception:  # noqa: BLE001
                data = None
            if data:
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_bytes(data)
        with self.icon_lock:
            self.icons[name] = data
        return data

    def tile(self, path: str) -> bytes | None:
        """Morceau de carte OpenStreetMap (zoom final du globe) : téléchargé une fois, puis gardé sur le PC."""
        parts = path[len("tuile/"):].removesuffix(".png").split("/")
        try:
            z, x, y = (int(v) for v in parts)
        except ValueError:
            return None
        if not (0 <= z <= 18 and 0 <= x < 2 ** z and 0 <= y < 2 ** z):
            return None
        f = CACHE / "tuiles" / str(z) / str(x) / f"{y}.png"
        if f.is_file():
            return f.read_bytes()
        try:
            req = urllib.request.Request(f"https://tile.openstreetmap.org/{z}/{x}/{y}.png",
                                         headers={"User-Agent": "Jarvis-Klypp/1.0 (assistant personnel, usage privé)"})
            with urllib.request.urlopen(req, timeout=10) as r:
                data = r.read()
        except Exception:  # noqa: BLE001
            return None
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(data)
        return data

    # --- actions venant de la page
    def action(self, a: dict) -> str:
        t = a.get("type")
        if t == "journal":                                 # ce que fait la page (diagnostic dans jarvis.log)
            log.info("Plan de travail (page) : %s", str(a.get("texte", ""))[:200])
            return "ok"
        if t == "fermer":
            threading.Thread(target=self.close, daemon=True).start()
            return "ok"
        if t == "demande" and self.ask and a.get("texte"):
            self.ask(str(a["texte"])[:500])
            return "ok"
        if t == "ouvrir" and self.actions is not None:
            nom = str(a.get("nom", ""))
            special = {"Ce PC": "shell:MyComputerFolder", "Explorateur de fichiers": "explorer.exe",
                       "Paramètres": "ms-settings:"}
            if nom in special:
                subprocess.Popen(["explorer.exe", special[nom]] if nom != "Explorateur de fichiers" else ["explorer.exe"])
                return "ok"
            q = next((x for x in self.state.get("rapide", []) if x["nom"] == nom), None)
            if q and q.get("site"):
                out = self.actions.do_ouvrir_site(q["site"])
            else:
                out = self.actions.do_ouvrir_application((q or {}).get("appli") or nom)
            note("jarvis", f"Lancement de {nom}." if not out.startswith("ÉCHEC") else f"Impossible d'ouvrir {nom}.")
            return out
        return "inconnu"

    # --- serveur
    def _serve(self) -> int:
        ws, token = self, self.token

        class H(http.server.BaseHTTPRequestHandler):
            def _send(self, code: int, body: bytes, ctype: str) -> None:
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _path(self) -> str | None:
                url = urllib.parse.urlparse(self.path)
                prefix = f"/{token}/"
                return url.path[len(prefix):] if url.path.startswith(prefix) or url.path == prefix[:-1] else None

            def do_GET(self):  # noqa: N802
                p = self._path()
                if p is None:
                    return self._send(404, b"", "text/plain")
                if p in ("", "index.html"):
                    return self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
                if p == "etat":
                    return self._send(200, json.dumps(ws.snapshot(), ensure_ascii=False).encode("utf-8"),
                                      "application/json")
                if p.startswith("tuile/"):
                    data = ws.tile(p)
                    return self._send(200, data, "image/png") if data else self._send(404, b"", "text/plain")
                if p == "icone":
                    name = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("nom", [""])[0]
                    data = ws.icon(name)
                    return self._send(200, data, "image/png") if data else self._send(404, b"", "text/plain")
                return self._send(404, b"", "text/plain")

            def do_POST(self):  # noqa: N802
                if self._path() != "action":
                    return self._send(404, b"", "text/plain")
                try:
                    body = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length") or 0), 20000)))
                    out = ws.action(body)
                except Exception as e:  # noqa: BLE001
                    out = f"ÉCHEC : {e}"
                return self._send(200, json.dumps({"resultat": out}, ensure_ascii=False).encode("utf-8"),
                                  "application/json")

            def log_message(self, *_a):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self.server.server_address[1]

    # --- ouverture / fermeture
    def open(self) -> str:
        if not PAGE.is_file():
            return "ÉCHEC : plan_de_travail.html introuvable"
        if self.proc is not None and self.proc.poll() is None:
            self.boot_seq += 1                             # déjà ouvert : on le ramène devant et on rejoue le globe
            threading.Thread(target=self._bring_front, args=(5,), daemon=True).start()
            return "OK : plan de travail ramené devant (animation rejouée)"
        import intro_web
        br = intro_web.find_browser()
        if br is None:
            return "ÉCHEC : il faut Chrome ou Edge pour le plan de travail"
        port = self.server.server_address[1] if self.server else self._serve()
        url = f"http://127.0.0.1:{port}/{self.token}/"
        screen = (os.environ.get("JARVIS_PLAN_ECRAN") or "principal").strip().lower()
        try:
            import assistant
            mons = assistant.monitors()                    # principal d'abord, puis les autres de gauche à droite
            l, t, r, b = mons[1] if (screen in ("gauche", "secondaire", "autre") and len(mons) > 1) else mons[0]
        except Exception:  # noqa: BLE001
            l, t, r, b = 0, 0, 1920, 1080
        profile = CACHE / "plan_navigateur"
        profile.mkdir(parents=True, exist_ok=True)
        args = [br[0], f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check",
                "--disable-extensions", "--disable-sync", "--disable-features=Translate,MediaRouter",
                "--hide-crash-restore-bubble", f"--window-position={l},{t}", f"--window-size={r - l},{b - t}",
                "--start-fullscreen", f"--app={url}"]
        if not self.state.get("lieu"):
            self.state["lieu"] = locate()                   # position prête avant le globe
        self.open_flag.set()
        threading.Thread(target=self._collect, daemon=True).start()
        try:
            self.proc = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                         stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW)
        except OSError as e:
            self.open_flag.clear()
            return f"ÉCHEC : {e}"
        if self.presence is not None:
            self.presence.hidden = True                   # la sphère du bureau laisse la place à celle du plan
        threading.Thread(target=self._watch, daemon=True).start()
        threading.Thread(target=self._bring_front, args=(20,), daemon=True).start()
        log.info("Plan de travail ouvert.")
        return "OK : plan de travail ouvert (globe de chargement puis interface)"

    def _watch(self) -> None:
        p = self.proc
        if p is not None:
            p.wait()
        if self.proc is p:                                 # fermé à la main (Alt+F4...)
            self._closed()

    def _closed(self) -> None:
        self.open_flag.clear()
        self.proc = None
        if self.presence is not None:
            self.presence.hidden = False

    def _bring_front(self, wait: float) -> None:
        """Attend la fenêtre puis la met DEVANT (sinon Windows peut l'ouvrir derrière, et Chrome met
        l'animation en pause tant qu'elle est cachée)."""
        import assistant
        end = time.monotonic() + wait
        while time.monotonic() < end:
            w = next((x for x in assistant.list_windows() if x["titre"].startswith("Plan de travail JARVIS")), None)
            if w:
                u32 = ctypes.windll.user32
                u32.ShowWindow(w["hwnd"], 9)                                   # si réduite : on la restaure
                u32.SetWindowPos(w["hwnd"], wintypes.HWND(-1), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)   # devant tout
                assistant.focus(w["hwnd"])
                time.sleep(0.4)
                u32.SetWindowPos(w["hwnd"], wintypes.HWND(-2), 0, 0, 0, 0, 0x0001 | 0x0002)          # puis normale
                log.info("Plan de travail affiché au premier plan.")
                return
            time.sleep(0.3)
        log.warning("Fenêtre du plan de travail introuvable (Chrome/Edge a-t-il démarré ?).")

    def _focus(self) -> None:
        try:
            import assistant
            w = next((x for x in assistant.list_windows() if x["titre"].startswith("Plan de travail JARVIS")), None)
            if w:
                assistant.focus(w["hwnd"])
        except Exception:  # noqa: BLE001
            pass

    def close(self) -> str:
        p = self.proc
        if p is None or p.poll() is not None:
            self._closed()
            return "OK : le plan de travail était déjà fermé"
        self.proc = None
        try:
            subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True,
                           creationflags=CREATE_NO_WINDOW, timeout=10)
        except Exception:  # noqa: BLE001
            p.kill()
        self._closed()
        log.info("Plan de travail fermé.")
        return "OK : plan de travail fermé"

    @property
    def is_open(self) -> bool:
        return self.proc is not None and self.proc.poll() is None


_ws: Workspace | None = None


def workspace() -> Workspace:
    global _ws
    if _ws is None:
        _ws = Workspace()
    return _ws
