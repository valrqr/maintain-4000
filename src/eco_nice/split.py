"""Turn a continuous stream of positions (all aircraft around Nice) into flights,
then keep only arrivals at and departures from LFMN.

Pure pandas: works on files from opensky_live_collector.py and adsb_logger.py.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

LFMN_LAT, LFMN_LON = 43.6584, 7.2159
NEAR_AIRPORT_KM = 8          # first/last point must be this close to LFMN...
LOW_ALT_FT = 2_500           # ...and this low
MIN_CLIMB_FT = 3_000         # the flight must climb/descend at least this much
MIN_MAX_ALT_FT = 5_000       # drops helicopters (Nice <-> Monaco shuttles fly low)
MAX_GAP_MIN = 20             # a longer silence starts a new flight
MIN_GROUND_STOP_MIN = 5      # shorter 'on ground' runs between airborne points = glitches
MIN_POINTS = 10


def haversine_km(lat, lon, lat0=LFMN_LAT, lon0=LFMN_LON):
    lat, lon = np.radians(lat), np.radians(lon)
    lat0, lon0 = np.radians(lat0), np.radians(lon0)
    a = (np.sin((lat - lat0) / 2) ** 2
         + np.cos(lat) * np.cos(lat0) * np.sin((lon - lon0) / 2) ** 2)
    return 6371 * 2 * np.arcsin(np.sqrt(a))


def load_positions(files) -> pd.DataFrame:
    df = pd.concat((pd.read_csv(f, dtype={"icao24": str, "callsign": str})
                    for f in files), ignore_index=True)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["callsign"] = df["callsign"].fillna("").str.strip()
    df["onground"] = df["onground"].astype(str).str.lower().eq("true")
    return (df.drop_duplicates(["icao24", "timestamp"])
              .sort_values(["icao24", "timestamp"])
              .reset_index(drop=True))


def _segment_ids(g: pd.DataFrame) -> np.ndarray:
    """Cut one aircraft's track on long gaps and in the middle of each ground stop
    between two airborne parts (arrival ... turnaround ... departure)."""
    t = g["timestamp"]
    new = t.diff().dt.total_seconds().gt(MAX_GAP_MIN * 60).to_numpy()

    og = g["onground"].to_numpy()
    run_start = np.r_[True, og[1:] != og[:-1]]
    run_id = np.cumsum(run_start)
    for rid in np.unique(run_id[og]):
        idx = np.flatnonzero(run_id == rid)
        before, after = idx[0] - 1, idx[-1] + 1
        if before < 0 or after >= len(og):            # track starts/ends on the ground
            continue
        stop_s = (t.iloc[idx[-1]] - t.iloc[idx[0]]).total_seconds()
        if stop_s < MIN_GROUND_STOP_MIN * 60:         # a glitch, not a real stop
            continue
        new[idx[len(idx) // 2]] = True                # air -> ground -> air: turnaround
    return np.cumsum(new)


def classify(f: pd.DataFrame) -> str | None:
    """'arr', 'dep' or None (overflight, helicopter, too short...)."""
    if len(f) < MIN_POINTS or f["altitude"].max() < MIN_MAX_ALT_FT:
        return None
    first, last = f.iloc[0], f.iloc[-1]
    d_first = haversine_km(first["latitude"], first["longitude"])
    d_last = haversine_km(last["latitude"], last["longitude"])
    peak = f["altitude"].max()
    if d_last <= NEAR_AIRPORT_KM and last["altitude"] <= LOW_ALT_FT \
            and peak - last["altitude"] >= MIN_CLIMB_FT:
        return "arr"
    if d_first <= NEAR_AIRPORT_KM and first["altitude"] <= LOW_ALT_FT \
            and peak - first["altitude"] >= MIN_CLIMB_FT:
        return "dep"
    return None


def split_flights(df: pd.DataFrame) -> pd.DataFrame:
    """Add flight_id and direction; return only LFMN arrivals and departures."""
    out = []
    for icao24, g in df.groupby("icao24", sort=False):
        g = g.reset_index(drop=True)
        for _, f in g.groupby(_segment_ids(g)):
            direction = classify(f)
            if direction is None:
                continue
            cs = next((c for c in f["callsign"] if c), "NOCALL")
            fid = f"{icao24}_{cs}_{f['timestamp'].iloc[0]:%Y%m%dT%H%M}"
            out.append(f.assign(flight_id=fid, direction=direction, callsign=cs))
    if not out:
        return df.iloc[0:0].assign(flight_id="", direction="")
    return pd.concat(out, ignore_index=True)
