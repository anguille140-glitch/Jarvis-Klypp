# Jarvis (Klypp) — notes pour Claude

Assistant vocal façon Iron Man pour **Windows**, en **Python 3.14** (environnement `.venv`). L'utilisateur s'appelle
Klypp, parle **français** et n'est pas développeur : réponds en français simple, explique ce que tu changes et pourquoi,
et donne les actions à faire (fichiers à lancer) clairement.

## Règles importantes
- **Ne jamais afficher, copier ni envoyer le contenu de `.env`** (clés Gemini, ElevenLabs, FACEIT, adresse). On peut
  ajouter une ligne de réglage, jamais en lire les valeurs à voix haute ou dans une réponse.
- Le dépôt GitHub `anguille140-glitch/Jarvis-Klypp` est **public** : rien de personnel dans le code (pas d'adresse, pas
  de clé). `.env`, `.cache/`, `jarvis.log`, `musique/`, `modeles/` sont ignorés par git.
- Jarvis tourne souvent **caché** (superviseur) : pour tester une modif, `arreter_jarvis.bat` puis
  `installer_demarrage.bat` (ou `lancer_debug.bat` pour voir la console). Le journal est dans `jarvis.log`.
- Tous les textes vus/entendus par l'utilisateur sont en français.
- Mode prudent : ne pas affaiblir `competences/_garde.py` (généré par `autonomie.py`) ni les confirmations vocales.

## Architecture
- `jarvis.py` — point d'entrée : attend « salut Jarvis », intro (`intro_web.py` + `intro.html`), ouvre FACEIT, Discord
  sur le 2e écran, musique locale pile à la fin de l'intro, puis lance l'assistant. Ferme les anciens Jarvis au démarrage.
- `superviseur.py` — fait tourner Jarvis caché et le relance s'il s'arrête (installé par `installer_demarrage.bat`).
- `assistant.py` — le cœur : `Voice` (ElevenLabs / Piper / Windows, interruption quand on dit « Jarvis »),
  `Gemini` (REST, modèles de secours), `Actions` (tous les outils `do_*`), `Brain` (voie express sans IA + boucle
  d'outils), `Ear` (Vosk : mot « Jarvis », découpage des phrases), `pick_ai` (hybride : Gemini d'abord, IA locale en
  secours), `run` (boucle principale).
- `local_ai.py` — IA locale : Ollama (`qwen3.5:9b`, vision), Whisper (transcription), Piper (voix), DuckDuckGo.
- `autonomie.py` — recherche web, code exécuté avec garde-fou, compétences auto-codées (`competences/`),
  auto-amélioration, arrêt d'urgence.
- `creations.py` — sites / diaporamas / interfaces / jeux générés en HTML (`creations/`).
- `plan_de_travail.py` + `plan_de_travail.html` — cockpit plein écran (globe de chargement, sphère, journal, applis,
  météo open-meteo, agenda + rappels, stats PC, tuiles OpenStreetMap en cache). Le HTML est généré à partir d'un
  gabarit + données du globe ; on peut le modifier directement.
- `orb.py` — sphère animée du bureau (fenêtre transparente, taille réglable à la voix) ; `orb.create()` choisit
  `orb_gpu.py` (OpenGL via ctypes, shader `orb_sphere.glsl`, synchro écran 240 Hz) et revient à l'ancienne sphère
  (numpy) si la carte graphique n'est pas utilisable.
- `local_music.py` — lecteur MCI (dossier `musique/`). `camera_mode.py` + `camera.html` — contrôle à la main.
- `hud.py` — ancienne intro (secours).

## Réglages utiles (`.env`)
`JARVIS_IA` (hybride | local | local_seul | gemini), `JARVIS_ADRESSE` / `JARVIS_VILLE`, `JARVIS_INTERRUPTION`,
`JARVIS_PLAN_APPS`, `JARVIS_MUSIQUE_DECALAGE`, `JARVIS_AUTO_AMELIORATION`, `JARVIS_DOSSIERS_AUTORISES`,
`JARVIS_BIP` (1 = bip quand il écoute), `JARVIS_PLAN_SONS` (bruitages du globe, 0–100), `JARVIS_SPHERE_MOTEUR` (cpu = ancienne sphère), `JARVIS_VOSK` (petit par défaut ; grand = modèle plus précis mais lourd, à charger longtemps).
