"""Lateral dispersion of LFMN arrivals by distance from the airport.

For each ring (10, 20, 40, 60 km), takes the point where each arrival enters
the ring and measures how spread out the entry bearings are.

Usage:
    python scripts/05_dispersion.py
"""
import glob
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from eco_nice.split import haversine_km  # noqa: E402

LAT0, LON0 = 43.6584, 7.2159


def gisement(lat, lon):
    dlon = np.radians(lon - LON0)
    lat_r, lat0_r = np.radians(lat), np.radians(LAT0)
    y = np.sin(dlon) * np.cos(lat_r)
    x = np.cos(lat0_r) * np.sin(lat_r) - np.sin(lat0_r) * np.cos(lat_r) * np.cos(dlon)
    return np.degrees(np.arctan2(y, x)) % 360


arr = pd.concat(pd.read_parquet(f) for f in glob.glob(str(ROOT / "data/raw/arr_*.parquet")))
arr["dist_km"] = haversine_km(arr["latitude"], arr["longitude"])

lignes = []
for rayon in [10, 20, 40, 60]:
    dehors = arr[arr["dist_km"] >= rayon].sort_values("timestamp")
    passage = dehors.groupby("flight_id").tail(1)
    g = np.radians(gisement(passage["latitude"], passage["longitude"]))
    R = np.hypot(np.sin(g).mean(), np.cos(g).mean())
    lignes.append({
        "rayon_km": rayon,
        "vols": len(passage),
        "dispersion_deg": round(np.degrees(np.sqrt(-2 * np.log(R))), 1),
        "secteurs_30deg": int((np.degrees(g) // 30).nunique()),
    })

print(pd.DataFrame(lignes).to_string(index=False))
