-- Weekly reservoir filling. `published_date` is when the value became public, which is
-- what a forecast may use; `week_end_date` is the week the value describes.
select
    area,
    area_type,
    week_end_date,
    iso_year,
    iso_week,
    published_date,
    filling_ratio,
    filling_twh,
    capacity_twh
from {{ source('bronze', 'nve_reservoir_filling') }}
