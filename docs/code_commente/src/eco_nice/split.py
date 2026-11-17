# =============================================================================
# split.py : DÉCOUPER LE FLUX DE POSITIONS EN VOLS
# -----------------------------------------------------------------------------
# Le collecteur enregistre en vrac toutes les positions de tous les avions
# autour de Nice. Ce fichier :
#   1. regroupe les positions par avion,
#   2. coupe la trace de chaque avion en vols séparés,
#   3. ne garde que les arrivées à Nice et les départs de Nice.
# Analogie : on reçoit une boîte de photos en vrac de toutes les voitures d'un
# carrefour ; on les trie par plaque, puis par trajet, et on ne garde que les
# voitures qui entrent ou sortent d'un parking précis.
# =============================================================================

# Docstring du module.
"""Turn a continuous stream of positions (all aircraft around Nice) into flights,
then keep only arrivals at and departures from LFMN.

Pure pandas: works on files from opensky_live_collector.py and adsb_logger.py.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# Coordonnées du point de référence de l'aéroport de Nice (degrés décimaux).
# `a, b = x, y` : deux constantes en une ligne.
LFMN_LAT, LFMN_LON = 43.6584, 7.2159
# Le 1er (départ) ou le dernier (arrivée) point doit être à moins de 8 km de Nice…
NEAR_AIRPORT_KM = 8          # first/last point must be this close to LFMN...
# …et sous 2 500 ft.
LOW_ALT_FT = 2_500           # ...and this low
# L'avion doit monter ou descendre d'au moins 3 000 ft (écarte les bouts de trace).
MIN_CLIMB_FT = 3_000         # the flight must climb/descend at least this much
# Un vol qui ne dépasse jamais 5 000 ft est écarté : ce sont surtout les
# hélicoptères Nice ↔ Monaco, qui volent bas.
MIN_MAX_ALT_FT = 5_000       # drops helicopters (Nice <-> Monaco shuttles fly low)
# Plus de 20 min sans nouvelle d'un avion → on considère que c'est un nouveau vol.
MAX_GAP_MIN = 20             # a longer silence starts a new flight
# Un passage « au sol » de moins de 5 min entre deux moments en vol est un
# simple bug de données, pas une vraie escale.
MIN_GROUND_STOP_MIN = 5      # shorter 'on ground' runs between airborne points = glitches
# Un vol de moins de 10 points est trop court pour être analysé.
MIN_POINTS = 10


# Distance « à vol d'oiseau » (en km) entre une position et l'aéroport de Nice,
# avec la formule de haversine (tient compte de la courbure de la Terre).
# lat0/lon0 ont Nice comme valeur par défaut.
def haversine_km(lat, lon, lat0=LFMN_LAT, lon0=LFMN_LON):
    # Les fonctions trigonométriques attendent des radians, pas des degrés.
    lat, lon = np.radians(lat), np.radians(lon)
    lat0, lon0 = np.radians(lat0), np.radians(lon0)
    # Cœur de la formule de haversine. `** 2` = « au carré ».
    a = (np.sin((lat - lat0) / 2) ** 2
         + np.cos(lat) * np.cos(lat0) * np.sin((lon - lon0) / 2) ** 2)
    # Rayon de la Terre (6 371 km) × angle au centre = distance en km.
    return 6371 * 2 * np.arcsin(np.sqrt(a))


# Lit tous les fichiers CSV.gz collectés et les fusionne en un seul tableau propre.
def load_positions(files) -> pd.DataFrame:
    # pd.read_csv lit un fichier (même compressé .gz, automatiquement).
    # dtype=…str : force icao24 et callsign en texte (sinon "000123" deviendrait 123).
    # La parenthèse `(… for f in files)` lit les fichiers un par un (générateur),
    # pd.concat les empile ; ignore_index=True renumérote les lignes.
    df = pd.concat((pd.read_csv(f, dtype={"icao24": str, "callsign": str})
                    for f in files), ignore_index=True)
    # Conversion du texte en vraies dates (UTC).
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    # Indicatif vide → "" ; .str.strip() enlève les espaces autour.
    df["callsign"] = df["callsign"].fillna("").str.strip()
    # Dans un CSV, "True" est du texte : on le reconvertit en vrai booléen.
    # .astype(str) → texte ; .str.lower() → minuscules ; .eq("true") → True/False.
    df["onground"] = df["onground"].astype(str).str.lower().eq("true")
    return (df.drop_duplicates(["icao24", "timestamp"])  # supprime les doublons (même avion, même heure)
              .sort_values(["icao24", "timestamp"])     # trie par avion puis par heure
              .reset_index(drop=True))                  # renumérote les lignes


# Pour UN avion, donne à chaque position un numéro de vol (0, 0, 0, 1, 1…).
# On coupe : (1) après un long silence ; (2) au milieu de chaque escale au sol
# située entre deux moments en vol (arrivée … escale … nouveau départ).
def _segment_ids(g: pd.DataFrame) -> np.ndarray:
    """Cut one aircraft's track on long gaps and in the middle of each ground stop
    between two airborne parts (arrival ... turnaround ... departure)."""
    t = g["timestamp"]
    # new = True là où un nouveau vol commence. Coupure n°1 : écart avec le point
    # précédent > 20 min (20 × 60 s). .to_numpy() → tableau numpy modifiable.
    new = t.diff().dt.total_seconds().gt(MAX_GAP_MIN * 60).to_numpy()

    # og = tableau True/False « au sol ».
    og = g["onground"].to_numpy()
    # Repère le début de chaque série identique (sol ou vol) :
    # og[1:] != og[:-1] compare chaque point au précédent ;
    # np.r_[True, …] ajoute True en tête (le 1er point commence toujours une série).
    run_start = np.r_[True, og[1:] != og[:-1]]
    # Numéro de série pour chaque point (somme cumulée des débuts).
    run_id = np.cumsum(run_start)
    # Pour chaque série « au sol » (np.unique = numéros sans doublon)…
    for rid in np.unique(run_id[og]):
        # …positions (indices) des points de cette série.
        idx = np.flatnonzero(run_id == rid)
        # Indice du point juste avant et juste après la série.
        before, after = idx[0] - 1, idx[-1] + 1
        # Si la trace commence ou finit au sol, ce n'est pas une escale entre
        # deux vols : on passe à la série suivante (`continue`).
        if before < 0 or after >= len(og):            # track starts/ends on the ground
            continue
        # Durée de l'arrêt au sol en secondes (.iloc[i] = i-ème point).
        stop_s = (t.iloc[idx[-1]] - t.iloc[idx[0]]).total_seconds()
        # Moins de 5 min : bug de données, pas une vraie escale → on ignore.
        if stop_s < MIN_GROUND_STOP_MIN * 60:         # a glitch, not a real stop
            continue
        # Vraie escale : on coupe au MILIEU de l'arrêt (len(idx) // 2), pour que
        # l'arrivée garde son roulage d'entrée et le départ son roulage de sortie.
        new[idx[len(idx) // 2]] = True                # air -> ground -> air: turnaround
    # Somme cumulée des coupures → numéro de vol de chaque point.
    return np.cumsum(new)


# Classe un vol : "arr" (arrivée à Nice), "dep" (départ de Nice) ou None (autre).
def classify(f: pd.DataFrame) -> str | None:
    """'arr', 'dep' or None (overflight, helicopter, too short...)."""
    # Trop peu de points, ou altitude max < 5 000 ft (hélico) → on écarte.
    if len(f) < MIN_POINTS or f["altitude"].max() < MIN_MAX_ALT_FT:
        return None
    # Premier et dernier point du vol (.iloc[0] et .iloc[-1]).
    first, last = f.iloc[0], f.iloc[-1]
    # Distance à Nice du premier et du dernier point.
    d_first = haversine_km(first["latitude"], first["longitude"])
    d_last = haversine_km(last["latitude"], last["longitude"])
    # Altitude maximale atteinte pendant le vol.
    peak = f["altitude"].max()
    # ARRIVÉE : le vol FINIT près de Nice, bas, après être descendu d'au moins
    # 3 000 ft. Le `\` en fin de ligne permet de continuer la condition à la ligne.
    if d_last <= NEAR_AIRPORT_KM and last["altitude"] <= LOW_ALT_FT \
            and peak - last["altitude"] >= MIN_CLIMB_FT:
        return "arr"
    # DÉPART : le vol COMMENCE près de Nice, bas, puis monte d'au moins 3 000 ft.
    if d_first <= NEAR_AIRPORT_KM and first["altitude"] <= LOW_ALT_FT \
            and peak - first["altitude"] >= MIN_CLIMB_FT:
        return "dep"
    # Ni l'un ni l'autre (survol, trace partielle…).
    return None


# Fonction principale : ajoute flight_id et direction, garde seulement les
# arrivées et départs de Nice.
def split_flights(df: pd.DataFrame) -> pd.DataFrame:
    """Add flight_id and direction; return only LFMN arrivals and departures."""
    # Liste (vide au départ) où l'on accumule les vols retenus.
    out = []
    # Parcourt chaque avion : icao24 = identifiant, g = ses positions.
    # sort=False : garde l'ordre d'apparition (un peu plus rapide).
    for icao24, g in df.groupby("icao24", sort=False):
        g = g.reset_index(drop=True)
        # Découpe les positions de cet avion en vols ; `_` = numéro ignoré,
        # f = positions d'un vol.
        for _, f in g.groupby(_segment_ids(g)):
            direction = classify(f)
            # Ni arrivée ni départ → on passe au vol suivant.
            if direction is None:
                continue
            # Premier indicatif non vide du vol ; "NOCALL" s'il n'y en a aucun.
            # next(générateur, valeur_par_défaut) renvoie le 1er élément trouvé.
            cs = next((c for c in f["callsign"] if c), "NOCALL")
            # Identifiant unique : avion_indicatif_dateheure (ex. 3944ef_AFR123_20261115T0800).
            # f"…{x}…" = f-string, insère des valeurs dans le texte ;
            # :%Y%m%dT%H%M = format de date (année mois jour T heure minute).
            fid = f"{icao24}_{cs}_{f['timestamp'].iloc[0]:%Y%m%dT%H%M}"
            # Ajoute les colonnes flight_id, direction, callsign et garde le vol.
            out.append(f.assign(flight_id=fid, direction=direction, callsign=cs))
    # Aucun vol retenu : on renvoie un tableau vide avec les bonnes colonnes
    # (df.iloc[0:0] = zéro ligne, mêmes colonnes).
    if not out:
        return df.iloc[0:0].assign(flight_id="", direction="")
    # Empile tous les vols retenus en un seul tableau.
    return pd.concat(out, ignore_index=True)
