"""Synthetic 25-second stream around Nice: one aircraft lands then takes off again,
plus an overflight and a helicopter that must be ignored."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from eco_nice.features import detect_level_offs  # noqa: E402
from eco_nice.split import LFMN_LAT, LFMN_LON, split_flights  # noqa: E402

T0 = pd.Timestamp("2026-11-15 08:00", tz="UTC")
STEP = 25


def _track(icao, cs, legs, t_start=0):
    """legs: (n_points, alt0, alt1, lat0, lon0, lat1, lon1, onground, vs_fpm)."""
    rows, t = [], t_start
    for n, a0, a1, la0, lo0, la1, lo1, og, vs in legs:
        for i in range(n):
            f = i / n
            rows.append(dict(timestamp=T0 + pd.to_timedelta(t, unit="s"), icao24=icao, callsign=cs,
                             latitude=la0 + (la1 - la0) * f, longitude=lo0 + (lo1 - lo0) * f,
                             altitude=a0 + (a1 - a0) * f, groundspeed=0 if og else 250,
                             vertical_rate=vs, track=0, onground=og))
            t += STEP
    return rows


def _stream():
    far_lat, far_lon = 44.1, 7.9
    rows = []
    # A: arrival with a 100 s level-off at 6000 ft, 40 min turnaround, departure
    rows += _track("aaa111", "AFR123", [
        (30, 30000, 6000, far_lat, far_lon, 43.75, 7.40, False, -2000),
        (4, 6000, 6000, 43.75, 7.40, 43.72, 7.33, False, 0),          # level-off
        (20, 6000, 0, 43.72, 7.33, LFMN_LAT, LFMN_LON, False, -800),
        (96, 0, 0, LFMN_LAT, LFMN_LON, LFMN_LAT, LFMN_LON, True, 0),  # 40 min on ground
        (40, 0, 20000, LFMN_LAT, LFMN_LON, far_lat, far_lon, False, 1500),
    ])
    # B: overflight at FL350, never near the airport
    rows += _track("bbb222", "DLH9", [(60, 35000, 35000, 43.1, 6.5, 44.1, 7.9, False, 0)])
    # C: helicopter shuttle to Monaco, low altitude
    rows += _track("ccc333", "MCM1", [(30, 0, 1000, LFMN_LAT, LFMN_LON, 43.73, 7.42, False, 300)])
    return pd.DataFrame(rows)


def test_split_keeps_one_arrival_and_one_departure():
    flights = split_flights(_stream())
    per_dir = flights.groupby("direction")["flight_id"].nunique().to_dict()
    assert per_dir == {"arr": 1, "dep": 1}
    assert set(flights["icao24"]) == {"aaa111"}


def test_level_off_found_with_25s_sampling():
    flights = split_flights(_stream())
    arr = flights[flights["direction"] == "arr"]
    lv = detect_level_offs(arr)
    assert len(lv) == 1
    assert lv.loc[0, "altitude_ft"] == 6000
    assert 50 <= lv.loc[0, "duration_s"] <= 100


def test_runway_config_from_track():
    from eco_nice.features import runway_config
    flights = split_flights(_stream())
    arr = flights[flights["direction"] == "arr"].copy()
    arr["track"] = 45.0                       # landing towards the north-east
    assert runway_config(arr, "arr") == "04"
    arr["track"] = 226.0
    assert runway_config(arr, "arr") == "22"
    arr["track"] = 130.0                      # neither runway: no guess
    assert runway_config(arr, "arr") is None


def test_fuel_proxies():
    from eco_nice.fuel import is_proxy, openap_type
    assert openap_type("CRJX") == "crj9" and is_proxy("CRJX")
    assert openap_type("A320") == "a320" and not is_proxy("A320")
    assert openap_type("ZZZZ") is None


def test_sparse_level_off_matches_the_eye():
    """Real case TVF72YJ (14/11): 4 nearly flat points around 3,900 ft, 25 s apart.
    The plateau lasts ~75 s, not the 25 s the reported vertical rate suggested."""
    alts = [4740, 4200, 3960, 3870, 3890, 3820, 3420, 3090, 2720]
    vs_reported = [-1300, -900, -400, -350, 100, -320, -1000, -800, -900]
    df = pd.DataFrame({
        "timestamp": [T0 + pd.to_timedelta(25 * i, unit="s") for i in range(len(alts))],
        "altitude": alts, "vertical_rate": vs_reported,
        "groundspeed": 180.0, "onground": False,
    })
    lv = detect_level_offs(df)
    assert len(lv) == 1
    assert lv.loc[0, "duration_s"] == 75
    assert lv.loc[0, "altitude_ft"] == 3900


def test_data_gap_is_never_counted_as_level_flight():
    """Regression: a 2-min gap before a flat point used to be counted as level time."""
    alts = [9000, 8000, 7000, 7000, 7000, 7000, 6000]
    df = pd.DataFrame({
        "timestamp": [T0 + pd.to_timedelta(25 * i, unit="s") for i in range(len(alts))],
        "altitude": [float(a) for a in alts], "vertical_rate": 0.0,
        "groundspeed": 200.0, "onground": False,
    })
    df["timestamp"] = df["timestamp"] + pd.to_timedelta([0] * 4 + [120] * 3, unit="s")
    assert list(detect_level_offs(df)["duration_s"]) == [25, 25]


def test_cruise_at_max_altitude_is_not_a_level_off():
    """Regression: short flights (Corsica, Geneva) cruise low; their cruise was counted as a level-off."""
    alts = [14000] * 10 + [13000, 12000, 11000, 10000, 9000, 8000]
    df = pd.DataFrame({
        "timestamp": [T0 + pd.to_timedelta(25 * i, unit="s") for i in range(len(alts))],
        "altitude": [float(a) for a in alts], "groundspeed": 250.0, "onground": False,
    })
    assert detect_level_offs(df).empty
