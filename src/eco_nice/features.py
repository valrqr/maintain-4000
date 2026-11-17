"""Measurements on a single flight trajectory: descent level-offs and runway configuration.

Expected columns (as produced by scripts/00_split_flights.py):
    timestamp (UTC), altitude (ft, barometric), groundspeed (kt), track (deg), onground (bool)

Everything here is pure pandas and testable without network access.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C

COLONNES = ["start", "end", "altitude_ft", "groundspeed_kt", "duration_s"]


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    """Sort by time and make sure every column has a plain, predictable type."""
    df = df.sort_values("timestamp").reset_index(drop=True).copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["onground"] = df["onground"].fillna(False).astype(bool)
    for col in ("altitude", "groundspeed", "track"):
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")
    return df


# --------------------------------------------------------------------------- #
# Paliers en descente
# Fonction écrite par Valentin (exercice/mes_paliers.py), validée par les tests.
# --------------------------------------------------------------------------- #
def detect_level_offs(df: pd.DataFrame) -> pd.DataFrame:
    """One row per level segment between the top of descent and 1,500 ft."""
    # ÉTAPES 1 à 3 : trier, garder le vol, garder la descente
    df = _prepare(df)
    vol = df[df["onground"] == False]  # noqa: E712
    if vol.empty:
        return pd.DataFrame(columns=COLONNES)

    # La descente commence au DERNIER point du sommet (marge de 200 ft) :
    # la croisière d'un vol court n'est pas un palier.
    au_sommet = vol["altitude"] >= vol["altitude"].max() - C.TOP_OF_DESCENT_MARGIN_FT
    dernier_point_du_sommet = vol.index[au_sommet][-1]
    descente = vol.loc[dernier_point_du_sommet:]

    paliers = []              # les paliers terminés
    palier_en_cours = None    # None = pas de palier en cours

    # ÉTAPES 4 et 5 : comparer chaque point au précédent, regrouper les tronçons plats
    for i in range(1, len(descente)):
        avant = descente.iloc[i - 1]
        apres = descente.iloc[i]
        secondes = (apres["timestamp"] - avant["timestamp"]).total_seconds()
        pente = (apres["altitude"] - avant["altitude"]) / secondes * 60
        a_plat = (
            abs(pente) < C.LEVEL_VS_THRESHOLD_FPM
            and C.LEVEL_MIN_ALT_FT <= apres["altitude"] <= C.LEVEL_MAX_ALT_FT
            and secondes <= C.MAX_GAP_S
        )

        if a_plat and palier_en_cours is None:
            # 1. C'est le début de mon palier
            palier_en_cours = {
                "start": avant["timestamp"],
                "end": apres["timestamp"],
                "altitudes": [avant["altitude"], apres["altitude"]],
                "vitesses": [avant["groundspeed"], apres["groundspeed"]],
            }
        elif a_plat:
            # 2. Mon palier continue
            palier_en_cours["end"] = apres["timestamp"]
            palier_en_cours["altitudes"].append(apres["altitude"])
            palier_en_cours["vitesses"].append(apres["groundspeed"])
        elif palier_en_cours is not None:
            # 3. Fin du palier : on le range et on repart de zéro
            paliers.append(palier_en_cours)
            palier_en_cours = None

    # 4. La trajectoire s'est terminée en plein palier : on le range quand même
    if palier_en_cours is not None:
        paliers.append(palier_en_cours)

    # ÉTAPES 6 et 7 : mesurer chaque palier, garder ceux d'au moins 20 s
    lignes = []
    for p in paliers:
        duree = (p["end"] - p["start"]).total_seconds()
        if duree >= C.LEVEL_MIN_DURATION_S:
            lignes.append({
                "start": p["start"],
                "end": p["end"],
                "altitude_ft": round(pd.Series(p["altitudes"]).median(), -2),
                "groundspeed_kt": pd.Series(p["vitesses"]).median(),
                "duration_s": duree,
            })
    return pd.DataFrame(lignes, columns=COLONNES)


# --------------------------------------------------------------------------- #
# Runway configuration (04 = towards NE, 22 = towards SW) from the track
# --------------------------------------------------------------------------- #
RUNWAY_HEADINGS = {"04": 44.0, "22": 224.0}   # LFMN runways 04L/R - 22L/R


def runway_config(df: pd.DataFrame, direction: str, max_alt_ft: float = 3_000,
                  n_points: int = 6, tolerance_deg: float = 35) -> str | None:
    """'04' or '22' from the mean track of the lowest airborne points: the last ones
    of an arrival or the first ones of a departure. Robust to 25-s sampling, unlike
    ILS-alignment methods that need dense data. L/R parallels are not separated."""
    d = _prepare(df)
    air = d[~d["onground"] & d["altitude"].le(max_alt_ft) & d["track"].notna()]
    pts = air.tail(n_points) if direction == "arr" else air.head(n_points)
    if len(pts) < 2:
        return None
    rad = np.radians(pts["track"].astype(float))
    mean = np.degrees(np.arctan2(np.sin(rad).mean(), np.cos(rad).mean())) % 360
    for name, hdg in RUNWAY_HEADINGS.items():
        if abs((mean - hdg + 180) % 360 - 180) <= tolerance_deg:
            return name
    return None
