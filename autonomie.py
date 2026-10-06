"""Autonomie de Jarvis : internet, code, et compétences qu'il s'ajoute lui-même.

- chercher_web : il cherche sur internet (Google, via Gemini) et lit des pages.
- executer_code : il écrit un script Python pour une tâche, le lance, corrige ses erreurs tout seul.
- compétences : quand il ne sait pas faire quelque chose, il code un nouvel outil pour lui-même (dossier
  « competences »), le TESTE, puis s'en sert ; il le garde pour les fois suivantes.
- auto-amélioration : quand tu ne l'utilises pas, il relit ses échecs et tes corrections, en tire des leçons
  (mémoire) et se code de nouvelles compétences. « Jarvis, qu'est-ce que tu as appris ? »

Sécurité (volontaire) :
- il ne modifie JAMAIS son propre cœur (assistant.py, jarvis.py...) : une erreur et il ne démarrerait plus.
  Il grandit par compétences ajoutées à côté, chacune testée et isolée (si elle plante, Jarvis continue).
- tout code qui supprime, déplace, envoie ou touche au système demande ta confirmation à voix haute ;
  en auto-amélioration (sans toi), ce genre de code est tout simplement refusé.
- il n'installe que des paquets Python d'une liste connue.
- MODE PRUDENT : chaque script / compétence tourne avec un garde-fou (competences/_garde.py) qui bloque, sans
  ton accord : écrire ou supprimer hors de « espace_jarvis », lancer des programmes, envoyer des données,
  toucher au registre. Et toujours (même avec accord) : lire .env, mots de passe / cookies des navigateurs,
  token Discord, ou modifier Windows et le cœur de Jarvis.
- « Jarvis, stop total » : arrêt d'urgence de tout ce qu'il fait.  « annule ce que tu as appris » : retour arrière.
Réglages (.env) : JARVIS_AUTO_AMELIORATION=0 (désactiver), JARVIS_AMELIORATION_HEURES=6 (fréquence),
  JARVIS_DOSSIERS_AUTORISES=D:\\Photos;D:\\Projets (dossiers où ses scripts peuvent écrire sans demander).
"""
from __future__ import annotations

import html as htmlmod
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
import unicodedata
import urllib.request
from datetime import datetime
from pathlib import Path

log = logging.getLogger("jarvis")
BASE = Path(__file__).resolve().parent
COMP_DIR = BASE / "competences"
WORK_DIR = BASE / "espace_jarvis"                 # là où ses scripts ont le droit d'écrire
JOURNAL = BASE / ".cache" / "journal.jsonl"
LEARNED = BASE / ".cache" / "ameliorations.json"
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

ALLOWED_PACKAGES = {
    "requests", "beautifulsoup4", "lxml", "pillow", "psutil", "feedparser", "openpyxl", "python-docx",
    "python-pptx", "matplotlib", "numpy", "pandas", "qrcode", "yt-dlp", "pyperclip", "pywin32", "comtypes",
    "pycaw", "screen-brightness-control", "wmi", "send2trash", "pypdf", "reportlab", "markdown", "rapidfuzz",
}
# en auto-amélioration (sans toi), ces éléments sont refusés d'office
AUTO_FORBIDDEN = re.compile(r"\bctypes\b|\bsubprocess\b|os\.system|os\.startfile|\bwinreg\b|\bsocket\b|"
                            r"addaudithook|sys\.modules|importlib|__import__|\beval\(|\bexec\(|_garde")
DANGER = re.compile(
    r"os\.remove|os\.unlink|\.unlink\(|rmtree|os\.rmdir|\.rmdir\(|shutil\.move|os\.rename|\.rename\(|\.replace\(\s*['\"]?[A-Za-z]:|"
    r"send2trash|winreg|reg\s+(add|delete)|\bdel\s+/|\brd\s+/s|Remove-Item|shutdown|format\s+[a-z]:|smtplib|"
    r"\.post\(|method\s*=\s*['\"]POST|sendmail|webhook|bcdedit|vssadmin|cipher\s+/w|taskkill|Stop-Process",
    re.I)


def _slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")[:40] or "competence"


def _text(resp: dict) -> str:
    try:
        parts = resp["candidates"][0]["content"].get("parts") or []
    except (KeyError, IndexError):
        return ""
    return "".join(p.get("text", "") for p in parts if not p.get("thought"))


