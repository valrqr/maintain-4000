"""Collected positions (opensky_live or receiver CSV.gz) -> one Parquet per day and
direction in data/raw/, the format 02_build_tables.py reads.

Also prints a data-quality check: hours covered, gaps, flights found.

Usage:
    python3 scripts/00_split_flights.py --src data/opensky_live
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eco_nice.split import load_positions, split_flights  # noqa: E402

RAW = ROOT / "data" / "raw"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--src", default="data/opensky_live")
    a = p.parse_args()

    files = sorted(Path(a.src).rglob("*.csv.gz"))
    if not files:
        raise SystemExit(f"No .csv.gz under {a.src}")
    df = load_positions(files)

    # --- data quality --------------------------------------------------------
    hours = df["timestamp"].dt.floor("h")
    expected = pd.date_range(hours.min(), hours.max(), freq="h")
    missing = expected.difference(hours.unique())
    print(f"Files: {len(files)} | positions: {len(df):,} | aircraft: {df['icao24'].nunique()}")
    print(f"From {df['timestamp'].min():%Y-%m-%d %H:%M} to {df['timestamp'].max():%Y-%m-%d %H:%M} UTC")
    print(f"Hours without any data: {len(missing)}"
          + (f" (e.g. {', '.join(f'{h:%d/%m %Hh}' for h in missing[:5])})" if len(missing) else ""))

    # --- split & save ----------------------------------------------------------
    flights = split_flights(df)
    if flights.empty:
        raise SystemExit("No arrival/departure at LFMN found: check the data.")
    n = flights.groupby("direction")["flight_id"].nunique()
    print(f"Arrivals: {n.get('arr', 0)} | departures: {n.get('dep', 0)}")

    RAW.mkdir(parents=True, exist_ok=True)
    flights["day"] = flights.groupby("flight_id")["timestamp"].transform("max").dt.strftime("%Y-%m-%d")
    for (direction, day), part in flights.groupby(["direction", "day"]):
        out = RAW / f"{direction}_{day}.parquet"
        part.drop(columns=["day", "direction"]).to_parquet(out, index=False)
        print(f"  saved {out.relative_to(ROOT)}: {part['flight_id'].nunique()} flights")


if __name__ == "__main__":
    main()
