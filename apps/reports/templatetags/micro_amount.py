import decimal

from django import template


register = template.Library()


@register.filter
def micro_amount(value):
    return decimal.Decimal(value / 10**6).quantize(decimal.Decimal('0.01'))