def _code(text: str) -> str:
    m = re.search(r"```(?:python|py)?\s*\n(.*?)```", text, re.S)
    return (m.group(1) if m else text).strip()


def _python() -> str:
    exe = Path(sys.executable)
    cand = exe.with_name("python.exe")
    return str(cand if cand.is_file() else exe)


HALT = threading.Event()                          # « Jarvis, stop total » : tout s'arrête
_procs: set = set()
_procs_lock = threading.Lock()


def emergency_stop() -> int:
    """Arrêt d'urgence : tue tous les scripts / compétences en cours et bloque les tâches de fond 1 minute."""
    HALT.set()
    threading.Timer(60, HALT.clear).start()
    n = 0
    with _procs_lock:
        for p in list(_procs):
            try:
                p.kill()
                n += 1
            except Exception:  # noqa: BLE001
                pass
    log.warning("ARRÊT D'URGENCE : %d programme(s) arrêté(s).", n)
    return n


def install_guard() -> None:
    COMP_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    for name, code in (("_garde.py", GUARD), ("_lancer_script.py", LAUNCHER), ("_runner.py", RUNNER)):
        f = COMP_DIR / name
        if not f.is_file() or f.read_text(encoding="utf-8") != code:
            f.write_text(code, encoding="utf-8")


def _run_py(args: list[str], stdin: str = "", timeout: float = 120, confirmed: bool = False,
            guarded: bool = True) -> tuple[int, str]:
    if HALT.is_set():
        return 1, "arrêt d'urgence en cours"
    install_guard()
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1", JARVIS_ESPACE=str(WORK_DIR),
               JARVIS_BASE=str(BASE), JARVIS_CONFIRME="1" if confirmed else "0")
    if guarded and args and args[0].endswith(".py") and not Path(args[0]).name.startswith("_"):
        args = [str(COMP_DIR / "_lancer_script.py"), *args]          # script : garde-fou d'abord
    try:
        p = subprocess.Popen([_python(), *args], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, cwd=WORK_DIR, env=env, creationflags=CREATE_NO_WINDOW)
    except OSError as e:
        return 1, str(e)
    with _procs_lock:
        _procs.add(p)
    try:
        out, _ = p.communicate(stdin.encode("utf-8"), timeout=timeout)
        return p.returncode, out.decode("utf-8", "replace")[-6000:]
    except subprocess.TimeoutExpired:
        p.kill()
        return 124, f"trop long (plus de {timeout:.0f} s), arrêté"
    finally:
        with _procs_lock:
            _procs.discard(p)


def _pip(packages: list[str]) -> str:
    bad = [p for p in packages if p.lower() not in ALLOWED_PACKAGES]
    if bad:
        return f"paquets refusés (pas dans la liste connue) : {', '.join(bad)}"
    if not packages:
        return ""
    rc, out = _run_py(["-m", "pip", "install", "--quiet", "--disable-pip-version-check", *packages], timeout=300,
                      guarded=False)
    return "" if rc == 0 else f"installation impossible : {out[-400:]}"


# ============================================================================
# Internet
# ============================================================================
def web_search(gemini, question: str) -> str:
    body = {"contents": [{"role": "user", "parts": [{"text":
            f"Cherche sur internet et réponds précisément, en français, avec les faits à jour (dates, chiffres) : "
            f"{question}"}]}], "tools": [{"google_search": {}}]}
    resp = gemini.generate(body, timeout=60)
    text = _text(resp).strip() or "Rien trouvé."
    try:
        chunks = resp["candidates"][0].get("groundingMetadata", {}).get("groundingChunks", [])
        src = [c["web"].get("title", "") for c in chunks if "web" in c][:4]
    except (KeyError, IndexError):
        src = []
    return text[:3000] + (f"\n(sources : {', '.join(s for s in src if s)})" if src else "")


def read_page(url: str) -> str:
    if not re.match(r"^https?://", url or ""):
        url = "https://" + (url or "").lstrip("/")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Jarvis"})
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = r.read(2_000_000).decode(r.headers.get_content_charset() or "utf-8", "replace")
    raw = re.sub(r"(?is)<(script|style|noscript|svg).*?</\1>", " ", raw)
    txt = htmlmod.unescape(re.sub(r"<[^>]+>", " ", raw))
    return re.sub(r"\s+", " ", txt).strip()[:8000] or "page vide"


