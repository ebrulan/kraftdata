{#
  In prod, models land in the schema named in dbt_project.yml (staging, intermediate, marts).
  In dev and CI they are prefixed with the target schema (dbt_dev_marts, dbt_ci_marts),
  so experiments never overwrite what the dashboard reads.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- elif target.name == 'prod' -%}
        {{ custom_schema_name | trim }}
    {%- else -%}
        {{ target.schema }}_{{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
