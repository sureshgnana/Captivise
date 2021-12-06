from django.db import models
from django.shortcuts import reverse
from django.utils.translation import ugettext_lazy as _

from ecom6.models import AbstractBasePayment
from django.core.validators import RegexValidator
import uuid


class Pricing(models.Model):

    class Meta:
        verbose_name_plural = _('Pricing groups')

    def save(self, *args, **kwargs):
        if self.__class__.objects.exclude(pk=self.pk).exists():
            raise ValueError(
                'There can be only one pricing group. Please edit the existing one.')
        return super().save(*args, **kwargs)

    def get_quote(self, monthly_adwords_spend):
        fee = self.get_fee(monthly_adwords_spend)
        return fee / 100 * monthly_adwords_spend

    def get_fee(self, monthly_adwords_spend):
        """
        :param monthly_adwords_spend: Monthly AdWords spend.
        :return: Fee, in percentage (Decimal).
        """
        fee = None
        previous_maximum = None
        for price_band in self.price_bands.all():
            # Check we haven't found a lower price band.
            if previous_maximum is None or (
                    price_band.maximum is not None and price_band.maximum < previous_maximum):
                # Check the spend is lesser than the maximum allowed by the
                # price band (or that the maximum is not set).
                if price_band.maximum is None or monthly_adwords_spend <= price_band.maximum:
                    fee = price_band.fee
                    previous_maximum = price_band.maximum
        return fee


class PriceBand(models.Model):
    pricing = models.ForeignKey(
        'Pricing',
        verbose_name=_('Pricing'),
        on_delete=models.CASCADE,
        related_name='price_bands',
    )
    maximum = models.BigIntegerField(
        _('Maximum'),
        null=True,
        blank=True,
        help_text=_('Inclusive. Leave empty for no upper limit.'),
    )
    fee = models.DecimalField(
        _('Fee'),
        max_digits=5,
        decimal_places=2,
        help_text=_('Fee in percentage'),
    )

    # Commented out as it makes it hard to update from the admin.
    # class Meta:
    #     unique_together = (('maximum', 'pricing'), )


class Payment(models.Model):
    user = models.ForeignKey('accounts.User', null=True, blank=True, on_delete=models.SET_NULL)
    
    # Core details, to be set automatically or explicitly by methods.    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Core details, to be set by the library user.
    transaction_id = models.CharField(max_length=255, null=True, blank=True)
    charges_id = models.CharField(max_length=255, null=True, blank=True)
    status = models.CharField(max_length=255, null=True, blank=True)
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
    customer_name = models.CharField(max_length=63, null=True, blank=True)
    customer_email = models.EmailField(max_length=255, null=True, blank=True)
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
    customer_address = models.CharField(max_length=255, null=True, blank=True)
    customer_postcode = models.CharField(max_length=15, null=True, blank=True)    
    customer_city = models.CharField(max_length=100, null=True, blank=True)
    customer_state = models.CharField(max_length=100, null=True, blank=True)
    customer_country = models.CharField(max_length=100, null=True, blank=True)
    status = models.CharField(max_length=100, null=True, blank=True)
    card_type = models.CharField(max_length=63, blank=True, null=True)
    card_last4 = models.CharField(max_length=20, blank=True, null=True)
    card_expiry_year = models.PositiveIntegerField(blank=True, null=True)
    card_expiry_month = models.PositiveIntegerField(blank=True, null=True)    

    def __str__(self):
        return 'Payment for {name}'.format(name=self.user.get_full_name())

    def get_success_url(self):
        return '/'

    def get_failure_url(self):
        return reverse('quoting_payment_failed')
