-- One row per arrival: how "continuous" was the descent, and what did it cost?
with levels as (
    select
        flight_id,
        count(*)                                  as n_level_offs,
        sum(duration_s)                           as level_time_s,
        sum(if(altitude_ft < 10000, duration_s, 0)) as level_time_below_fl100_s,
        min(flight_level)                         as lowest_level_fl,
        sum(excess_fuel_kg)                       as excess_fuel_kg,
        sum(excess_co2_kg)                        as excess_co2_kg
    from {{ ref('stg_level_offs') }}
    group by flight_id
)

select
    f.flight_id,
    f.callsign,
    f.airline_icao,
    f.typecode,
    f.runway,
    f.flight_date_local,
    f.hour_local,
    coalesce(l.n_level_offs, 0)               as n_level_offs,
    coalesce(l.level_time_s, 0)               as level_time_s,
    coalesce(l.level_time_below_fl100_s, 0)   as level_time_below_fl100_s,
    l.lowest_level_fl,
    coalesce(l.n_level_offs, 0) = 0           as is_continuous_descent,
    -- no level-off -> 0 kg; level-offs on an unknown aircraft type -> stays NULL (unknown, not zero)
    if(l.flight_id is null, 0, l.excess_fuel_kg) as excess_fuel_kg,
    if(l.flight_id is null, 0, l.excess_co2_kg)  as excess_co2_kg,
    f.typecode is not null                    as has_fuel_estimate
from {{ ref('stg_flights') }} f
left join levels l on l.flight_id = f.flight_id
where f.direction = 'arrival'
