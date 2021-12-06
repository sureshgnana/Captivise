import decimal

from .exceptions import InvalidMicroAmount
import datetime


def micro_amount_to_decimal(value, raise_errors=True):
    try:
        decimal_value = decimal.Decimal(value)
    except decimal.InvalidOperation:
        if raise_errors:
            raise InvalidMicroAmount()
        return value

    decimal_value /= 10**6
    # Force two decimal places.
    try:
        return decimal_value.quantize(decimal.Decimal('0.01'))
        
        #return decimal_value.quantize(
        #    decimal.Decimal('0.01'),
        #    context=decimal.Context(traps=[decimal.Inexact])
        #)
        
    except decimal.Inexact:
        if raise_errors:
            raise InvalidMicroAmount()
        return decimal_value


def decimal_to_micro_amount(value):
    value *= 10**6

    return int(value)

def get_30_day_date():
    res = (datetime.date.today() - datetime.timedelta(30)).strftime ('%d/%m/%Y')
    return str(res)
