-- One EUR/NOK rate for every calendar day, also weekends and holidays.
-- A day without a published rate uses the most recent rate before it (an "as-of" rate),
-- and the calendar runs two days ahead so tomorrow's prices can be converted too.
with bounds as (
    select min(rate_date) as first_date
    from {{ ref('stg_valutakurser') }}
),

calendar as (
    select explode(sequence(first_date, date_add(current_date(), 2), interval 1 day)) as calendar_date
    from bounds
)

select
    c.calendar_date,
    last_value(r.eur_nok, true) over (
        order by c.calendar_date rows between unbounded preceding and current row
    ) as eur_nok,
    last_value(r.rate_date, true) over (
        order by c.calendar_date rows between unbounded preceding and current row
    ) as rate_date
from calendar c
left join {{ ref('stg_valutakurser') }} r
    on r.rate_date = c.calendar_date
