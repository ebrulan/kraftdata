-- One EUR/NOK rate per Norwegian business day.
select
    rate_date,
    rate as eur_nok
from {{ source('bronze', 'norges_bank_eur_nok') }}
where base_currency = 'EUR'
  and quote_currency = 'NOK'
