# =============================================================================
# features.py : CE QUE L'ON MESURE SUR UN VOL
# -----------------------------------------------------------------------------
# Entrée : la trajectoire d'UN vol (un tableau pandas, une ligne par position).
# Sortie : ses paliers en descente, et sa configuration de piste.
# Analogie : on parcourt un sentier de randonnée borne par borne ; un tronçon
# est « plat » si l'altitude change à peine entre deux bornes, et un palier,
# c'est plusieurs tronçons plats d'affilée.
# La fonction detect_level_offs est celle que tu as écrite dans l'exercice.
# =============================================================================

# Docstring du module : ce qu'il mesure et les colonnes attendues.
"""Measurements on a single flight trajectory: descent level-offs and runway configuration.

Expected columns (as produced by scripts/00_split_flights.py):
    timestamp (UTC), altitude (ft, barometric), groundspeed (kt), track (deg), onground (bool)

Everything here is pure pandas and testable without network access.
"""
# Permet les annotations de type modernes (ex. `str | None`).
from __future__ import annotations

# numpy : trigonométrie pour la moyenne des caps (runway_config).
import numpy as np
import pandas as pd

# Nos réglages (config.py), sous le nom court C.
from . import config as C

# Les colonnes du tableau renvoyé par detect_level_offs (même quand il est vide).
COLONNES = ["start", "end", "altitude_ft", "groundspeed_kt", "duration_s"]


# Prépare le tableau d'un vol : tri par heure + types de colonnes prévisibles.
# Le `_` au début du nom = fonction interne au module.
def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    """Sort by time and make sure every column has a plain, predictable type."""
    # Trie par heure, renumérote 0,1,2… et travaille sur une copie.
    df = df.sort_values("timestamp").reset_index(drop=True).copy()
    # Dates en UTC.
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    # « Au sol » en vrais booléens ; valeur manquante = en vol (False).
    df["onground"] = df["onground"].fillna(False).astype(bool)
    # Colonnes numériques en nombres à virgule ; ce qui n'est pas un nombre
    # devient NaN (errors="coerce") au lieu de faire planter le script.
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
    # Points en vol seulement. `# noqa: E712` dit à l'outil de style d'accepter
    # l'écriture `== False` (plus lisible ici que `~df["onground"]`).
    vol = df[df["onground"] == False]  # noqa: E712
    # Aucun point en vol → aucun palier : tableau vide avec les bonnes colonnes.
    if vol.empty:
        return pd.DataFrame(columns=COLONNES)

    # La descente commence au DERNIER point du sommet (marge de 200 ft) :
    # la croisière d'un vol court n'est pas un palier.
    # au_sommet = True pour chaque point à moins de 200 ft de l'altitude max.
    au_sommet = vol["altitude"] >= vol["altitude"].max() - C.TOP_OF_DESCENT_MARGIN_FT
    # vol.index[au_sommet] = numéros de ligne des points au sommet ;
    # [-1] = le dernier d'entre eux.
    dernier_point_du_sommet = vol.index[au_sommet][-1]
    # Tout ce qui suit ce point = la descente.
    descente = vol.loc[dernier_point_du_sommet:]

    paliers = []              # les paliers terminés
    palier_en_cours = None    # None = pas de palier en cours

    # ÉTAPES 4 et 5 : comparer chaque point au précédent, regrouper les tronçons plats
    # On commence à 1 : le point 0 n'a pas de point « avant ».
    for i in range(1, len(descente)):
        # .iloc[i] = la ligne n° i (en comptant depuis 0).
        avant = descente.iloc[i - 1]
        apres = descente.iloc[i]
        # Temps écoulé entre les deux points, en secondes.
        secondes = (apres["timestamp"] - avant["timestamp"]).total_seconds()
        # Pente en ft/min : variation d'altitude / secondes × 60.
        pente = (apres["altitude"] - avant["altitude"]) / secondes * 60
        # Le tronçon est « à plat » si les 3 conditions sont vraies :
        a_plat = (
            # pente faible (montée ou descente de moins de 300 ft/min),
            abs(pente) < C.LEVEL_VS_THRESHOLD_FPM
            # altitude entre 1 500 et 30 000 ft (ni approche finale, ni croisière haute),
            and C.LEVEL_MIN_ALT_FT <= apres["altitude"] <= C.LEVEL_MAX_ALT_FT
            # et pas de trou de données de plus de 60 s entre les deux points.
            and secondes <= C.MAX_GAP_S
        )

        # `if / elif` : Python teste dans l'ordre et s'arrête à la 1re condition vraie.
        if a_plat and palier_en_cours is None:
            # 1. C'est le début de mon palier
            # Un dictionnaire qui mémorise le palier : début, fin, et les listes
            # d'altitudes et de vitesses de ses points.
            palier_en_cours = {
                "start": avant["timestamp"],
                "end": apres["timestamp"],
                "altitudes": [avant["altitude"], apres["altitude"]],
                "vitesses": [avant["groundspeed"], apres["groundspeed"]],
            }
        elif a_plat:
            # 2. Mon palier continue
            # On repousse la fin et on ajoute le nouveau point aux listes (.append).
            palier_en_cours["end"] = apres["timestamp"]
            palier_en_cours["altitudes"].append(apres["altitude"])
            palier_en_cours["vitesses"].append(apres["groundspeed"])
        elif palier_en_cours is not None:
            # 3. Fin du palier : on le range et on repart de zéro
            paliers.append(palier_en_cours)
            palier_en_cours = None
        # (Tronçon pas plat et pas de palier en cours : rien à faire, on continue.)

    # 4. La trajectoire s'est terminée en plein palier : on le range quand même
    # (aucun tronçon pas plat n'est venu déclencher le cas 3).
    if palier_en_cours is not None:
        paliers.append(palier_en_cours)

    # ÉTAPES 6 et 7 : mesurer chaque palier, garder ceux d'au moins 20 s
    lignes = []
    for p in paliers:
        # Durée en secondes.
        duree = (p["end"] - p["start"]).total_seconds()
        if duree >= C.LEVEL_MIN_DURATION_S:
            lignes.append({
                "start": p["start"],
                "end": p["end"],
                # Médiane des altitudes, arrondie à la centaine (round(x, -2) :
                # 3 880 → 3 900), à la manière d'un niveau de vol.
                "altitude_ft": round(pd.Series(p["altitudes"]).median(), -2),
                # Vitesse sol médiane (sert à l'estimation carburant).
                "groundspeed_kt": pd.Series(p["vitesses"]).median(),
                "duration_s": duree,
            })
    # Une ligne par palier ; columns=COLONNES garantit les colonnes même si vide.
    return pd.DataFrame(lignes, columns=COLONNES)


