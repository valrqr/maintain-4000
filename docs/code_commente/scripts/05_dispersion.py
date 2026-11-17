# =============================================================================
# 05_dispersion.py : LES FLUX D'ARRIVÉE S'ALIGNENT-ILS EN APPROCHANT DE NICE ?
# -----------------------------------------------------------------------------
# On trace des cercles de 10, 20, 40 et 60 km autour de l'aéroport. Pour chaque
# arrivée, on note par quelle direction (le « gisement ») elle entre dans chaque
# cercle. Si tous les avions entrent par le même côté, la dispersion est faible ;
# s'ils viennent de partout, elle est forte.
# Analogie : des gens qui convergent vers la porte d'un stade. Loin du stade, ils
# arrivent de toutes les rues ; devant la porte, ils sont tous dans la même file.
# ⚠️ Copie annotée pour la lecture : exécute la version du dossier scripts/.
# =============================================================================

# Docstring : rôle du script et commande pour le lancer.
"""Lateral dispersion of LFMN arrivals by distance from the airport.

For each ring (10, 20, 40, 60 km), takes the point where each arrival enters
the ring and measures how spread out the entry bearings are.

Usage:
    python scripts/05_dispersion.py
"""
# glob : trouve tous les fichiers qui correspondent à un motif (arr_*.parquet).
import glob
# sys : permet d'ajouter le dossier src/ à la liste des endroits où Python cherche les modules.
import sys
# Path : manipule les chemins de fichiers proprement.
from pathlib import Path

# numpy : calcul numérique (trigonométrie sur des colonnes entières d'un coup).
import numpy as np
import pandas as pd

# Racine du repo = dossier parent de scripts/.
ROOT = Path(__file__).resolve().parents[1]
# On rend le package eco_nice (dans src/) importable.
sys.path.insert(0, str(ROOT / "src"))
# haversine_km : distance à vol d'oiseau jusqu'à LFMN, en km.
from eco_nice.split import haversine_km  # noqa: E402

# Coordonnées de l'aéroport de Nice (point de référence des cercles).
LAT0, LON0 = 43.6584, 7.2159


# Gisement = direction de l'avion VUE DEPUIS l'aéroport, en degrés
# (0 = nord, 90 = est, 180 = sud, 270 = ouest). Formule classique du cap
# initial sur une sphère, appliquée de l'aéroport vers l'avion.
def gisement(lat, lon):
    # Écart de longitude, converti en radians (les fonctions sin/cos travaillent en radians).
    dlon = np.radians(lon - LON0)
    lat_r, lat0_r = np.radians(lat), np.radians(LAT0)
    # y : composante est-ouest ; x : composante nord-sud.
    y = np.sin(dlon) * np.cos(lat_r)
    x = np.cos(lat0_r) * np.sin(lat_r) - np.sin(lat0_r) * np.cos(lat_r) * np.cos(dlon)
    # arctan2 donne l'angle ; « % 360 » le ramène entre 0 et 360°.
    return np.degrees(np.arctan2(y, x)) % 360


# On empile toutes les arrivées de tous les jours en une seule table.
arr = pd.concat(pd.read_parquet(f) for f in glob.glob(str(ROOT / "data/raw/arr_*.parquet")))
# Distance de chaque position à l'aéroport.
arr["dist_km"] = haversine_km(arr["latitude"], arr["longitude"])

# Une ligne de résultat par rayon.
lignes = []
for rayon in [10, 20, 40, 60]:
    # On garde les positions situées HORS du cercle, triées dans le temps.
    dehors = arr[arr["dist_km"] >= rayon].sort_values("timestamp")
    # Pour une arrivée, le dernier point hors du cercle = le moment où elle y entre.
    passage = dehors.groupby("flight_id").tail(1)
    # Gisement de ce point d'entrée, en radians.
    g = np.radians(gisement(passage["latitude"], passage["longitude"]))
    # Moyenne circulaire : on additionne des flèches de longueur 1. Si elles
    # pointent toutes du même côté, la flèche moyenne est longue (R proche de 1) ;
    # si elles partent dans tous les sens, elles s'annulent (R proche de 0).
    # (On ne peut pas faire une moyenne simple : la moyenne de 350° et 10° n'est pas 180°.)
    R = np.hypot(np.sin(g).mean(), np.cos(g).mean())
    lignes.append({
        "rayon_km": rayon,
        # Nombre d'arrivées vues à cette distance (moins à 60 km : bord de la zone de collecte).
        "vols": len(passage),
        # Écart-type circulaire, en degrés : ≈ 0° = un seul couloir, > 60° = de partout.
        "dispersion_deg": round(np.degrees(np.sqrt(-2 * np.log(R))), 1),
        # Nombre de « parts de gâteau » de 30° utilisées par au moins une arrivée.
        "secteurs_30deg": int((np.degrees(g) // 30).nunique()),
    })

# Affichage du tableau, sans la colonne d'index.
print(pd.DataFrame(lignes).to_string(index=False))
