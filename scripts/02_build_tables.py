"""Turn the flights in data/raw/ into 2 analytical tables (Parquet), ready for BigQuery.

    flights.parquet     one row per flight (arrival or departure)
    level_offs.parquet  one row per level segment during descent (arrivals)

Usage:
    python scripts/02_build_tables.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eco_nice.features import detect_level_offs, runway_config  # noqa: E402
from eco_nice.fuel import co2_kg, is_proxy, level_off_excess_fuel_kg  # noqa: E402

RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"


def typecode_lookup() -> dict:
    """icao24 -> ICAO type code, from the aircraft database shipped with `traffic`."""
    try:
        from traffic.data import aircraft
        db = aircraft.data[["icao24", "typecode"]].dropna()
        return dict(zip(db["icao24"].str.lower(), db["typecode"].str.upper()))
    except Exception as e:  # database unavailable: fuel columns will be empty
        print(f"warning: aircraft database unavailable ({e})")
        return {}


def main() -> None:
    types = typecode_lookup()
    flights, levels = [], []

    for path in sorted(RAW.glob("*.parquet")):
        direction = path.name[:3]                     # "arr" or "dep"
        positions = pd.read_parquet(path)

        for fid, df in positions.groupby("flight_id"):
            icao24 = df["icao24"].iloc[0]
            typecode = types.get(icao24)

            flights.append({
                "flight_id": fid,
                "icao24": icao24,
                "callsign": df["callsign"].iloc[0],
                "typecode": typecode,
                "fuel_type_proxy": is_proxy(typecode),
                "direction": direction,
                "first_seen": df["timestamp"].min(),
                "last_seen": df["timestamp"].max(),
                "runway": runway_config(df, direction),
            })

            if direction != "arr":
                continue
            for _, lv in detect_level_offs(df).iterrows():
                fuel = level_off_excess_fuel_kg(
                    typecode, lv["duration_s"], lv["altitude_ft"], lv["groundspeed_kt"])
                levels.append({
                    "flight_id": fid,
                    **lv.to_dict(),
                    "excess_fuel_kg": fuel,
                    "excess_co2_kg": co2_kg(fuel),
                })

    OUT.mkdir(parents=True, exist_ok=True)
    # Timestamps in microseconds: BigQuery reads nanosecond Parquet timestamps as INT64.
    parquet = dict(index=False, coerce_timestamps="us", allow_truncated_timestamps=True)
    pd.DataFrame(flights).to_parquet(OUT / "flights.parquet", **parquet)
    pd.DataFrame(levels).to_parquet(OUT / "level_offs.parquet", **parquet)
    print(f"flights: {len(flights)} rows | level_offs: {len(levels)} rows")


if __name__ == "__main__":
    main()
