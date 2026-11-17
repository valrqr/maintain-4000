"""Synthetic trajectories with known answers: no network, no OpenSky account needed."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from eco_nice.features import detect_level_offs  # noqa: E402
from eco_nice.fuel import level_off_excess_fuel_kg  # noqa: E402

T0 = pd.Timestamp("2026-10-01 08:00", tz="UTC")


def _traj(segments):
    """segments: list of (duration_s, alt_start, alt_end, gs, onground)."""
    rows, t = [], 0
    for dur, a0, a1, gs, og in segments:
        for i in range(dur):
            alt = a0 + (a1 - a0) * i / dur
            rows.append((T0 + pd.to_timedelta(t, unit="s"), alt, gs, og))
            t += 1
    df = pd.DataFrame(rows, columns=["timestamp", "altitude", "groundspeed", "onground"])
    df["vertical_rate"] = np.nan  # force recomputation from altitude
    return df


ARRIVAL = _traj([
    (600, 36000, 36000, 450, False),   # cruise
    (600, 36000, 7000, 320, False),    # descent  (~ -2900 ft/min)
    (120, 7000, 7000, 250, False),     # LEVEL-OFF at 7000 ft, 2 min
    (300, 7000, 0, 150, False),        # final descent
    (40, 0, 0, 120, True),             # landing roll
])


def test_level_off_detected():
    lv = detect_level_offs(ARRIVAL)
    assert len(lv) == 1
    assert lv.loc[0, "altitude_ft"] == 7000
    assert lv.loc[0, "duration_s"] == pytest.approx(120, abs=10)


def test_no_level_off_on_continuous_descent():
    cdo = _traj([(600, 36000, 36000, 450, False), (1200, 36000, 0, 300, False),
                 (60, 0, 0, 20, True)])
    assert detect_level_offs(cdo).empty


def test_fuel_estimates_are_plausible():
    excess = level_off_excess_fuel_kg("A320", 120, 7000, 250)
    assert 20 < excess < 100            # a 2-min level-off costs tens of kg
    assert np.isnan(level_off_excess_fuel_kg("XXXX", 120, 7000, 250))   # unknown type -> null
