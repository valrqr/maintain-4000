# =============================================================================
# 02_build_tables.py : ÉTAPE 2 — DES VOLS AUX 2 TABLES D'ANALYSE
# -----------------------------------------------------------------------------
# Pour chaque vol de data/raw/ (produit par l'étape 0) : retrouve le type
# d'avion, la configuration de piste, détecte les paliers (features.py) et
# estime leur coût en carburant et en CO2 (fuel.py).
# Produit 2 tables Parquet dans data/processed/, prêtes pour BigQuery :
#   flights    : 1 ligne par vol
#   level_offs : 1 ligne par palier (arrivées seulement)
# ⚠️ Copie annotée pour la lecture : exécute la version du dossier scripts/.
# =============================================================================

# Docstring : les 2 tables produites et la commande d'usage.
"""Turn the flights in data/raw/ into 2 analytical tables (Parquet), ready for BigQuery.

    flights.parquet     one row per flight (arrival or departure)
    level_offs.parquet  one row per level segment during descent (arrivals)

Usage:
    python scripts/02_build_tables.py
"""
from __future__ import annotations

# sys : pour ajouter src/ aux dossiers où Python cherche les modules.
import sys
# Path : manipuler les chemins de fichiers.
from pathlib import Path

import pandas as pd

# Racine du repo : ce script est dans scripts/, donc on remonte d'un dossier
# (.parents[1]). Puis on ajoute src/ pour pouvoir importer eco_nice.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# Nos fonctions : détection des paliers et de la piste, estimations carburant.
# `# noqa: E402` : accepte un import placé après du code (le sys.path.insert).
from eco_nice.features import detect_level_offs, runway_config  # noqa: E402
from eco_nice.fuel import co2_kg, is_proxy, level_off_excess_fuel_kg  # noqa: E402

# Dossier d'entrée (vols découpés) et dossier de sortie (tables d'analyse).
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"


# Construit un dictionnaire « identifiant ADS-B de l'avion → type OACI ».
# L'ADS-B ne transmet pas le type d'avion : on le retrouve dans la base des
# avions fournie avec la librairie traffic (téléchargée au 1er lancement).
def typecode_lookup() -> dict:
    """icao24 -> ICAO type code, from the aircraft database shipped with `traffic`."""
    try:
        # Import ici plutôt qu'en haut du fichier : si la base est indisponible,
        # seule cette fonction échoue, et le script continue sans les types.
        from traffic.data import aircraft
        # Garde 2 colonnes et supprime les lignes incomplètes (dropna).
        db = aircraft.data[["icao24", "typecode"]].dropna()
        # zip associe les 2 colonnes ligne à ligne ; dict(...) en fait un
        # dictionnaire. Identifiant en minuscules, type en majuscules.
        return dict(zip(db["icao24"].str.lower(), db["typecode"].str.upper()))
    # `as e` récupère l'erreur pour l'afficher.
    except Exception as e:  # base indisponible : les colonnes carburant seront vides
        print(f"warning: aircraft database unavailable ({e})")
        # Dictionnaire vide : aucun type trouvé, mais le script continue.
        return {}


# Fonction principale. `-> None` : elle ne renvoie rien, elle écrit des fichiers.
def main() -> None:
    # Table de correspondance avion → type, chargée une seule fois.
    types = typecode_lookup()
    # Deux listes vides qui vont accumuler les lignes des 2 tables.
    flights, levels = [], []

    # Parcourt chaque fichier .parquet de data/raw/, dans l'ordre alphabétique
    # (donc par sens puis par date : arr_… puis dep_…).
    for path in sorted(RAW.glob("*.parquet")):
        # Les 3 premiers caractères du nom de fichier : "arr" ou "dep".
        direction = path.name[:3]                     # "arr" or "dep"
        # Lecture de toutes les positions du fichier.
        positions = pd.read_parquet(path)

        # Regroupe les positions par vol : à chaque tour, fid = identifiant
        # du vol, df = ses positions (comme un GROUP BY en SQL).
        for fid, df in positions.groupby("flight_id"):
            # Identifiant ADS-B de l'avion (le même sur toutes les lignes du
            # vol : on prend la 1re avec .iloc[0]).
            icao24 = df["icao24"].iloc[0]
            # Type d'avion, ou None s'il est inconnu (.get ne plante pas).
            typecode = types.get(icao24)

            # Ajoute une ligne (un dictionnaire) à la table flights.
            flights.append({
                "flight_id": fid,
                "icao24": icao24,
                "callsign": df["callsign"].iloc[0],
                "typecode": typecode,
                # True si le carburant est estimé avec un type de remplacement.
                "fuel_type_proxy": is_proxy(typecode),
                "direction": direction,
                # Premier et dernier instant observé du vol.
                "first_seen": df["timestamp"].min(),
                "last_seen": df["timestamp"].max(),
                # Configuration de piste ("04", "22" ou None), déduite du cap.
                "runway": runway_config(df, direction),
            })

            # Les paliers ne concernent que les arrivées : pour un départ,
            # on passe directement au vol suivant (`continue`).
            if direction != "arr":
                continue
            # Pour chaque palier détecté (.iterrows() parcourt les lignes ;
            # `_` = numéro de ligne ignoré, lv = la ligne du palier)…
            for _, lv in detect_level_offs(df).iterrows():
                # …estimation du carburant en trop pour ce palier…
                fuel = level_off_excess_fuel_kg(
                    typecode, lv["duration_s"], lv["altitude_ft"], lv["groundspeed_kt"])
                # …et ajout d'une ligne à la table level_offs.
                levels.append({
                    "flight_id": fid,
                    # `**lv.to_dict()` recopie toutes les colonnes du palier
                    # (start, end, altitude_ft, groundspeed_kt, duration_s).
                    **lv.to_dict(),
                    "excess_fuel_kg": fuel,
                    "excess_co2_kg": co2_kg(fuel),
                })

    # Crée data/processed/ si besoin (sans erreur s'il existe déjà).
    OUT.mkdir(parents=True, exist_ok=True)
    # Options d'écriture Parquet, regroupées dans un dictionnaire réutilisé 2 fois :
    # - index=False : ne pas écrire la colonne d'index de pandas ;
    # - coerce_timestamps="us" : enregistrer les dates à la MICROseconde.
    #   Par défaut, pandas les écrit à la NANOseconde, un format que BigQuery ne
    #   sait pas lire comme une date : il les charge comme de simples nombres
    #   (INT64), et dbt plante ensuite sur DATE(INT64, …) ;
    # - allow_truncated_timestamps=True : accepte de perdre les nanosecondes
    #   (sans intérêt ici, les positions sont à la seconde).
    # Timestamps in microseconds: BigQuery reads nanosecond Parquet timestamps as INT64.
    parquet = dict(index=False, coerce_timestamps="us", allow_truncated_timestamps=True)
    # Liste de dictionnaires → DataFrame → fichier Parquet. `**parquet` « déplie »
    # le dictionnaire en paramètres nommés (index=False, coerce_timestamps="us"…).
    pd.DataFrame(flights).to_parquet(OUT / "flights.parquet", **parquet)
    pd.DataFrame(levels).to_parquet(OUT / "level_offs.parquet", **parquet)
    # Résumé : nombre de lignes de chaque table.
    print(f"flights: {len(flights)} rows | level_offs: {len(levels)} rows")


# Point d'entrée : ce bloc ne s'exécute que si on lance le fichier directement.
if __name__ == "__main__":
    main()
