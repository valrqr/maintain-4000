-- =============================================================================
-- stg_level_offs.sql : STAGING — NETTOYER LA TABLE DES PALIERS
-- -----------------------------------------------------------------------------
-- Une ligne par palier détecté en descente. On renomme les colonnes ambiguës
-- et on ajoute le niveau de vol (flight level).
-- =============================================================================

select
    -- vol auquel appartient le palier (sert à faire la jointure avec stg_flights)
    flight_id,
    -- `start` et `end` sont des mots réservés en SQL BigQuery : on les entoure
    -- d'accents graves (`…`) pour pouvoir les utiliser comme noms de colonnes,
    -- puis on les renomme en noms explicites et sans ambiguïté.
    `start`                         as level_start,
    `end`                           as level_end,
    -- cast(… as int64) = conversion en nombre entier (int64 = entier BigQuery)
    cast(altitude_ft as int64)      as altitude_ft,
    -- niveau de vol = altitude / 100 (3 900 ft → niveau 39)
    cast(altitude_ft / 100 as int64) as flight_level,
    -- durée du palier en secondes
    duration_s,
    -- vitesse sol médiane pendant le palier (nœuds)
    groundspeed_kt,
    -- carburant et CO2 en trop estimés (kg), NULL si type d'avion inconnu
    excess_fuel_kg,
    excess_co2_kg
-- table brute chargée par 03_load_bigquery.py (voir _sources.yml)
from {{ source('raw_eco_nice', 'level_offs') }}
