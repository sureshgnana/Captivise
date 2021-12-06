from abc import ABC, ABCMeta, abstractmethod
import decimal

from django.conf import settings
from django.db import models
from django.utils.translation import ugettext_lazy as _

from billing.utils import get_pricing


class Quote(models.Model):
    QUOTE_TYPE_AUTOMATIC = 'automatic'
    QUOTE_TYPE_ESTIMATE = 'estimate'

    QUOTE_TYPE_CHOICES = (
        (QUOTE_TYPE_AUTOMATIC, _('Automatic')),
        (QUOTE_TYPE_ESTIMATE, _('Estimate')),
    )

    created_at = models.DateTimeField(_('Created at'), auto_now_add=True)

    user_first_name = models.CharField(_('First name'), max_length=30)
    user_last_name = models.CharField(_('Last name'), max_length=30)
    user_email = models.EmailField(_('Email address'))
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_('User'),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )

    monthly_adwords_spend = models.BigIntegerField(_('Monthly Google Adwords Spend'))

    quote = models.BigIntegerField(_('Quote'))
    type = models.CharField(_('Type'), max_length=20, choices=QUOTE_TYPE_CHOICES)
    is_accepted = models.BooleanField(_('Accepted'), default=False)

    @property
    def is_automatic(self):
        return self.type == self.QUOTE_TYPE_AUTOMATIC

    @property
    def is_estimate(self):
        return self.type == self.QUOTE_TYPE_ESTIMATE

    def __str__(self):
        return '{first_name} {last_name} - £{quote}'.format(
            first_name=self.user_first_name,
            last_name=self.user_last_name,
            quote=decimal.Decimal(self.quote / 10**6).quantize(decimal.Decimal('0.01')),
        )

    def set_type_automatic(self, commit=True):
        self.type = self.QUOTE_TYPE_AUTOMATIC
        if commit:
            self.save()

    def set_type_estimate(self, commit=True):
        self.type = self.QUOTE_TYPE_ESTIMATE
        if commit:
            self.save()

    def calculate_quote(self, commit=True):
        pricing = get_pricing()  # `billing.models.Pricing` instance.
        self.quote = pricing.get_quote(self.monthly_adwords_spend)
        if commit:
            self.save()

    def set_accepted(self, commit=True):
        self.is_accepted = True
        if commit:
            self.save()

    def set_user_details(self, user, commit=True):
        self.user = user
        self.user_first_name = user.first_name
        self.user_last_name = user.last_name
        self.user_email = user.email
        if commit:
            self.save()

class StripeResponse(models.Model):
    response_code = models.CharField("Response Code", "response_code", max_length=255)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_('User'),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    timestamp = models.CharField("Timestamp", "timestamp", max_length=255)
    card_number_mask = models.CharField("Card Number Mask", "card_number_mask", max_length=255, null=True)
    user_email = models.CharField("Email", "user_email", max_length=255, null=True)
    card_expiry_year = models.PositiveIntegerField("Card Expiry Year", "card_expiry_year", null=True)
    card_expiry_month = models.PositiveIntegerField("Card Expiry Month", "card_expiry_month", null=True)
    customer_id = models.CharField("Stripe Customer ID", "customer_id", max_length=255, null=True)
    setup_intents_id = models.CharField("Stripe Intents ID", "setup_intents_id", max_length=255, null=True)
    payment_method = models.CharField("Payment Method", "payment_method", max_length=255, null=True)
    client_secret = models.CharField("Client Secret", "client_secret", max_length=255, null=True)
    card_type = models.CharField("Card Type", "card_type", max_length=255, null=True)
    response_data = models.TextField()

    def save(self, *args, **kwargs):
        return super(StripeResponse, self).save(*args, **kwargs)
    def __str__(self):
        return self.id

class CompatibilityCheckBase(ABC):

    def __init__(self, adwords_adapter):
        self.adwords_adapter = adwords_adapter

    @property
    @abstractmethod
    def label(self):
        return ''

    @abstractmethod
    def passed(self):
        return False


class CompatibilityCheckTrackingBase(CompatibilityCheckBase, metaclass=ABCMeta):

    @property
    @abstractmethod
    def tracker_type(self):
        return ''

    def passed(self):
        trackers = self.adwords_adapter.get_conversion_trackers()
        for tracker in trackers:
            if getattr(tracker, 'ConversionTracker.Type') == self.tracker_type:
                if tracker.status == 'ENABLED':
                    return True
        return False


class CompatibilityCheckWebsiteTracking(CompatibilityCheckTrackingBase):
    label = 'Website tracking set up.'
    tracker_type = 'AdWordsConversionTracker'


class CompatibilityCheckECommerceTracking(CompatibilityCheckBase):
    label = 'E-commerce tracking set up.'

    def passed(self):
        keywords = self.adwords_adapter.get_keywords()

        return any(bool(keyword['value_per_conversion']) for keyword in keywords)


class CompatibilityCheckOnPagePhoneCallTracking(CompatibilityCheckTrackingBase):
    label = 'On-page phone tracking set up.'
    tracker_type = 'WebsiteCallMetricsConversion'
