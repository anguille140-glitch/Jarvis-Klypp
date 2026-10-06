"""Enregistre ton adresse (ou ta ville) pour la météo et le globe du plan de travail. Elle reste sur ton PC (.env)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import plan_de_travail  # noqa: E402

print("Ton adresse (ex. : 12 rue des Lilas, 74300 Cluses) ou juste ta ville.")
print("Elle est enregistrée seulement sur ton PC, dans le fichier .env.\n")
adresse = input("Adresse : ").strip()
print("\nRecherche...")
out = plan_de_travail.set_address(adresse)
print(out.replace("OK : ", "C'est fait : ").replace("ÉCHEC : ", "Problème : "))
if out.startswith("OK"):
    lieu = plan_de_travail.locate()
    print(f"Coordonnées : {lieu['lat']:.4f}, {lieu['lon']:.4f}")
    print("Le globe du plan de travail zoomera là. (Pas besoin de redémarrer Jarvis.)")