# ============================================================================
# Code à la demande
# ============================================================================
SCRIPT_PROMPT = """Écris un script Python 3 (Windows) qui fait EXACTEMENT ceci : {goal}
{context}
Règles : stdlib de préférence (sinon seulement : {allowed}) ; le dossier de travail courant est un espace à toi ;
n'écris ailleurs que si la tâche le demande ; aucune interaction (pas d'input) ; imprime à la fin un résumé court
en français de ce qui a été fait (sera lu à voix haute) ; gère les erreurs proprement.
Si un paquet pip est nécessaire, mets en 1re ligne : # DEPENDANCES: paquet1, paquet2
Réponds uniquement avec le code dans ```python."""


def run_code(gemini, goal: str, confirmed: bool = False, autonomous: bool = False) -> str:
    """Écrit le script, le lance, et le corrige tout seul s'il plante (3 essais)."""
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    context, code = "", ""
    for attempt in range(3):
        if HALT.is_set():
            return "ÉCHEC : arrêt d'urgence"
        code = _code(_text(gemini.generate({"contents": [{"role": "user", "parts": [{"text": SCRIPT_PROMPT.format(
            goal=goal, context=context, allowed=", ".join(sorted(ALLOWED_PACKAGES)))}]}]}, timeout=120, fast=False)))
        if not code:
            return "ÉCHEC : pas de code généré"
        if autonomous and AUTO_FORBIDDEN.search(code):
            return "ÉCHEC : script refusé (code système non autorisé en mode autonome)"
        if DANGER.search(code) and not confirmed:
            path = WORK_DIR / "script_a_confirmer.py"
            path.write_text(code, encoding="utf-8")
            if autonomous:
                return "ÉCHEC : script sensible refusé en mode autonome"
            return ("CONFIRMATION REQUISE : ce script supprime / déplace / envoie ou touche au système. Explique en "
                    "une phrase ce qu'il va faire et demande « je lance ? ». Si oui, rappelle executer_code avec "
                    "le même objectif et confirme=true.")
        m = re.match(r"#\s*DEPENDANCES\s*:\s*(.+)", code)
        if m:
            err = _pip([x.strip() for x in m.group(1).split(",") if x.strip()])
            if err:
                context = f"\nATTENTION : {err}. Fais sans ces paquets."
                continue
        path = WORK_DIR / f"script_{datetime.now():%Y%m%d_%H%M%S}.py"
        path.write_text(code, encoding="utf-8")
        rc, out = _run_py([str(path)], timeout=300, confirmed=confirmed)
        if "Bloqué par le mode prudent" in out and not confirmed:
            if autonomous:
                return "ÉCHEC : action refusée par le mode prudent"
            why = re.search(r"Bloqué par le mode prudent de Jarvis : ([^\n]+)", out)
            return (f"CONFIRMATION REQUISE : le mode prudent a bloqué le script ({why.group(1) if why else 'action '
                    f'sensible'}). Explique-le en une phrase et demande « je lance ? » ; si oui, rappelle "
                    f"executer_code avec le même objectif et confirme=true.")
        log.info("Script %s -> code %s", path.name, rc)
        if rc == 0:
            return f"OK : {out.strip()[-1500:] or 'terminé sans message'}"
        context = f"\nLa version précédente a échoué :\n```python\n{code}\n```\nErreur :\n{out[-2000:]}\nCorrige."
    return f"ÉCHEC après 3 essais : {out[-500:]}"


