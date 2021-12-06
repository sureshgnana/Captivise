import uuid

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.shortcuts import redirect

import requests

from .exceptions import (
    PaymentIncompleteError,
    PaymentNotContinuousAuthorityError,
    PaymentUnsuccessfulError,
)
from .utils import generate_signature


class AbstractBasePayment(models.Model):
    PAYMENT_TYPE_OPTIONS_KEYS = {
        None: 'default',
        9: 'continuous_authority',
    }

    # Core details, to be set automatically or explicitly by methods.
    type = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Core details, to be set by the library user.
    action = models.CharField(max_length=7, choices=(
        ('SALE', 'sale'),
        ('VERIFY', 'verify'),
        ('PREAUTH', 'preauth'),
    ))
    amount = models.PositiveIntegerField(help_text='The amount to charge the customer, in pence')
    currency_code = models.CharField(
        max_length=3,
        help_text=(
            'The ISO-4217 formatted currency code denoting what'
            ' currency to charge the customer in.'
        )
    )
    transaction_unique = models.UUIDField(default=uuid.uuid4)
    order_ref = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text=(
            'Free format test field to store order details, reference'
            ' numbers, etc. for the Merchant\'s records.'
        ),
    )

    xref = models.CharField(max_length=255, null=True, blank=True)

    # Form prefill details
    customer_name = models.CharField(max_length=63, blank=True)
    customer_address = models.CharField(max_length=255, blank=True)
    customer_postcode = models.CharField(max_length=15, blank=True)
    customer_email = models.EmailField(max_length=255, blank=True)
    customer_phone = models.CharField(
        max_length=15,
        blank=True,
        validators=[
            RegexValidator(
                regex=r'^\+?(?:\d ?){10,15}$',
                message=(
                    'Please enter a valid phone number, including'
                    ' country code for international numbers.'
                ),
            ),
        ],
    )

    response = models.OneToOneField('ecom6.Response', null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        abstract = True

    def get_success_url(self):
        """
        Returns a URL to which to redirect the user to upon a
        successful payment.

        This method must be overridden in your subclass of
        AbstractBasePayment.
        """
        raise NotImplementedError(
            'subclasses of AbstractBasePayment must provide a get_success_url() method')

    def get_failure_url(self):
        """
        Returns a URL to which to redirect the user to upon a failed
        payment.

        This method must be overridden in your subclass of
        AbstractBasePayment.
        """
        raise NotImplementedError(
            'subclasses of AbstractBasePayment must provide a get_failure_url() method')

    def get_redirect(self):
        """
        Determines whether the payment has been successful, and returns
        a HttpResponseRedirect redirecting to the appropriate URL.
        """
        if self.response is None or self.response.response_code != 0:
            return redirect(self.get_failure_url())

        return redirect(self.get_success_url())

    def set_as_continuous_authority_payment(self, previous_payment, commit=True):
        """
        When provided a previous successful payment, this method will
        set the current payment as a continuous authority payment,
        allowing it to be taken automatically without user
        intervention.  This is useful for subscriptions, loan payments,
        and the like.

        `commit` can optionally be set `False` if more work needs doing
        on the instance before saving.
        """
        if previous_payment.response is None:
            raise PaymentIncompleteError(
                'The `previous_payment` provided has not yet completed'
                ' and cannot be referred to by another payment yet.'
            )

        if previous_payment.response.response_code != 0:
            raise PaymentUnsuccessfulError(
                'The `previous_payment` provided was unsuccessful and'
                ' cannot be referred to by another payment.'
            )

        self.xref = previous_payment.response.xref
        self.type = 9

        if commit:
            self.save()

    def set_as_normal_payment(self, commit=True):
        """
        The counterpart to `.set_as_continuous_authority_payment()`,
        this method unsets the data set when setting a payment up as a
        continuous authority payment.

        `commit` can optionally be set `False` if more work needs doing
        on the instance before saving.
        """
        self.type = None
        self.xref = None

        if commit:
            self.save()

    def get_options_key(self):
        """
        Returns a string that can be used to query the
        `ECOM6_PAYMENT_OPTIONS` in settings depending on what type of
        payment this payment is.
        """
        return self.PAYMENT_TYPE_OPTIONS_KEYS[self.type]

    def capture_continuous_authority_payment(self):
        """
        After calling `.set_as_continuous_authority_payment()`, this
        method will call Ecom6 and capture the payment without user
        interaction.
        """
        if self.type != 9 or self.xref is None:
            raise PaymentNotContinuousAuthorityError(
                'This {classname} is not set as a continuous authority'
                ' payment.  Please set it as such by calling'
                ' `.set_as_continuous_authority_payment()` before'
                ' calling this function'.format(classname=self.__class__.__name__)
            )

        from .forms import get_payment_form
        PaymentForm = get_payment_form(self.__class__, headless=True)

        try:
            scheme = settings.ECOM6_CALLBACK_SCHEME
            host = settings.ECOM6_CALLBACK_HOST
        except AttributeError as e:
            raise ImproperlyConfigured(e)

        form = PaymentForm(scheme, host, instance=self)

        response = requests.post('https://gateway.ecom6.com/direct/', data=form.get_data())

        return response

    @property
    def is_successful(self):
        """
        Determines whether the payment was successful.  Returns a
        boolean.
        """
        return self.response is not None and self.response.response_code == 0


class Response(models.Model):
    response_code = models.PositiveIntegerField(blank=True)
    response_message = models.TextField(blank=True)
    transaction_id = models.CharField(max_length=255, blank=True)
    xref = models.CharField(max_length=255, blank=True)
    state = models.TextField(
        max_length=9,
        choices=(
            ('received', 'Received'),
            ('approved', 'Approved'),
            ('declined', 'Declined'),
            ('referred', 'Referred'),
            ('reversed', 'Reversed'),
            ('captured', 'Captured'),
            ('tendered', 'Tendered'),
            ('deferred', 'Deferred'),
            ('accepted', 'Accepted'),
            ('rejected', 'Rejected'),
            ('cancelled', 'Cancelled'),
            ('finished', 'Finished'),
            ('verified', 'Verified'),
        ),
        blank=True,
    )
    timestamp = models.DateTimeField(blank=True)
    authorisation_code = models.CharField(max_length=255, blank=True)
    referral_phone = models.CharField(max_length=15, blank=True)
    amount_received = models.PositiveIntegerField(null=True, blank=True)
    card_number_mask = models.CharField(max_length=63, blank=True)
    card_type_code = models.CharField(
        max_length=2,
        choices=(
            ('MC', 'MasterCard Credit'),
            ('MD', 'MasterCard Debit'),
            ('MA', 'MasterCard International Maestro'),
            ('MI', 'MasterCard/Diners Club'),
            ('MP', 'MasterCard Purchasing'),
            ('MU', 'MasterCard Domestic Maestro (UK)'),
            ('VC', 'Visa Credit'),
            ('VD', 'Visa Debit'),
            ('EL', 'Visa Electron'),
            ('VA', 'Visa ATM'),
            ('VP', 'Visa Purchasing'),
            ('AM', 'American Express'),
            ('JC', 'JCB'),
        ),
        blank=True,
    )
    card_type = models.CharField(max_length=63, blank=True)
    card_scheme_code = models.CharField(
        max_length=2,
        choices=(
            ('MC', 'MasterCard Credit'),
            ('MD', 'MasterCard Debit'),
            ('MA', 'MasterCard International Maestro'),
            ('MI', 'MasterCard/Diners Club'),
            ('MP', 'MasterCard Purchasing'),
            ('MU', 'MasterCard Domestic Maestro (UK)'),
            ('VC', 'Visa Credit'),
            ('VD', 'Visa Debit'),
            ('EL', 'Visa Electron'),
            ('VA', 'Visa ATM'),
            ('VP', 'Visa Purchasing'),
            ('AM', 'American Express'),
            ('JC', 'JCB'),

            # Secondary card types.
            ('CF', 'Clydesdale Financial Services'),
            ('CU', 'China UnionPay'),
            ('BC', 'BankCard'),
            ('DK', 'Dankort'),
            ('DS', 'Discover'),
            ('DI', 'Diners Club'),
            ('DE', 'Diners Club Enroute'),
            ('DC', 'Diners Club Carte Blanche'),
            ('FC', 'FlexCache'),
            ('LS', 'Laser'),
            ('SO', 'Solo'),
            ('ST', 'Style'),
            ('SW', 'Switch'),
            ('TP', 'Tempo Payments'),
            ('IP', 'InstaPayment'),
            ('XX', 'Unknown/unrecognised card type'),
        ),
        blank=True,
    )
    card_scheme = models.CharField(max_length=63, blank=True)
    card_issuer = models.CharField(max_length=63, blank=True)
    card_issuer_country = models.CharField(max_length=63, blank=True)
    card_issuer_country_code = models.CharField(max_length=3, blank=True)

    card_expiry_year = models.PositiveIntegerField(blank=True, null=True)
    card_expiry_month = models.PositiveIntegerField(blank=True, null=True)

    response_data = models.TextField()
