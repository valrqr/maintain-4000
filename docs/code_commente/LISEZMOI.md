# Code commenté ligne par ligne (en français)

Ce dossier contient une **copie annotée** de chaque script Python et de chaque modèle SQL du projet. Chaque ligne ou expression y est expliquée en français.

- Ces copies servent **à lire et à apprendre**. Pour exécuter le pipeline, utilise toujours les fichiers d'origine (`src/`, `scripts/`, `dbt/models/`).
- Le code des copies est **strictement identique** à celui des originaux : seuls les commentaires changent.
- Les docstrings (textes entre `"""…"""`) sont restées en anglais : elles font partie du code.

## Ordre de lecture conseillé

Suis le trajet de la donnée, de l'antenne au dashboard :

| # | Fichier | Ce qu'il fait |
|---|---|---|
| 1 | `src/eco_nice/config.py` | Tous les réglages et hypothèses du projet |
| 2 | `scripts/opensky_live_collector.py` | Collecte des positions via l'API OpenSky |
| 3 | `src/eco_nice/split.py` | Découpage du flux de positions en vols |
| 4 | `scripts/00_split_flights.py` | Lancement du découpage + contrôle qualité |
| 5 | `src/eco_nice/features.py` | Détection des paliers et de la configuration de piste |
| 6 | `src/eco_nice/fuel.py` | Estimation du carburant et du CO₂ (modèle OpenAP) |
| 7 | `scripts/02_build_tables.py` | Assemblage des 2 tables d'analyse |
| 8 | `scripts/03_load_bigquery.py` | Chargement dans BigQuery |
| 8 bis | `scripts/04_figures.py` | Les graphiques et la carte du README |
| 8 ter | `scripts/05_dispersion.py` | Dispersion des arrivées selon la distance à Nice |
| 9 | `dbt/models/staging/*.sql` | Nettoyage des tables brutes (vues) |
| 10 | `dbt/models/marts/fct_arrivals_efficiency.sql` | Table finale pour l'analyse et Power BI |

## Après une modification du code

Si tu modifies un script d'origine, la copie annotée ne suit pas automatiquement. Pour repérer les copies devenues différentes, lance depuis la racine du repo :

```bash
python docs/code_commente/verifier_copies.py
```

Chaque fichier affiche `OK` (code identique) ou `DIFF` (copie à mettre à jour).
