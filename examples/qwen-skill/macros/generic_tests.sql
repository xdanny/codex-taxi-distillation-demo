{% test expression_is_true(model, column_name, expression) %}
    {% set macro = adapter.dispatch('test_expression_is_true', 'dbt') %}
    {{ macro(model, column_name, expression) }}
{% endtest %}

{% macro default__test_expression_is_true(model, column_name, expression) -%}
select * from {{ model }} where not ({{ expression }})
{%- endmacro %}
