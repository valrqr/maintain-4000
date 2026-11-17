# =============================================================================
# fuel.py : ESTIMER LE CARBURANT (ET LE CO2) AVEC LE MODÈLE OpenAP
# -----------------------------------------------------------------------------
# OpenAP (université TU Delft) est un modèle de performance avion : pour un type
# d'avion, une masse, une vitesse, une altitude et une vitesse verticale, il
# donne une consommation de carburant (kg/s). Ce sont des ESTIMATIONS de
# modèle, pas des mesures réelles (on n'a pas les données de l'enregistreur).
# Analogie : c'est comme estimer la consommation d'une voiture à partir de sa
# fiche technique et de sa vitesse, sans brancher de capteur.
# =============================================================================

# Docstring : rappelle que ce sont des estimations.
"""Fuel estimates with OpenAP (TU Delft). These are MODEL ESTIMATES, not measured fuel."""
# Annotations de type modernes (`str | None`).
from __future__ import annotations

# lru_cache : « mémoire » automatique d'une fonction (voir _aircraft plus bas).
from functools import lru_cache

# numpy, pour np.nan (valeur manquante) et np.isnan (test de valeur manquante).
import numpy as np
# FuelFlow : calculateur de consommation ; prop : fiches techniques avions/moteurs.
from openap import FuelFlow, prop

# Nos paramètres (masse supposée, facteur CO2, rendements…).
from . import config as C

# Ensemble (set) de tous les codes avion que OpenAP sait modéliser
# (ex. "a320", "b738"). use_synonym=True inclut les variantes de noms.
# Un set permet de tester très vite « est-ce que X est dedans ? ».
SUPPORTED = set(prop.available_aircraft(use_synonym=True))

# Types vus à Nice que OpenAP ne modélise pas → type modélisé le plus proche.
# C'est une approximation assumée (même famille ou taille/moteurs proches),
# signalée dans les résultats par la colonne fuel_type_proxy.
# Dictionnaire : "type réel" : "type utilisé à la place".
PROXIES = {
    "crjx": "crj9", "crj7": "crj9",          # CRJ1000 / CRJ700 -> CRJ900
    "bcs1": "e195", "bcs3": "e195",          # Airbus A220 -> Embraer E195 (taille proche)
    "e75s": "e75l",                          # variante d'Embraer 175
    "ga5c": "glf6", "ga6c": "glf6",          # Gulfstream G500/G600 -> G650
}


# Traduit un code type OACI (ex. "A320") en code OpenAP utilisable, ou None.
def openap_type(typecode: str | None) -> str | None:
    # Si ce n'est pas un texte (ex. valeur manquante), on ne peut rien faire.
    # isinstance(x, str) = « x est-il une chaîne de caractères ? »
    if not isinstance(typecode, str):
        return None
    # Nettoyage : enlève les espaces (strip) et met en minuscules (lower).
    t = typecode.strip().lower()
    # .get(t, t) : si t est dans PROXIES, prend le remplaçant ; sinon garde t.
    t = PROXIES.get(t, t)
    # Renvoie t seulement si OpenAP le connaît, sinon None.
    return t if t in SUPPORTED else None


# True si l'estimation de ce type passe par un type de remplacement (proxy).
def is_proxy(typecode: str | None) -> bool:
    # `and` : si le 1er test est faux, Python ne regarde même pas le 2e.
    return isinstance(typecode, str) and typecode.strip().lower() in PROXIES


# @lru_cache : décorateur qui mémorise le résultat pour chaque type d'avion.
# Le 2e appel avec "a320" renvoie le résultat déjà calculé au lieu de relire
# les fiches techniques : beaucoup plus rapide sur des milliers de vols.
# maxsize=None : pas de limite au nombre de résultats mémorisés.
@lru_cache(maxsize=None)
def _aircraft(ac: str):
    # Renvoie 2 objets à la fois (un « tuple ») : la fiche technique de l'avion
    # (masses, moteurs… sous forme de dictionnaire) et son calculateur de conso.
    return prop.aircraft(ac), FuelFlow(ac)


# Surconsommation d'un palier : carburant brûlé à plat MOINS celui qu'aurait
# brûlé l'avion en continuant sa descente moteurs au ralenti, au même endroit.
def level_off_excess_fuel_kg(typecode, duration_s, altitude_ft, groundspeed_kt) -> float:
    """Extra fuel burnt flying level vs. continuing an idle descent at the same point.

    Ground speed is used as a TAS proxy (wind ignored) and landing mass is assumed.
    """
    # Code OpenAP du type d'avion (ou None si inconnu).
    ac = openap_type(typecode)
    # Type inconnu ou durée nulle/absente → pas d'estimation (NaN).
    # `not duration_s` est vrai si la durée vaut 0 ou None.
    if ac is None or not duration_s:
        return np.nan
    # try/except : si OpenAP plante sur un cas particulier, on renvoie NaN
    # au lieu d'arrêter tout le traitement.
    try:
        # On récupère la fiche avion (a) et le calculateur (ff).
        a, ff = _aircraft(ac)
        # Masse supposée = 90 % de la masse maximale à l'atterrissage (mlw).
        mass = C.LANDING_MASS_RATIO * a["mlw"]
        # Débit carburant (kg/s) en vol à plat (vitesse verticale vs=0).
        # La vitesse sol remplace la vitesse air (tas) : le vent est ignoré.
        level = ff.enroute(mass=mass, tas=groundspeed_kt, alt=altitude_ft, vs=0)
        # Débit carburant en descente continue de référence (-1 500 ft/min).
        idle = ff.enroute(mass=mass, tas=groundspeed_kt, alt=altitude_ft,
                          vs=C.IDLE_DESCENT_VS_FPM)
        # Surplus par seconde × durée = kg de carburant en trop.
        # max(…, 0) : jamais négatif. float() : nombre Python classique.
        return float(max(level - idle, 0) * duration_s)
    # `except Exception` attrape n'importe quelle erreur.
    except Exception:
        return np.nan


# Conversion carburant → CO2 : kg de kérosène × 3,16.
def co2_kg(fuel_kg: float) -> float:
    return fuel_kg * C.CO2_PER_KG_FUEL
