-- =============================================================================
-- fct_arrivals_efficiency.sql : COUCHE « MARTS » — UNE LIGNE PAR ARRIVÉE
-- -----------------------------------------------------------------------------
-- Rôle des marts dans dbt : les tables finales, prêtes pour l'analyse et
-- Power BI. Ici on combine les vols et leurs paliers pour répondre à :
-- « la descente a-t-elle été continue ? combien de paliers ? quel surcoût ? »
-- `fct_` = table de faits (une ligne = un événement mesuré, ici une arrivée).
-- Matérialisé en TABLE (voir dbt_project.yml) : résultat stocké, lecture rapide.
-- =============================================================================

-- One row per arrival: how "continuous" was the descent, and what did it cost?
-- WITH … AS (…) = CTE (« table temporaire nommée ») : on prépare un résultat
-- intermédiaire, réutilisé plus bas sous le nom `levels`.
with levels as (
    select
        flight_id,
        -- nombre de paliers du vol (count(*) compte les lignes du groupe)
        count(*)                                  as n_level_offs,
        -- temps total passé en palier (secondes)
        sum(duration_s)                           as level_time_s,
        -- temps en palier SOUS le niveau 100 (10 000 ft), là où c'est le plus
        -- coûteux : if(condition, valeur_si_vrai, valeur_si_faux)
        sum(if(altitude_ft < 10000, duration_s, 0)) as level_time_below_fl100_s,
        -- niveau du palier le plus bas
        min(flight_level)                         as lowest_level_fl,
        -- carburant et CO2 en trop, cumulés sur tous les paliers du vol
        sum(excess_fuel_kg)                       as excess_fuel_kg,
        sum(excess_co2_kg)                        as excess_co2_kg
    -- {{ ref(...) }} = syntaxe dbt pour lire un AUTRE modèle dbt (ici le staging).
    -- dbt en déduit l'ordre d'exécution : stg_level_offs avant ce modèle.
    from {{ ref('stg_level_offs') }}
    -- un résultat par vol
    group by flight_id
)

select
    -- `f.` = colonne venant de la table aliasée `f` (stg_flights, voir plus bas)
    f.flight_id,
    f.callsign,
    f.airline_icao,
    f.typecode,
    f.runway,
    f.flight_date_local,
    f.hour_local,
    -- coalesce(a, b) = « a, ou b si a est NULL ». Un vol SANS palier n'a pas de
    -- ligne dans `levels` → la jointure donne NULL → on remplace par 0.
    coalesce(l.n_level_offs, 0)               as n_level_offs,
    coalesce(l.level_time_s, 0)               as level_time_s,
    coalesce(l.level_time_below_fl100_s, 0)   as level_time_below_fl100_s,
    -- on laisse NULL ici : « pas de palier » n'a pas de niveau le plus bas
    l.lowest_level_fl,
    -- colonne booléenne : True si aucun palier = descente continue (CDO)
    coalesce(l.n_level_offs, 0) = 0           as is_continuous_descent,
    -- Carburant et CO2 en trop. if(condition, si_vrai, si_faux) :
    -- vol absent de `levels` (aucun palier) → 0 kg, c'est un vrai zéro ;
    -- vol avec paliers mais type d'avion inconnu → reste NULL (« inconnu »),
    -- pour ne pas faire passer un manque d'information pour une descente gratuite.
    -- no level-off -> 0 kg; level-offs on an unknown aircraft type -> stays NULL (unknown, not zero)
    if(l.flight_id is null, 0, l.excess_fuel_kg) as excess_fuel_kg,
    if(l.flight_id is null, 0, l.excess_co2_kg)  as excess_co2_kg,
    -- True si le type d'avion est connu (condition préalable à une estimation)
    f.typecode is not null                    as has_fuel_estimate
-- table des vols (alias f)…
from {{ ref('stg_flights') }} f
-- …LEFT JOIN : on garde TOUS les vols, même ceux sans palier (sinon les
-- descentes continues disparaîtraient !). `on l.flight_id = f.flight_id` :
-- condition de jointure (même identifiant de vol des deux côtés). Pour un vol
-- sans palier, toutes les colonnes `l.` valent alors NULL.
left join levels l on l.flight_id = f.flight_id
-- seulement les arrivées
where f.direction = 'arrival'
