{#
  Fails for prices outside the harmonised limits of the European day-ahead market
  (SDAC): -500 to 4000 EUR/MWh. A value outside that range cannot be a real
  clearing price, so it points to a parsing or unit error.
#}
{% test price_in_reasonable_range(model, column_name, min_value=-500, max_value=4000) %}

select *
from {{ model }}
where {{ column_name }} < {{ min_value }}
   or {{ column_name }} > {{ max_value }}

{% endtest %}
