select
    flight_id,
    `start`                         as level_start,
    `end`                           as level_end,
    cast(altitude_ft as int64)      as altitude_ft,
    cast(altitude_ft / 100 as int64) as flight_level,
    duration_s,
    groundspeed_kt,
    excess_fuel_kg,
    excess_co2_kg
from {{ source('raw_eco_nice', 'level_offs') }}
