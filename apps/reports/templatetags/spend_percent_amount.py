import decimal
from constance import config

from django import template


register = template.Library()


@register.filter
def spend_percent_amount(value):

    spend_amount = decimal.Decimal(value / 10**6).quantize(decimal.Decimal('0.01'))
    spend_percent_amount = float(spend_amount) * (float(config.DEFAULT_PERCENT)/100.0)
    return decimal.Decimal(spend_percent_amount).quantize(decimal.Decimal('0.01'))
