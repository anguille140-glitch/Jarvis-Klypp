# Jarvis (Klypp)

Assistant vocal façon Iron Man pour Windows, en Python.

- **Lancement** : « salut Jarvis » → intro plein écran, FACEIT, Discord sur le 2e écran, musique locale.
- **Assistant vocal** : « Jarvis, … » pour ouvrir des applis, gérer les fenêtres et les écrans, la musique, la caméra
  (contrôle à la main), créer des sites / diaporamas / jeux, chercher sur internet, écrire et lancer du code.
- **Autonome** : enchaîne les tâches, routines, compétences qu'il se code lui-même (testées et isolées),
  auto-amélioration quand il est inactif.
- **IA locale** (gratuite, sans quota) : Ollama (`qwen3.5:9b`), Faster-Whisper, voix Piper. Gemini gratuit en option.
- **Mode prudent** : garde-fou sur tout le code qu'il écrit, confirmation vocale pour les actions sensibles,
  « Jarvis, stop total » pour tout arrêter.

## Installation
1. `installer.bat` (environnement Python et modules)
2. `installer_ia_locale.bat` (IA locale : Ollama, modèles, voix, ~12 Go)
3. Copier `.env.exemple` en `.env` et remplir ce qui sert
4. `lancer.bat`, ou `installer_demarrage.bat` pour qu'il tourne caché et démarre avec Windows

Arrêt : `arreter_jarvis.bat` · Journal : `jarvis.log`
