# =============================================================================
# 00_split_flights.py : ÉTAPE 0 DU PIPELINE — DES POSITIONS AUX VOLS
# -----------------------------------------------------------------------------
# Lit les fichiers collectés (CSV.gz horaires), affiche un contrôle qualité,
# découpe en vols (voir src/eco_nice/split.py) et écrit un fichier Parquet
# par jour et par sens (arr_AAAA-MM-JJ / dep_AAAA-MM-JJ) dans data/raw/.
# Parquet = format de fichier en colonnes, compact et rapide, que lit l'étape 2.
# ⚠️ Copie annotée pour la lecture : exécute la version du dossier scripts/.
# =============================================================================

# Docstring : rôle du script et commande pour le lancer.
"""Collected positions (opensky_live or receiver CSV.gz) -> one Parquet per day and
direction in data/raw/, the format 02_build_tables.py reads.

Also prints a data-quality check: hours covered, gaps, flights found.

Usage:
    python3 scripts/00_split_flights.py --src data/opensky_live
"""
from __future__ import annotations

# argparse : lit les options passées en ligne de commande (ex. --src …).
import argparse
# sys : accès à l'interpréteur Python (ici, la liste des dossiers où chercher les modules).
import sys
# Path : manipule les chemins de fichiers proprement (Mac, Windows, Linux).
from pathlib import Path

import pandas as pd

# Dossier racine du projet : __file__ = ce script ; .resolve() = chemin complet ;
# .parents[1] = remonte de 2 niveaux (scripts/ → racine du repo).
ROOT = Path(__file__).resolve().parents[1]
# Ajoute src/ en tête des endroits où Python cherche les modules, pour pouvoir
# faire `from eco_nice…` sans installer le package.
sys.path.insert(0, str(ROOT / "src"))

# Import de nos fonctions de découpage. `# noqa: E402` dit à l'outil de style
# (flake8) d'accepter un import qui n'est pas tout en haut du fichier.
from eco_nice.split import load_positions, split_flights  # noqa: E402

# Dossier de sortie : racine/data/raw. L'opérateur `/` assemble les chemins.
RAW = ROOT / "data" / "raw"


# Fonction principale. `-> None` : elle ne renvoie rien (elle agit).
def main() -> None:
    # Prépare la lecture des options de la ligne de commande.
    p = argparse.ArgumentParser()
    # Option --src : dossier des fichiers collectés (valeur par défaut fournie).
    p.add_argument("--src", default="data/opensky_live")
    # Lit les options réellement tapées ; a.src contient la valeur.
    a = p.parse_args()

    # Tous les .csv.gz du dossier ET de ses sous-dossiers (rglob = recherche
    # récursive), triés par nom donc par date.
    files = sorted(Path(a.src).rglob("*.csv.gz"))
    # Aucun fichier → on arrête le script avec un message clair.
    if not files:
        raise SystemExit(f"No .csv.gz under {a.src}")
    # Lecture et fusion de tous les fichiers en un tableau propre.
    df = load_positions(files)

    # --- contrôle qualité ----------------------------------------------------
    # Heure « arrondie à l'heure inférieure » de chaque position (floor = plancher).
    hours = df["timestamp"].dt.floor("h")
    # Toutes les heures qui DEVRAIENT exister entre la 1re et la dernière.
    expected = pd.date_range(hours.min(), hours.max(), freq="h")
    # Heures attendues mais absentes des données (.difference = « ce qui manque »).
    missing = expected.difference(hours.unique())
    # Résumé : nb de fichiers, de positions (`:,` ajoute des séparateurs de
    # milliers), et d'avions distincts (.nunique() = nombre de valeurs uniques).
    print(f"Files: {len(files)} | positions: {len(df):,} | aircraft: {df['icao24'].nunique()}")
    # Période couverte, au format date-heure.
    print(f"From {df['timestamp'].min():%Y-%m-%d %H:%M} to {df['timestamp'].max():%Y-%m-%d %H:%M} UTC")
    # Nombre d'heures sans données, + jusqu'à 5 exemples (missing[:5]) s'il y en a.
    # ', '.join(...) colle les textes avec une virgule entre eux.
    print(f"Hours without any data: {len(missing)}"
          + (f" (e.g. {', '.join(f'{h:%d/%m %Hh}' for h in missing[:5])})" if len(missing) else ""))

    # --- découpage et enregistrement -------------------------------------------
    # Découpe en vols et ne garde que les arrivées/départs de Nice.
    flights = split_flights(df)
    # Rien trouvé → arrêt avec un message (problème probable dans les données).
    if flights.empty:
        raise SystemExit("No arrival/departure at LFMN found: check the data.")
    # Nombre de vols distincts par sens (arr / dep).
    n = flights.groupby("direction")["flight_id"].nunique()
    # n.get('arr', 0) : la valeur pour 'arr', ou 0 si absente.
    print(f"Arrivals: {n.get('arr', 0)} | departures: {n.get('dep', 0)}")

    # Crée data/raw/ s'il n'existe pas (parents=True : crée aussi les dossiers
    # parents ; exist_ok=True : pas d'erreur s'il existe déjà).
    RAW.mkdir(parents=True, exist_ok=True)
    # Jour de rattachement d'un vol = date de son DERNIER point.
    # .transform("max") renvoie, pour chaque ligne, le max de son vol ;
    # .dt.strftime("%Y-%m-%d") formate la date en texte AAAA-MM-JJ.
    flights["day"] = flights.groupby("flight_id")["timestamp"].transform("max").dt.strftime("%Y-%m-%d")
    # Un fichier par couple (sens, jour). part = lignes de ce couple.
    for (direction, day), part in flights.groupby(["direction", "day"]):
        # Nom du fichier, ex. data/raw/arr_2026-11-15.parquet
        out = RAW / f"{direction}_{day}.parquet"
        # Retire les colonnes de travail (day, direction : déjà dans le nom du
        # fichier) puis écrit en Parquet, sans la colonne d'index pandas.
        part.drop(columns=["day", "direction"]).to_parquet(out, index=False)
        # .relative_to(ROOT) : affiche un chemin court, depuis la racine du repo.
        print(f"  saved {out.relative_to(ROOT)}: {part['flight_id'].nunique()} flights")


# Ce bloc ne s'exécute que si on lance le fichier directement
# (python scripts/00_split_flights.py), pas si on l'importe depuis un autre fichier.
if __name__ == "__main__":
    main()