# ============================================================================
# Compétences : des outils que Jarvis se code lui-même
# ============================================================================
GUARD = r'''"""Garde-fou de Jarvis (mode prudent) : chargé AVANT chaque script ou compétence qu'il a écrit.
Sans ton accord (JARVIS_CONFIRME=1), le code ne peut PAS : écrire / supprimer / renommer hors de son espace,
lancer d'autres programmes, envoyer des données (POST), modifier le registre.
Jamais, même avec accord : lire tes clés (.env), tes mots de passe et cookies de navigateur, ton token Discord,
ni modifier le cœur de Jarvis ou Windows."""
import os, sys, tempfile

_ok = os.environ.get("JARVIS_CONFIRME") == "1"
_n = lambda p: os.path.normcase(os.path.abspath(os.fsdecode(p)))
_base = _n(os.environ.get("JARVIS_BASE", "."))
_espace = _n(os.environ.get("JARVIS_ESPACE", "."))
_ecriture = [_espace, _n(tempfile.gettempdir()), _n(os.path.join(_base, "competences")),
             _n(os.path.join(_base, "creations"))]
_ecriture += [_n(d) for d in os.environ.get("JARVIS_DOSSIERS_AUTORISES", "").split(";") if d.strip()]
_zones = [_espace, _n(os.path.join(_base, "competences")), _n(os.path.join(_base, "creations"))]
_la, _ra, _h = os.environ.get("LOCALAPPDATA", ""), os.environ.get("APPDATA", ""), os.path.expanduser("~")
_secret = [_n(os.path.join(_base, ".env")), _n(os.path.join(_base, ".cache")), _n(os.path.join(_base, ".venv")),
           _n(os.path.join(_la, "Google", "Chrome", "User Data")), _n(os.path.join(_la, "Microsoft", "Edge", "User Data")),
           _n(os.path.join(_la, "BraveSoftware")), _n(os.path.join(_ra, "Mozilla")), _n(os.path.join(_ra, "Opera Software")),
           _n(os.path.join(_ra, "discord")), _n(os.path.join(_h, ".ssh")), _n(os.path.join(_ra, "Microsoft", "Credentials")),
           _n(os.path.join(_la, "Microsoft", "Credentials")), _n(os.path.join(_ra, "Microsoft", "Protect"))]
_systeme = [_n(os.environ.get("SystemRoot", r"C:\Windows")), _n(os.environ.get("ProgramFiles", r"C:\Program Files")),
            _n(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))]
_PROG = (".exe", ".bat", ".cmd", ".ps1", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".msi", ".scr", ".py", ".pyw", ".lnk", ".com", ".hta")


def _sous(p, racines):
    return any(p == r or p.startswith(r.rstrip("\\/") + os.sep) for r in racines)


def _non(msg):
    raise PermissionError("Bloqué par le mode prudent de Jarvis : " + msg)


def _ecrire(p, quoi):
    try:
        p = _n(p)
    except Exception:
        return
    if _sous(p, _secret):
        _non(quoi + " sur une donnée protégée")
    if _sous(p, [_base]) and not _sous(p, _zones):
        _non(quoi + " dans le cœur de Jarvis (interdit, même avec accord)")
    if _ok:
        if _sous(p, _systeme):
            _non(quoi + " dans Windows ou Program Files (interdit, même avec accord)")
        return
    if not _sous(p, _ecriture):
        _non(quoi + " hors de l'espace de Jarvis (" + p + ") : il faut ton accord")


def _hook(ev, args):
    if ev == "open":
        path, mode, flags = (list(args) + [None, None, None])[:3]
        if path is None or isinstance(path, int):
            return
        try:
            p = _n(path)
        except Exception:
            return
        if _sous(p, _secret):
            _non("lecture d'une donnée protégée (" + p + ")")
        w = (isinstance(mode, str) and any(c in mode for c in "wax+")) or \
            (mode is None and isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC))
        if w:
            _ecrire(path, "écriture")
    elif ev in ("os.remove", "os.rmdir", "os.truncate", "os.chmod", "shutil.rmtree", "os.mkdir", "os.symlink", "os.link"):
        if args and not isinstance(args[0], int):
            _ecrire(args[0], "modification (" + ev + ")")
    elif ev in ("os.rename", "shutil.move", "shutil.copyfile", "shutil.copytree"):
        if len(args) >= 2:
            _ecrire(args[1], "copie / déplacement")
            if ev in ("os.rename", "shutil.move"):
                _ecrire(args[0], "déplacement")
    elif ev in ("subprocess.Popen", "os.system", "os.exec", "os.spawn", "os.posix_spawn", "_winapi.CreateProcess"):
        if not _ok:
            _non("lancement d'un autre programme : il faut ton accord")
    elif ev == "os.startfile":
        if args and os.fsdecode(args[0]).lower().endswith(_PROG) and not _ok:
            _non("lancement d'un programme : il faut ton accord")
    elif ev == "urllib.Request":
        url, data, headers, method = (list(args) + [None] * 4)[:4]
        if (data is not None or (method or "GET").upper() in ("POST", "PUT", "PATCH", "DELETE")) and not _ok:
            _non("envoi de données sur internet : il faut ton accord")
    elif ev == "http.client.send":
        data = args[1] if len(args) > 1 else b""
        if isinstance(data, (bytes, bytearray)) and data[:7].upper().startswith((b"POST", b"PUT", b"PATCH", b"DELETE")) and not _ok:
            _non("envoi de données sur internet : il faut ton accord")
    elif ev.startswith("winreg.") and ev.split(".")[1] in ("SetValue", "SetValueEx", "DeleteKey", "DeleteKeyEx", "DeleteValue", "CreateKey", "CreateKeyEx"):
        if not _ok:
            _non("modification du registre Windows : il faut ton accord")


if os.environ.get("JARVIS_PRUDENT", "1") != "0":
    sys.addaudithook(_hook)
'''