# --------------------------------------------------------------------------- #
# Configuration de piste (04 = vers le nord-est, 22 = vers le sud-ouest)
# déduite du cap suivi par l'avion
# --------------------------------------------------------------------------- #
# Dictionnaire : nom de piste → cap approximatif en degrés.
RUNWAY_HEADINGS = {"04": 44.0, "22": 224.0}   # LFMN runways 04L/R - 22L/R


# Paramètres avec valeurs par défaut : altitude max des points regardés,
# nombre de points, écart de cap toléré. Renvoie "04", "22" ou None.
def runway_config(df: pd.DataFrame, direction: str, max_alt_ft: float = 3_000,
                  n_points: int = 6, tolerance_deg: float = 35) -> str | None:
    """'04' or '22' from the mean track of the lowest airborne points: the last ones
    of an arrival or the first ones of a departure. Robust to 25-s sampling, unlike
    ILS-alignment methods that need dense data. L/R parallels are not separated."""
    d = _prepare(df)
    # Points en vol (~ = « non »), sous 3 000 ft (.le = ≤), avec un cap connu.
    air = d[~d["onground"] & d["altitude"].le(max_alt_ft) & d["track"].notna()]
    # Arrivée : les 6 DERNIERS points bas (.tail) ; départ : les 6 PREMIERS (.head).
    pts = air.tail(n_points) if direction == "arr" else air.head(n_points)
    # Moins de 2 points : pas assez pour conclure.
    if len(pts) < 2:
        return None
    # Moyenne de caps : la moyenne de 350° et 10° n'est pas 180° mais 0° !
    # On passe chaque cap en vecteur (sinus, cosinus), on fait la moyenne des
    # vecteurs, puis on reconvertit en angle (arctan2), ramené entre 0 et 360.
    rad = np.radians(pts["track"].astype(float))
    mean = np.degrees(np.arctan2(np.sin(rad).mean(), np.cos(rad).mean())) % 360
    # Compare au cap de chaque piste.
    for name, hdg in RUNWAY_HEADINGS.items():
        # Écart d'angle le plus court, entre -180 et +180 ; si ≤ 35°, c'est cette piste.
        if abs((mean - hdg + 180) % 360 - 180) <= tolerance_deg:
            return name
    # Aucun cap ne correspond (ex. virage en cours) : on ne devine pas.
    return None
