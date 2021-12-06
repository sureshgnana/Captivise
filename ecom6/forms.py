import json

from django import forms
from django.apps import apps
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.forms.models import ModelForm
from django.shortcuts import get_object_or_404, reverse
from django.urls.exceptions import NoReverseMatch
from django.utils.functional import cached_property

from .models import Response
from .utils import (
    PaymentModelLookupMixin,
    convert_to_camel_case,
    generate_signature,
    get_payment_model,
    get_payment_options,
)


def get_payment_form(model_class, headless=False):
    """
    Returns a ModelForm subclass on the model defined in settings with
    ECOM6_PAYMENT_MODEL.
    """
    class PaymentForm(PaymentModelLookupMixin, ModelForm):
        form_action = 'https://gateway.ecom6.com/paymentform/'
        form_method = 'POST'

        # Details from settings.
        merchant_ID = forms.IntegerField()
        country_code = forms.CharField(max_length=2)
        merchant_category_code = forms.IntegerField()
        receiver_name = forms.CharField(max_length=6)
        receiver_account_no = forms.IntegerField()
        receiver_date_of_birth = forms.DateField(input_formats=('%Y-%m-%d', ))
        receiver_postcode = forms.CharField(max_length=8)

        # Details from urls.
        if headless:
            callback_URL = forms.URLField()
        else:
            redirect_URL = forms.URLField()

        # Automatically generated details.
        signature = forms.CharField(max_length=128)

        class Meta:
            model = model_class
            fields = '__all__'

        def __init__(self, scheme, host, *args, **kwargs):
            super().__init__(*args, **kwargs)

            for fieldname, field in self.fields.items():
                # Set all fields hidden.
                field.widget = forms.HiddenInput()

                # Remove hidden initials.
                field.show_hidden_initial = False

                # Set initial data.
                field.initial = self.get_initial_for_field(field, fieldname)


            fields_from_settings = (
                'merchant_ID',
                'country_code',
            )

            mcc_6012_fields = (
                'merchant_category_code',
                'receiver_name',
                'receiver_account_no',
                'receiver_date_of_birth',
                'receiver_postcode',
            )

            payment_options = get_payment_options(self.instance)

            if payment_options.get('merchant_category_code', None) == 6012:
                # If we're an MCC6012 merchant, (operating in the UK),
                # mark the data from settings to be set on the fields.
                fields_from_settings += mcc_6012_fields
            else:
                # If not, remove the fields.
                for fieldname in mcc_6012_fields:
                    self.fields.pop(fieldname, None)

            # Set the data on the fields from settings.
            for fieldname in fields_from_settings:
                try:
                    self.fields[fieldname].initial = payment_options.get(fieldname)
                except KeyError as e:
                    raise ImproperlyConfigured(e)

            # Set the data on the fields from URLs.
            try:
                path = reverse('ecom6:ecom6-redirect-url')
            except NoReverseMatch as e:
                raise ImproperlyConfigured(e)
            redirect_URL = '{scheme}://{host}{path}'.format(scheme=scheme, host=host, path=path)

            self.fields.get('redirect_URL', self.fields.get('callback_URL')).initial = redirect_URL

            # Remove blank fields.
            blank_fields = []
            for fieldname in self.fields:
                if (self[fieldname].value() or self.fields[fieldname].initial) in (None, ''):
                    if not fieldname == 'signature':
                        blank_fields.append(fieldname)

            for fieldname in blank_fields:
                self.fields.pop(fieldname)

            # Convert fieldnames to camelCase.
            self._fieldname_translations = {}
            fields = self.fields.__class__()
            for fieldname, field in self.fields.items():
                new_fieldname = convert_to_camel_case(fieldname)
                fields[new_fieldname] = field
                self._fieldname_translations[new_fieldname] = fieldname

            self.fields = fields

            # Generate the signature.  Must be done after all the other
            # data is in place and camelcased.
            parameters = self.get_data()

            try:
                secret_key = payment_options['secret_key']
            except KeyError as e:
                raise ImproperlyConfigured(e)

            self['signature'].initial = generate_signature(secret_key, **parameters)

        def get_data(self):
            """
            Returns the data the form is responsible for, after its
            conversion to camelCase, and (if called after
            `.__init__()`) the correct signature.  The data returned is
            then suitable for passing into a request for a continuous
            authority payment, or into `generate_signature()` to
            recalculate the signature.
            """
            data = {}
            for fieldname in self.fields:
                bound_field = self[fieldname]
                value = bound_field.initial
                data[fieldname] = self.fields[fieldname].prepare_value(value)

            return data

    return PaymentForm


class ResponseForm(ModelForm):

    class Meta:
        model = Response
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Convert fieldnames to camelCase.
        self._fieldname_translations = {}
        fields = self.fields.__class__()
        for fieldname, field in self.fields.items():
            new_fieldname = convert_to_camel_case(fieldname)
            fields[new_fieldname] = field
            self._fieldname_translations[new_fieldname] = fieldname

        self.fields = fields

    @cached_property
    def payment(self):
        Payment = get_payment_model()
        payment = get_object_or_404(Payment, transaction_unique=self.data['transactionUnique'])

        return payment

    def full_clean(self, *args, **kwargs):
        # Get the secret key from settings.
        payment_options = get_payment_options(self.payment)
        try:
            secret_key = payment_options['secret_key']
        except KeyError as e:
            raise ImproperlyConfigured(e)

        # Verify signature.
        signature = generate_signature(secret_key, **dict(self.data.items()))
        if signature != self.data['signature']:
            raise ValidationError('Signature mismatch')

        # Convert fieldnames back to snake_case.
        new_data = {}
        for fieldname, data in self.data.items():
            new_fieldname = self._fieldname_translations.get(fieldname, fieldname)
            new_data[new_fieldname] = data

        self.data = new_data

        fields = self.fields.__class__()
        for fieldname, field in self.fields.items():
            new_fieldname = self._fieldname_translations.get(fieldname, fieldname)
            fields[new_fieldname] = field

        self.fields = fields

        self.data['response_data'] = json.dumps(self.data)

        super().full_clean(*args, **kwargs)


    def save(self, commit=True):
        instance = super().save()

        self.payment.response = instance
        self.payment.save()

        return instance
