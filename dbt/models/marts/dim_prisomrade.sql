-- The five Norwegian bidding zones with names and the city/station used for weather.
select
    price_area,
    area_name,
    eic_code,
    reference_city,
    weather_station_id
from {{ ref('price_areas') }}