LAUNCHER = '''import runpy, sys
sys.path.insert(0, __import__("os").path.dirname(__file__))
import _garde  # noqa: F401  (garde-fou chargé en premier)
script = sys.argv[1]
sys.argv = sys.argv[1:]
runpy.run_path(script, run_name="__main__")
'''

RUNNER = '''import importlib.util, json, sys, os
sys.path.insert(0, os.path.dirname(__file__))
import _garde  # noqa: F401  (garde-fou chargé en premier)
path, mode = sys.argv[1], sys.argv[2]
spec = importlib.util.spec_from_file_location("competence", path)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
if mode == "info":
    print("<<<INFO>>>" + json.dumps({"description": m.DESCRIPTION, "parametres": getattr(m, "PARAMETRES", {}) or {},
          "dependances": getattr(m, "DEPENDANCES", []) or [], "test": getattr(m, "TEST", None)}, ensure_ascii=False))
else:
    args = json.loads(sys.stdin.read() or "{}")
    print("<<<RESULTAT>>>" + str(m.executer(**args)))
'''

COMP_PROMPT = """Tu écris une COMPÉTENCE (un nouvel outil) pour JARVIS, assistant vocal sur un PC Windows (Python 3).
Besoin : {need}
{research}{context}
Produis UN module Python avec EXACTEMENT cette structure :
DESCRIPTION = "ce que fait l'outil et quand l'utiliser (une phrase)"
PARAMETRES = {{"nom_du_parametre": "description"}}   # valeurs passées en texte ; {{}} si aucun
DEPENDANCES = []          # paquets pip, UNIQUEMENT parmi : {allowed} (stdlib de préférence)
TEST = {{...}}            # arguments d'un essai SANS effet (lecture seule), ou None si tout appel a un effet
def executer(**kw) -> str:
    ...                   # renvoie une phrase courte en français, lisible à voix haute
Règles : robuste (try/except, timeout réseau 15 s), API publiques SANS clé (ex. open-meteo.com, wttr.in,
api.coingecko.com, fr.wikipedia.org/api), aucune interaction console, ne supprime rien, n'envoie rien à personne,
écrit seulement dans os.environ["JARVIS_ESPACE"] si besoin. Réponds uniquement avec le code dans ```python."""


