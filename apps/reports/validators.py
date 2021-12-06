from django.core.exceptions import ValidationError

from .exceptions import InvalidMicroAmount

from .utils import micro_amount_to_decimal


def validate_micro_amount(value):
    try:
        micro_amount_to_decimal(value)
    except InvalidMicroAmount:
        raise ValidationError('Enter a valid amount')
    return value
