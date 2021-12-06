from collections import OrderedDict
from hashlib import sha512
from urllib.parse import urlencode

from django.apps import apps
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.functional import cached_property


def convert_to_camel_case(string, upper=False):
    """
    Converts the given snake_case `string` to camelCase.  If `upper` is
    set to `True`, converts the given snake_case `string` to
    UpperCamelCase.
    """
    words = string.split('_')
    offset = int(not upper)

    capitalised = map(lambda word: word[0].upper() + word[1:], words[offset:])

    return ''.join(words[:offset]) + ''.join(capitalised)


def get_payment_options(payment):
    """
    Given a subclass of AbstractBasePayment, returns the relevant
    payment options dictionary, based on the options key returned by
    `payment.get_options_key()`.
    """
    payment_type_options_key = payment.get_options_key()
    try:
        return settings.ECOM6_PAYMENT_OPTIONS[payment_type_options_key]
    except (KeyError, AttributeError) as e:
        raise ImproperlyConfigured(e)


def generate_signature(secret_key, **parameters):
    """
    Given a string `secret_key` and any number of `parameters` as
    kwargs, calculates a message signature suitable for submission to
    Ecom6.

    Ignores the `signature` parameter if present.
    """
    ordered_params = OrderedDict(sorted(parameters.items()))
    ordered_params.pop('signature', None)

    signature_data = (urlencode(ordered_params) + secret_key) \
        .replace('%0D%0A', '%0A') \
        .replace('%0A%0D', '%0A') \
        .replace('%0D', '%0A')
    digest = sha512(signature_data.encode()).digest().hex()

    return digest


def get_payment_model():
    """
    Returns the AbstractBasePayment subclass as defined by
    `ECOM6_PAYMENT_MODEL` in settings.
    """
    try:
        payment_app, payment_model = settings.ECOM6_PAYMENT_MODEL
    except ValueError:
        raise ImproperlyConfigured(
            'Denote your AbstractBasePayment subclass in the form'
            ' (\'payment_app_name\', \'payment_model_name\')'
        )
    except AttributeError as e:
        raise ImproperlyConfigured(e)

    try:
        return apps.get_model(payment_app, payment_model)
    except LookupError:
        raise ImproperlyConfigured(e)


class PaymentModelLookupMixin(object):

    @cached_property
    def model(self):
        return get_payment_model()
