# =============================================================================
# 03_load_bigquery.py : ÉTAPE 3 — CHARGER LES 2 TABLES DANS BIGQUERY
# -----------------------------------------------------------------------------
# Envoie flights et level_offs dans le dataset BigQuery `raw_eco_nice`.
# Ensuite, dbt prend le relais (modèles SQL dans dbt/models/).
# Prérequis : être connecté à Google Cloud sur ta machine
# (gcloud auth application-default login).
# ⚠️ Copie annotée pour la lecture : exécute la version du dossier scripts/.
# =============================================================================

# Docstring : rôle et commande d'usage.
"""Load the processed Parquet tables into BigQuery (dataset `raw_eco_nice`).

Usage:
    python scripts/03_load_bigquery.py --project YOUR_GCP_PROJECT
"""
from __future__ import annotations

import argparse
from pathlib import Path

# Client officiel Google pour BigQuery.
from google.cloud import bigquery

# Dossier des tables produites par l'étape 2.
PROCESSED = Path(__file__).resolve().parents[1] / "data" / "processed"
# Nom du dataset BigQuery (≈ un « schéma » : un dossier de tables).
DATASET = "raw_eco_nice"


def main() -> None:
    p = argparse.ArgumentParser()
    # --project obligatoire : l'identifiant de ton projet Google Cloud.
    p.add_argument("--project", required=True)
    # --location : région de stockage, "EU" par défaut (données en Europe).
    p.add_argument("--location", default="EU")
    a = p.parse_args()

    # Connexion à BigQuery pour ce projet.
    client = bigquery.Client(project=a.project)
    # Prépare la description du dataset (projet.nom)…
    dataset = bigquery.Dataset(f"{a.project}.{DATASET}")
    # …et sa région. Sans cette ligne, BigQuery le crée aux États-Unis, et le
    # chargement demandé en Europe échoue avec une erreur peu claire (« Error: 3848323 »).
    dataset.location = a.location            # without this, BigQuery creates it in the US
    # Crée le dataset s'il n'existe pas (exists_ok=True : pas d'erreur sinon) ;
    # la fonction renvoie le dataset tel qu'il existe réellement dans BigQuery.
    dataset = client.create_dataset(dataset, exists_ok=True)
    # S'il existait déjà dans une autre région, on s'arrête avec la marche à suivre :
    # la région d'un dataset ne peut pas être changée, il faut le supprimer et le recréer.
    if dataset.location != a.location:
        raise SystemExit(f"Dataset {DATASET} already exists in {dataset.location}, not {a.location}: "
                         f"delete it (bq rm -r -f {a.project}:{DATASET}) and run again.")
    # Réglages du chargement :
    cfg = bigquery.LoadJobConfig(
        # le fichier envoyé est au format Parquet,
        source_format=bigquery.SourceFormat.PARQUET,
        # WRITE_TRUNCATE = on REMPLACE le contenu de la table à chaque chargement
        # (le script peut donc être relancé sans créer de doublons).
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    # Pour chacune des 2 tables…
    for name in ("flights", "level_offs"):
        # …ouvre le fichier en lecture binaire ("rb") ; `with` le referme
        # automatiquement à la fin du bloc…
        with open(PROCESSED / f"{name}.parquet", "rb") as fh:
            # …et lance le « job » de chargement vers projet.dataset.table.
            job = client.load_table_from_file(
                fh, f"{a.project}.{DATASET}.{name}", job_config=cfg, location=a.location
            )
        # .result() attend la fin du chargement (et lève une erreur s'il échoue).
        job.result()
        # Vérification : nombre de lignes effectivement présentes dans BigQuery.
        print(f"loaded {name}: {client.get_table(job.destination).num_rows} rows")


if __name__ == "__main__":
    main()