class Skills:
    def __init__(self, gemini) -> None:
        self.gemini = gemini
        self.lock = threading.Lock()
        COMP_DIR.mkdir(parents=True, exist_ok=True)
        install_guard()
        self.index_file = COMP_DIR / "_index.json"
        try:
            self.index: dict[str, dict] = json.loads(self.index_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.index = {}
        self.refresh()

    def _save(self) -> None:
        self.index_file.write_text(json.dumps(self.index, ensure_ascii=False, indent=1), encoding="utf-8")

    def _info(self, path: Path) -> dict | None:
        rc, out = _run_py([str(COMP_DIR / "_runner.py"), str(path), "info"], timeout=30)
        m = re.search(r"<<<INFO>>>(.*)", out)
        if rc != 0 or not m:
            return None
        try:
            return json.loads(m.group(1))
        except ValueError:
            return None

    def refresh(self) -> None:
        """(Re)lit les compétences du dossier (ajoutées par Jarvis ou à la main)."""
        with self.lock:
            seen = set()
            for p in COMP_DIR.glob("*.py"):
                if p.name.startswith("_"):
                    continue
                name, mtime = p.stem, p.stat().st_mtime
                seen.add(name)
                cur = self.index.get(name)
                if cur and cur.get("mtime") == mtime:
                    continue
                info = self._info(p)
                if info:
                    self.index[name] = {**info, "mtime": mtime, "actif": cur.get("actif", True) if cur else True,
                                        "erreurs": 0}
                else:
                    log.warning("Compétence %s illisible : ignorée.", name)
            for name in list(self.index):
                if name not in seen:
                    del self.index[name]
            self._save()

    # --- pour Gemini
    def declarations(self) -> list[dict]:
        out = []
        for name, info in self.index.items():
            if not info.get("actif"):
                continue
            props = {k: {"type": "STRING", "description": str(v)[:200]}
                     for k, v in (info.get("parametres") or {}).items() if re.match(r"^[A-Za-z_]\w*$", k)}
            d = {"name": f"comp_{name}"[:64], "description": f"[compétence apprise] {info.get('description', '')}"[:900]}
            if props:
                d["parameters"] = {"type": "OBJECT", "properties": props, "required": []}
            out.append(d)
        return out

    def text(self) -> str:
        on = [f"{n} ({i.get('description', '')[:80]})" for n, i in self.index.items() if i.get("actif")]
        off = [n for n, i in self.index.items() if not i.get("actif")]
        return ("; ".join(on) or "aucune") + (f" | désactivées : {', '.join(off)}" if off else "")

    def run(self, tool: str, args: dict) -> str:
        name = tool[len("comp_"):]
        info = self.index.get(name)
        if not info or not info.get("actif"):
            return f"ÉCHEC : compétence {name} inconnue ou désactivée"
        rc, out = _run_py([str(COMP_DIR / "_runner.py"), str(COMP_DIR / f"{name}.py"), "run"],
                          stdin=json.dumps({k: str(v) for k, v in (args or {}).items()}), timeout=120,
                          confirmed=bool(info.get("confirme")))
        m = re.search(r"<<<RESULTAT>>>(.*)", out, re.S)
        if rc == 0 and m:
            info["erreurs"] = 0
            return m.group(1).strip()[:2000] or "fait"
        info["erreurs"] = info.get("erreurs", 0) + 1
        self._save()
        log.warning("Compétence %s en échec : %s", name, out[-300:])
        return f"ÉCHEC de la compétence {name} : {out[-400:]} (tu peux la réparer : competence ameliorer)"

    # --- apprendre
    def create(self, need: str, name: str = "", autonomous: bool = False, confirmed: bool = False,
               improve: bool = False) -> str:
        """Code la compétence, l'installe, la TESTE, corrige si besoin (3 essais), puis l'active."""
        name = _slug(name or need)
        path = COMP_DIR / f"{name}.py"
        research = ""
        try:
            research = "Infos trouvées sur internet :\n" + web_search(
                self.gemini, f"Comment faire en Python, sans clé API, de façon fiable : {need}")[:2500] + "\n"
        except Exception:  # noqa: BLE001
            pass
        context = ""
        if improve and path.is_file():
            context = f"\nVoici la version actuelle à AMÉLIORER / RÉPARER :\n```python\n{path.read_text(encoding='utf-8')}\n```\n"
        last = ""
        for _ in range(3):
            if HALT.is_set():
                return "ÉCHEC : arrêt d'urgence"
            code = _code(_text(self.gemini.generate({"contents": [{"role": "user", "parts": [{"text": COMP_PROMPT.format(
                need=need, research=research, context=context, allowed=", ".join(sorted(ALLOWED_PACKAGES)))}]}]},
                timeout=180, fast=False)))
            if "def executer" not in code or "DESCRIPTION" not in code:
                last = "structure invalide"
                context = "\nTa réponse précédente n'avait pas la structure demandée."
                continue
            if autonomous and AUTO_FORBIDDEN.search(code):
                return "ÉCHEC : compétence refusée (code système non autorisé en auto-amélioration)"
            if DANGER.search(code) and not confirmed:
                if autonomous:
                    return "ÉCHEC : compétence sensible refusée en mode autonome"
                (COMP_DIR / f"_{name}.a_confirmer.txt").write_text(code, encoding="utf-8")
                return ("CONFIRMATION REQUISE : cette compétence supprimerait / enverrait / toucherait au système. "
                        "Demande « je l'installe ? » ; si oui, rappelle competence avec confirme=true.")
            tmp = COMP_DIR / f"_{name}.essai.py"
            tmp.write_text(code, encoding="utf-8")
            info = self._info(tmp)
            if not info:
                _, out = _run_py([str(COMP_DIR / "_runner.py"), str(tmp), "info"], timeout=30)
                last = out[-1500:]
                context = f"\nLe code précédent ne se charge pas :\n```python\n{code}\n```\nErreur :\n{last}\nCorrige."
                continue
            err = _pip(info.get("dependances") or [])
            if err:
                last = err
                context = f"\n{err}. Fais sans ces paquets (stdlib)."
                continue
            if info.get("test") is not None:
                rc, out = _run_py([str(COMP_DIR / "_runner.py"), str(tmp), "run"],
                                  stdin=json.dumps({k: str(v) for k, v in (info["test"] or {}).items()}), timeout=90)
                if rc != 0 or "<<<RESULTAT>>>" not in out:
                    last = out[-1500:]
                    context = (f"\nLe test a échoué :\n```python\n{code}\n```\nSortie :\n{last}\nCorrige.")
                    continue
                log.info("Test de la compétence %s : %s", name, out.split("<<<RESULTAT>>>")[-1][:200])
            if path.is_file():
                path.with_suffix(".py.ancien").write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
            tmp.replace(path)
            self.refresh()
            if name in self.index:
                self.index[name]["confirme"] = bool(confirmed)      # pouvoirs accordés à voix haute
                self.index[name]["auto"] = bool(autonomous)
                self._save()
            log.info("Nouvelle compétence apprise : %s", name)
            note_learned(f"compétence « {name} » : {info.get('description', '')}", "competence", name)
            return (f"OK : compétence comp_{name} installée et testée ({info.get('description', '')}). "
                    f"Tu peux l'utiliser tout de suite.")
        for t in COMP_DIR.glob(f"_{name}.essai.py"):
            t.unlink(missing_ok=True)
        return f"ÉCHEC : je n'ai pas réussi à coder cette compétence ({last[-300:]})"

    def set_active(self, name: str, on: bool) -> str:
        key = self._find(name)
        if not key:
            return f"ÉCHEC : pas de compétence « {name} »"
        self.index[key]["actif"] = on
        self._save()
        return f"Compétence {key} {'activée' if on else 'désactivée'}"

    def delete(self, name: str) -> str:
        key = self._find(name)
        if not key:
            return f"ÉCHEC : pas de compétence « {name} »"
        p = COMP_DIR / f"{key}.py"
        p.replace(p.with_suffix(".py.supprime"))           # gardé de côté, au cas où
        self.refresh()
        return f"Compétence {key} retirée"

    def _find(self, name: str) -> str | None:
        s = _slug(name)
        if s in self.index:
            return s
        return next((k for k in self.index if s in k or k in s), None)


# ============================================================================
# Auto-amélioration
# ============================================================================
def journal(entry: dict) -> None:
    try:
        JOURNAL.parent.mkdir(parents=True, exist_ok=True)
        with JOURNAL.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"t": datetime.now().isoformat(timespec="seconds"), **entry}, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _read_learned() -> dict:
    try:
        return json.loads(LEARNED.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"faits": [], "derniere_revue": 0, "lu_jusqu_a": 0}


