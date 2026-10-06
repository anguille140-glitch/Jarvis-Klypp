"""Créations de Jarvis : sites internet, diaporamas, interfaces/applis, mini-jeux, pages... à la voix.

« Jarvis, crée-moi un site pour ma team CS »  « Jarvis, fais un diaporama sur les volcans, 8 diapos »
« Jarvis, fais-moi une interface pour suivre mes entraînements »  « Jarvis, ajoute une page contact au site »

Gemini écrit une page web complète (un seul fichier .html), Jarvis l'enregistre dans le dossier « creations »
et l'ouvre dans ton navigateur. Ça tourne en arrière-plan : tu peux continuer à parler à Jarvis pendant ce temps.
Un diaporama se pilote avec les flèches (F = plein écran) et s'exporte en PDF avec Ctrl+P.
Dossier : « creations » dans Jarvis (ou JARVIS_DOSSIER_CREATIONS dans .env).
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
import unicodedata
from datetime import datetime
from pathlib import Path

log = logging.getLogger("jarvis")
BASE = Path(__file__).resolve().parent

KINDS = {
    "site": "un SITE INTERNET complet (une seule page avec navigation par ancres, ou plusieurs « pages » affichées "
            "en JavaScript) : en-tête, sections riches, pied de page, responsive (PC et téléphone).",
    "diaporama": "un DIAPORAMA plein écran en HTML : une diapo à la fois, 16/9 centré, transitions fluides, "
                 "navigation flèches gauche/droite + clic + barre espace, touche F pour le plein écran, numéro de "
                 "diapo et barre de progression, première diapo = titre, dernière = conclusion. Contenu réel et "
                 "précis sur chaque diapo (pas de texte de remplissage). Ajoute @media print avec une diapo par "
                 "page (paysage) pour l'export PDF avec Ctrl+P.",
    "interface": "une APPLICATION / INTERFACE web qui FONCTIONNE vraiment (boutons, formulaires, calculs, listes, "
                 "graphiques si utile) en JavaScript. Les données de l'utilisateur sont gardées avec localStorage.",
    "jeu": "un MINI-JEU jouable tout de suite (canvas ou DOM), avec écran titre, score, meilleur score "
           "(localStorage), commandes clavier et souris expliquées à l'écran, rejouer.",
    "page": "une PAGE / un DOCUMENT bien mis en page (CV, affiche, fiche, lettre, menu, invitation...), "
            "imprimable proprement (@media print).",
    "autre": "ce qui est décrit, sous forme d'une page web autonome.",
}

RULES = """Tu es un excellent développeur web et designer. Crée {kind}

Demande de l'utilisateur (dictée à la voix, en français) : {desc}

RÈGLES :
- Réponds UNIQUEMENT avec le code d'UN SEUL fichier HTML complet, de <!DOCTYPE html> à </html>. Pas d'explication.
- Tout dans ce fichier : CSS dans <style>, JavaScript dans <script>. Bibliothèques autorisées seulement depuis
  https://cdnjs.cloudflare.com ou https://cdn.jsdelivr.net ; polices depuis Google Fonts.
- Images : SVG dessinés par toi, dégradés, emojis, ou photos https://picsum.photos/seed/<mot-anglais>/<largeur>/<hauteur>.
- Design moderne et soigné, cohérent, beau du premier coup : vraie direction artistique (palette, typographie,
  espacements, animations discrètes), pas un modèle générique. Sauf demande contraire : style futuriste sombre
  façon interface de JARVIS (bleu cyan lumineux sur fond très sombre).
