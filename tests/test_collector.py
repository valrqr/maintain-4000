"""Offline test of the OpenSky live collector parsing (no credentials, no network)."""
import gzip
import importlib.util
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("collector", ROOT / "scripts" / "opensky_live_collector.py")
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)

PAYLOAD = {"time": 1763142000, "states": [
    # icao24, callsign, country, t_pos, last_contact, lon, lat, baro_m, onground,
    # velocity m/s, track, vrate m/s, sensors, geo_m, squawk, spi, source
    ["3944ef", "AFR7700 ", "France", 1763141995, 1763141999, 7.30, 43.55, 2133.6, False,
     128.6, 45.2, -5.08, None, 2200.0, "1000", False, 0],
    ["4ca123", "EZY45   ", "Ireland", 1763141990, 1763141999, 7.21, 43.66, None, True,
     6.2, 220.0, None, None, None, None, False, 0],
    ["abcdef", None, "France", None, 1763141999, None, None, None, False,
     None, None, None, None, None, None, False, 0],
]}


def test_units_and_dedup(tmp_path):
    seen = {}
    rows = collector.parse_states(PAYLOAD, seen)
    assert len(rows) == 2                               # no-position aircraft skipped
    afr = rows[0]
    assert afr[5] == 7000                               # 2133.6 m -> 7000 ft
    assert afr[6] == 250.0                              # 128.6 m/s -> 250 kt
    assert afr[7] == -1000                              # -5.08 m/s -> -1000 ft/min
    assert rows[1][5] == 0 and rows[1][9] is True       # on ground
    assert collector.parse_states(PAYLOAD, seen) == []  # same positions: not rewritten

    collector.append(tmp_path, rows)
    f = next(tmp_path.rglob("*.csv.gz"))
    df = pd.read_csv(f, parse_dates=["timestamp"])
    assert list(df.columns) == collector.COLUMNS
    assert df["onground"].dtype == bool
