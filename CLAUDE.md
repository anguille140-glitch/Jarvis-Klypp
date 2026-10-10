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
- `web/holo.js` (+ `web/three/`, three.js r128 local) — HOLO-TABLE 3D dans le plan de travail : vrai relief (tuiles
  Terrarium via `/relief/`), carte OSM holographique drapée, bâtiments / sommets / rivières / remontées (Overpass via
  `/zone`, cache `.cache/zone_*.json`), soleil et météo réels, modes holo / thermique / rayons X, scan, survol, drones,
  satellite, cible + profil. Remplace la carte plate à la fin du globe ; plein écran via le bouton « Holo » ou la voix
  (outil `holo_table`, canal `state["holo"]`). Test sans internet : données factices + Chromium swiftshader.
- `vitrine_cs.py` + `vitrine_cs.html` + `skins_cs.json` — VITRINE CS2 (« lance mon fond d'écran ») : intro ouverture de
  caisse, skins chers qui défilent (inspection 3D souris, zoom, caisses, favoris, tirs dans le décor, bruitages WebAudio),
  pilotable à la voix (outil `fond_ecran`, `VITRINE_RE` / `VITRINE_CMDS`, `find_skin`). Images Steam téléchargées une
  fois dans `.cache/skins` (jamais dans le dépôt). Prix indicatifs SteamAnalyst (sept. 2026) pour 14 skins.
  3D : `web/vitrine3d.js` (three.js local) transforme l'image en objet épais (bords arrondis, relief de peinture,
  laque/métal, sol réfléchissant, bloom) ; repli 2D automatique si WebGL échoue (ou `?2d`). Images Steam : essaie
  `/1024fx1024f` puis la taille par défaut.
  Décor `web/vitrine_decor.js` : village italien de nuit sous la pluie (création originale, pas d'assets Valve) —
  pavés mouillés, façades/volets/lierre/mousse, toits, lanternes, guirlandes, arche, clocher + horloge holo, néons,
  panneau défilant, drone, socle holo + anneaux + scan, pluie (shader), éclaboussures, éclairs (événement « eclair »
  → tonnerre dans la page). Sons : moteur SFX à attaques nettes + ambiance pluie ; visière avec gouttes (canvas).
- `session_jeu.py` — « lance-moi une session CS » : FACEIT AC (élévation UAC, ou tâche planifiée sans confirmation) puis
  CS2 via `steam://rungameid/730`, annonces vocales à chaque étape (outil `session_jeu` + voie express).
- `mode_jeu.py` — mode jeu automatique (psutil) : décharge Ollama et Whisper GPU (Whisper « small » CPU pendant la
  partie), priorité basse, sphère ralentie, mesures GPU espacées (NVML au lieu de nvidia-smi dans `plan_de_travail.py`).
- `local_music.py` — lecteur MCI (dossier `musique/`). `camera_mode.py` + `camera.html` — contrôle à la main.
- `hud.py` — ancienne intro (secours).

## Réglages utiles (`.env`)
`JARVIS_IA` (hybride | local | local_seul | gemini), `JARVIS_ADRESSE` / `JARVIS_VILLE`, `JARVIS_INTERRUPTION`,
`JARVIS_PLAN_APPS`, `JARVIS_MUSIQUE_DECALAGE`, `JARVIS_AUTO_AMELIORATION`, `JARVIS_DOSSIERS_AUTORISES`,
`JARVIS_BIP` (1 = bip quand il écoute), `JARVIS_PLAN_SONS` (bruitages du globe, 0–100), `JARVIS_SPHERE_MOTEUR` (cpu = ancienne sphère), `JARVIS_MODE_JEU` (non = désactivé), `JARVIS_VITRINE_ECRAN` (gauche = 2e écran), `JARVIS_JEUX` (jeux en plus), `JARVIS_FACEIT_AC` (chemin de faceitclient.exe si besoin), `JARVIS_FACEIT_ATTENTE` (s avant CS2), `JARVIS_VOSK` (petit par défaut ; grand = modèle plus précis mais lourd, à charger longtemps).

## Où on en est (à vérifier sur le PC de Klypp)
- **Sphère OpenGL** (`orb_gpu.py`) : jamais testée sur un vrai Windows. Vérifier dans `jarvis.log` la ligne
  « Sphère dessinée par la carte graphique » et « Sphère : N images/s » (attendu ≈ 240). Si carré noir autour de la
  sphère ou erreur : regarder la transparence DWM (`_init_gl`), sinon `JARVIS_SPHERE_MOTEUR=cpu` en secours.
- **Animation du plan de travail** (globe → carte holographique 3D + bruitages WebAudio) : à valider en vrai,
  notamment le son (Chrome lancé avec `--autoplay-policy=no-user-gesture-required`) et la fluidité de la carte.
- **Holo-table 3D** : jamais vue avec les vraies données (relief Terrarium + Overpass) ; vérifier la ligne
  « Holo-table : N bâtiments… » dans `jarvis.log`. **Session CS** : vérifier le nom du programme FACEIT AC.
- **Vitrine CS2** : jamais vue avec les vraies images Steam (testée avec des images factices).
- **Sphère** : réglages taille / fond noir désormais aussi en voie express (`parse_orb_style`).
- **Position** : la puce de position est cliquable pour corriger l'adresse (`JARVIS_ADRESSE` dans `.env`, jamais
  dans le code).
- **Idée en attente** : brancher Claude Code à Jarvis (« Jarvis, répare-toi ») avec garde-fous : sauvegarde avant
  changement, vérification que le code se lance, confirmation vocale, interdiction de toucher `.env` et `_garde.py`.
