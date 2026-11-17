select
    flight_id,
    lower(icao24)                                         as icao24,
    trim(callsign)                                        as callsign,
    left(trim(callsign), 3)                               as airline_icao,  -- ICAO callsign prefix
    upper(typecode)                                       as typecode,
    fuel_type_proxy,
    case direction when 'arr' then 'arrival' else 'departure' end as direction,
    runway,
    first_seen,
    last_seen,
    date(last_seen, 'Europe/Paris')                       as flight_date_local,
    extract(hour from datetime(last_seen, 'Europe/Paris')) as hour_local
from {{ source('raw_eco_nice', 'flights') }}
qualify row_number() over (partition by flight_id order by last_seen desc) = 1
