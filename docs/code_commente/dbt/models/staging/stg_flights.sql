-- =============================================================================
-- stg_flights.sql : COUCHE « STAGING » — NETTOYER LA TABLE DES VOLS
-- -----------------------------------------------------------------------------
-- Rôle du staging dans dbt : prendre une table brute (source) et la rendre
-- propre et homogène (noms, formats, doublons), SANS calcul métier.
-- Analogie : le « lavage des légumes » avant de cuisiner.
-- Matérialisé en VUE (voir dbt_project.yml) : pas de copie des données, juste
-- une requête enregistrée, recalculée à chaque lecture.
-- Dialecte : SQL BigQuery. Les commentaires commencent par `--`.
-- =============================================================================

select
    -- identifiant unique du vol, gardé tel quel
    flight_id,
    -- identifiant ADS-B de l'avion, forcé en minuscules (lower) pour être homogène
    lower(icao24)                                         as icao24,
    -- indicatif sans espaces au début ni à la fin (trim) ; `as` = renommer la colonne
    trim(callsign)                                        as callsign,
    -- 3 premiers caractères de l'indicatif (left(…, 3)) = code OACI de la
    -- compagnie (ex. AFR = Air France, EZY = easyJet, TVF = Transavia France)
    left(trim(callsign), 3)                               as airline_icao,  -- ICAO callsign prefix
    -- type d'avion en majuscules (A320, B738…)
    upper(typecode)                                       as typecode,
    -- True si le carburant de ce vol est estimé avec un type de remplacement
    fuel_type_proxy,
    -- CASE … WHEN … THEN … ELSE … END = « si … alors … sinon » en SQL :
    -- 'arr' devient 'arrival', tout le reste 'departure' (libellés plus lisibles)
    case direction when 'arr' then 'arrival' else 'departure' end as direction,
    -- configuration de piste ('04' ou '22'), éventuellement vide (NULL)
    runway,
    -- premier et dernier instant observé du vol (en UTC)
    first_seen,
    last_seen,
    -- date LOCALE du vol (heure de Paris) à partir du dernier instant :
    -- un vol à 23h30 UTC en hiver est déjà le lendemain à Nice
    date(last_seen, 'Europe/Paris')                       as flight_date_local,
    -- heure locale (0 à 23) : datetime(…, fuseau) convertit en heure de Paris,
    -- extract(hour from …) n'en garde que l'heure ; utile pour analyser par créneau
    extract(hour from datetime(last_seen, 'Europe/Paris')) as hour_local
-- {{ source(...) }} est une syntaxe dbt (Jinja) : dbt la remplace par le vrai
-- nom de la table brute déclarée dans _sources.yml (projet.raw_eco_nice.flights).
-- Avantage : dbt connaît ainsi la dépendance et dessine le graphe du pipeline.
from {{ source('raw_eco_nice', 'flights') }}
-- Dédoublonnage : row_number() numérote les lignes 1, 2, 3… À L'INTÉRIEUR de
-- chaque flight_id (partition by), de la plus récente à la plus ancienne
-- (order by last_seen desc). QUALIFY filtre APRÈS ce calcul (comme un WHERE
-- pour les fonctions de fenêtre) : on garde seulement la ligne n°1 de chaque vol.
qualify row_number() over (partition by flight_id order by last_seen desc) = 1