def note_learned(what: str, kind: str = "", ref: str = "") -> None:
    d = _read_learned()
    d["faits"] = (d.get("faits", []) + [{"t": datetime.now().strftime("%d/%m %H:%M"), "ts": time.time(),
                                         "quoi": what, "type": kind, "ref": ref}])[-40:]
    LEARNED.parent.mkdir(parents=True, exist_ok=True)
    LEARNED.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def learned_text(n: int = 8) -> str:
    f = _read_learned().get("faits", [])[-n:]
    return "\n".join(f"- {x['t']} : {x['quoi']}" for x in f) or "rien pour l'instant"


def undo_learned(hours: float, memory, skills) -> str:
    """« Jarvis, annule ce que tu as appris cette nuit » : retire leçons et compétences récentes."""
    d = _read_learned()
    since = time.time() - hours * 3600
    keep, undone = [], []
    for f in d.get("faits", []):
        if f.get("ts", 0) < since:
            keep.append(f)
            continue
        if f.get("type") == "lecon" and f.get("ref") in memory.facts:
            memory.facts.remove(f["ref"])
            memory._save()
            undone.append(f["quoi"])
        elif f.get("type") == "competence" and skills is not None:
            out = skills.delete(f.get("ref", ""))
            undone.append(f["quoi"] if not out.startswith("ÉCHEC") else f"(déjà retiré) {f['quoi']}")
        else:
            keep.append(f)
    d["faits"] = keep
    LEARNED.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    log.info("Améliorations annulées : %s", undone)
    return ("Annulé : " + "; ".join(undone)) if undone else "Rien à annuler sur cette période."