- Contenu réel, en français, précis et complet : jamais de « Lorem ipsum » ni de « Texte ici ».
- Tout doit marcher en ouvrant le fichier directement (file://), sans serveur, sans erreur dans la console.
- <title> court et parlant."""

EDIT = """Voici une page web que tu as créée (fichier HTML complet) :

{html}

Modifie-la selon cette demande (dictée à la voix) : {change}

Garde tout le reste identique sauf si la demande dit le contraire. Mêmes règles qu'avant : un seul fichier HTML
complet, CSS et JS intégrés. Réponds UNIQUEMENT avec le fichier HTML complet modifié, sans explication."""


def folder() -> Path:
    extra = (os.environ.get("JARVIS_DOSSIER_CREATIONS") or "").strip()
    d = Path(os.path.expandvars(os.path.expanduser(extra))) if extra else BASE / "creations"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:40] or "creation"


def _norm(s: str) -> str:
    return _slug(s).replace("-", " ")


def extract_html(text: str) -> str | None:
    """Le fichier HTML dans la réponse de Gemini (avec ou sans ```html)."""
    m = re.search(r"```(?:html)?\s*(<!DOCTYPE.*?</html>)\s*```", text, re.I | re.S)
    if m:
        return m.group(1)
    m = re.search(r"(<!DOCTYPE html.*</html>)", text, re.I | re.S) or re.search(r"(<html.*</html>)", text, re.I | re.S)
    if m:
        return m.group(1)
    return None


def all_items() -> list[Path]:
    return sorted(folder().glob("*.html"), key=lambda p: p.stat().st_mtime, reverse=True)


def find(name: str | None) -> Path | None:
    items = all_items()
    if not items:
        return None
    if not name:
        return items[0]                                  # la dernière créée / modifiée
    q = _norm(name)
    for p in items:
        if q and (q in _norm(p.stem) or all(w in _norm(p.stem) for w in q.split())):
            return p
    import difflib
    best = max(items, key=lambda p: difflib.SequenceMatcher(None, q, _norm(p.stem)).ratio())
    return best if difflib.SequenceMatcher(None, q, _norm(best.stem)).ratio() >= 0.5 else items[0]


def open_file(p: Path) -> None:
    try:
        os.startfile(str(p))                             # type: ignore[attr-defined]  (navigateur par défaut)
    except Exception:  # noqa: BLE001
        import webbrowser
        webbrowser.open(p.as_uri())


class Creator:
    """Fabrique en arrière-plan, puis annonce « c'est prêt » et ouvre le résultat."""

    def __init__(self, gemini, say) -> None:
        self.gemini, self.say = gemini, say
        self.busy: dict[str, float] = {}                 # travaux en cours : nom -> début

    def _ask(self, prompt: str) -> str:
        body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.7, "maxOutputTokens": 60000}}
        resp = self.gemini.generate(body, timeout=300, fast=False)
        try:
            parts = resp["candidates"][0]["content"].get("parts") or []
        except (KeyError, IndexError):
            parts = []
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        html = extract_html(text)
        if not html or len(html) < 200:
            raise RuntimeError("Gemini n'a pas renvoyé de page complète")
        return html

    def _job(self, label: str, fn, done: str) -> None:
        self.busy[label] = time.monotonic()
        try:
            path = fn()
            import autonomie
            if autonomie.HALT.is_set():                  # « stop total » pendant la fabrication
                return
            dt = time.monotonic() - self.busy[label]
            log.info("Création prête en %.0f s : %s", dt, path)
            open_file(path)
            self.say(done)
        except Exception as e:  # noqa: BLE001
            log.warning("Création en échec (%s) : %s", label, e, exc_info=True)
            msg = str(e)
            if msg.startswith("429"):
                self.say("Je n'ai plus de quota Gemini pour créer ça. Réessaie un peu plus tard.")
            else:
                self.say(f"Je n'ai pas réussi à terminer {label}. Redemande-moi, je réessaierai.")
        finally:
            self.busy.pop(label, None)

    def create(self, kind: str, desc: str, name: str = "") -> str:
        kind = kind if kind in KINDS else "autre"
        if not (desc or "").strip():
            return "ÉCHEC : décris ce qu'il faut créer"
        title = (name or desc).strip()
        label = {"site": "ton site", "diaporama": "ton diaporama", "interface": "ton interface",
                 "jeu": "ton jeu", "page": "ta page"}.get(kind, "ta création")
        if label in self.busy:                           # déjà en fabrication : on ne relance pas
            secs = int(time.monotonic() - self.busy[label])
            return (f"DÉJÀ EN COURS : {label} est en fabrication depuis {secs} s (ça continue en arrière-plan, même si le "
                    f"plan de travail est fermé). Ne relance rien : dis-le simplement.")

        def build() -> Path:
            html = self._ask(RULES.format(kind=KINDS[kind], desc=desc.strip()))
            path = folder() / f"{_slug(title)}_{datetime.now():%Y%m%d-%H%M}.html"
            path.write_text(html, encoding="utf-8")
            return path

        done = {"ta page": "Ta page est prête, monsieur. Je l'ouvre.", "ton interface": "Ton interface est prête, "
                "monsieur. Je l'ouvre.", "ta création": "Ta création est prête, monsieur. Je l'ouvre."}.get(
            label, f"{label[0].upper() + label[1:]} est prêt, monsieur. Je l'ouvre.")
        threading.Thread(target=self._job, args=(label, build, done), daemon=True).start()
        return (f"EN COURS : je fabrique {label} en arrière-plan (environ une minute) ; je préviendrai et "
                f"l'ouvrirai quand ce sera prêt. Dis-le en une phrase courte.")

    def edit(self, change: str, name: str = "") -> str:
        p = find(name)
        if p is None:
            return "ÉCHEC : aucune création à modifier"
        if not (change or "").strip():
            return "ÉCHEC : dis-moi quoi changer"

        def build() -> Path:
            html = self._ask(EDIT.format(html=p.read_text(encoding="utf-8"), change=change.strip()))
            p.with_suffix(".avant.bak").write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
            p.write_text(html, encoding="utf-8")
            return p

        threading.Thread(target=self._job, args=("la nouvelle version", build,
                                                 "La nouvelle version est prête. Je l'ouvre."), daemon=True).start()
        return f"EN COURS : je modifie « {p.stem} » en arrière-plan ; je l'ouvrirai quand ce sera prêt."

    def open(self, name: str = "") -> str:
        p = find(name)
        if p is None:
            return "ÉCHEC : aucune création pour l'instant"
        open_file(p)
        return f"Ouvert : {p.stem}"

    def status(self) -> str:
        """Pour l'IA : ce qui est en train d'être fabriqué."""
        if not self.busy:
            return "aucune"
        return ", ".join(f"{k} (depuis {int(time.monotonic() - v)} s)" for k, v in self.busy.items())

    def listing(self) -> str:
        items = all_items()[:15]
        busy = ", ".join(self.busy) or "rien"
        return ("Créations : " + (", ".join(p.stem for p in items) or "aucune") + f". En cours : {busy}.")

    def open_folder(self) -> str:
        open_file(folder())
        return f"Dossier ouvert : {folder()}"
