"""Fuel estimates with OpenAP (TU Delft). These are MODEL ESTIMATES, not measured fuel."""
from __future__ import annotations

from functools import lru_cache

import numpy as np
from openap import FuelFlow, prop

from . import config as C

SUPPORTED = set(prop.available_aircraft(use_synonym=True))

# Types seen at Nice that OpenAP does not model -> closest modelled type (documented
# approximation: same family or similar size/engines). Extend as new types show up.
PROXIES = {
    "crjx": "crj9", "crj7": "crj9",          # CRJ1000 / CRJ700 -> CRJ900
    "bcs1": "e195", "bcs3": "e195",          # Airbus A220 -> Embraer E195 (similar size)
    "e75s": "e75l",
    "ga5c": "glf6", "ga6c": "glf6",          # Gulfstream G500/G600 -> G650
}


def openap_type(typecode: str | None) -> str | None:
    if not isinstance(typecode, str):
        return None
    t = typecode.strip().lower()
    t = PROXIES.get(t, t)
    return t if t in SUPPORTED else None


def is_proxy(typecode: str | None) -> bool:
    return isinstance(typecode, str) and typecode.strip().lower() in PROXIES


@lru_cache(maxsize=None)
def _aircraft(ac: str):
    return prop.aircraft(ac), FuelFlow(ac)


def level_off_excess_fuel_kg(typecode, duration_s, altitude_ft, groundspeed_kt) -> float:
    """Extra fuel burnt flying level vs. continuing an idle descent at the same point.

    Ground speed is used as a TAS proxy (wind ignored) and landing mass is assumed.
    """
    ac = openap_type(typecode)
    if ac is None or not duration_s:
        return np.nan
    try:
        a, ff = _aircraft(ac)
        mass = C.LANDING_MASS_RATIO * a["mlw"]
        level = ff.enroute(mass=mass, tas=groundspeed_kt, alt=altitude_ft, vs=0)
        idle = ff.enroute(mass=mass, tas=groundspeed_kt, alt=altitude_ft,
                          vs=C.IDLE_DESCENT_VS_FPM)
        return float(max(level - idle, 0) * duration_s)
    except Exception:
        return np.nan


def co2_kg(fuel_kg: float) -> float:
    return fuel_kg * C.CO2_PER_KG_FUEL