REVIEW_PROMPT = """Tu es JARVIS et tu t'auto-évalues pour devenir plus autonome et plus utile à {user}.
Voici tes derniers échanges (demande, outils appelés, résultats, réponse ; « correction » = il t'a repris) :
{journal}

Ce que tu sais déjà de lui :
{memory}

Tes compétences apprises : {skills}

Analyse : échecs, demandes mal comprises, choses que tu n'as pas su faire, ce qu'il demande souvent.
Réponds en JSON :
{{"lecons": ["règle courte et concrète à retenir pour mieux faire la prochaine fois", ...],
  "competences": [{{"nom": "nom_court", "besoin": "outil précis à coder, utile et SANS RISQUE (lecture, info, "
                  "ouverture...)"}}],
  "resume": "une phrase : ce que tu as amélioré"}}
Maximum 3 leçons et 2 compétences, seulement si c'est vraiment utile (listes vides sinon). Pas de doublon avec
ce qui existe déjà."""


class Improver:
    """Quand tu ne l'utilises pas, Jarvis relit ses échanges et s'améliore (leçons + nouvelles compétences)."""

    def __init__(self, gemini, skills: Skills, memory, user: str) -> None:
        self.gemini, self.skills, self.memory, self.user = gemini, skills, memory, user
        self.last_activity = time.monotonic()
        self.running = threading.Lock()
        self.enabled = (os.environ.get("JARVIS_AUTO_AMELIORATION") or "1").strip().lower() not in ("0", "non", "off")
        self.every = float(os.environ.get("JARVIS_AMELIORATION_HEURES") or 6) * 3600

    def touch(self) -> None:
        self.last_activity = time.monotonic()

    def start(self) -> None:
        if self.enabled:
            threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self) -> None:
        while True:
            time.sleep(60)
            idle = time.monotonic() - self.last_activity
            if idle < 15 * 60 or HALT.is_set():                               # seulement quand tu ne t'en sers pas
                continue
            if time.time() - _read_learned().get("derniere_revue", 0) < self.every:
                continue
            try:
                self.review()
            except Exception:  # noqa: BLE001
                log.warning("Auto-amélioration en échec", exc_info=True)

    def review(self, user_asked: bool = False) -> str:
        if not self.running.acquire(blocking=False):
            return "Je suis déjà en train de m'améliorer."
        try:
            d = _read_learned()
            d["derniere_revue"] = time.time()
            LEARNED.parent.mkdir(parents=True, exist_ok=True)
            LEARNED.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
            try:
                lines = JOURNAL.read_text(encoding="utf-8").splitlines()[-60:]
            except OSError:
                lines = []
            if len(lines) < 3 and not user_asked:
                return "Pas assez d'échanges pour apprendre."
            log.info("Auto-amélioration : je relis mes %d derniers échanges...", len(lines))
            resp = self.gemini.generate({"contents": [{"role": "user", "parts": [{"text": REVIEW_PROMPT.format(
                user=self.user, journal="\n".join(lines)[-30000:] or "(aucun)", memory=self.memory.text(),
                skills=self.skills.text())}]}], "generationConfig": {"responseMimeType": "application/json"}},
                timeout=120, fast=False)
            try:
                plan = json.loads(_text(resp))
            except ValueError:
                return "Je n'ai pas réussi à analyser mes échanges."
            done = []
            for lesson in (plan.get("lecons") or [])[:3]:
                if HALT.is_set():
                    break
                if isinstance(lesson, str) and lesson.strip():
                    fact = f"(leçon) {lesson.strip()}"
                    out = self.memory.add(fact)
                    if out.startswith("Retenu"):
                        done.append(f"leçon : {lesson.strip()}")
                        note_learned(f"leçon : {lesson.strip()}", "lecon", fact)
            for c in (plan.get("competences") or [])[:2]:
                if HALT.is_set():
                    break
                if isinstance(c, dict) and c.get("besoin"):
                    out = self.skills.create(c["besoin"], c.get("nom", ""), autonomous=True)
                    log.info("Auto-amélioration, compétence %s : %s", c.get("nom"), out[:200])
                    if out.startswith("OK"):
                        done.append(f"compétence {c.get('nom')}")
            summary = plan.get("resume") or ""
            log.info("Auto-amélioration terminée : %s", "; ".join(done) or "rien de nouveau")
            return ("J'ai appris : " + "; ".join(done)) if done else (summary or "Rien de nouveau à améliorer.")
        finally:
            self.running.release()
