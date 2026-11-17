"""Load the processed Parquet tables into BigQuery (dataset `raw_eco_nice`).

Usage:
    python scripts/03_load_bigquery.py --project YOUR_GCP_PROJECT
"""
from __future__ import annotations

import argparse
from pathlib import Path

from google.cloud import bigquery

PROCESSED = Path(__file__).resolve().parents[1] / "data" / "processed"
DATASET = "raw_eco_nice"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--project", required=True)
    p.add_argument("--location", default="EU")
    a = p.parse_args()

    client = bigquery.Client(project=a.project)
    dataset = bigquery.Dataset(f"{a.project}.{DATASET}")
    dataset.location = a.location            # without this, BigQuery creates it in the US
    dataset = client.create_dataset(dataset, exists_ok=True)
    if dataset.location != a.location:
        raise SystemExit(f"Dataset {DATASET} already exists in {dataset.location}, not {a.location}: "
                         f"delete it (bq rm -r -f {a.project}:{DATASET}) and run again.")
    cfg = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.PARQUET,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    for name in ("flights", "level_offs"):
        with open(PROCESSED / f"{name}.parquet", "rb") as fh:
            job = client.load_table_from_file(
                fh, f"{a.project}.{DATASET}.{name}", job_config=cfg, location=a.location
            )
        job.result()
        print(f"loaded {name}: {client.get_table(job.destination).num_rows} rows")


if __name__ == "__main__":
    main()
