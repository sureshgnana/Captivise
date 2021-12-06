from django.conf import settings
from django.db import models

from model_utils import Choices
import decimal


class Campaign(models.Model):
    is_managed = models.BooleanField(
        'Manage Using Captivise',
        default=False,
        choices=((True, 'Enabled'), (False, 'Disabled')),
    )
    max_cpc_limit = models.PositiveIntegerField(
        'Maximum CPC (Cost Per Click) limit e.g. £1.00',
        default=10 * 10 ** 6,
        help_text='', #The maximum you would like to pay per click
    )

    CYCLE_PERIOD_CHOICES = Choices(
        (30, '30 days', ),
        (60, '60 days', ),
        (90, '90 days', ),
        (180, '180 days', ),
        (365, '365 days', ),
        (730, '730 days', ),
        (1095, '1095 days', ),
    )
    cycle_period_days = models.PositiveIntegerField(
        'Cycle Period',
        default=30,
        choices=CYCLE_PERIOD_CHOICES,
    )

    CONVERSION_TYPE_CPA = 'cpa'
    CONVERSION_TYPE_MARGIN = 'conversion_margin'
    CONVERSION_TYPE_CHOICES = (
        (CONVERSION_TYPE_CPA, 'Conversions by Lead'),
        (CONVERSION_TYPE_MARGIN, 'Conversions by Margin'),
    )
    conversion_type = models.CharField(
        max_length=17,
        choices=CONVERSION_TYPE_CHOICES,
        default=CONVERSION_TYPE_CPA,
    )
    target_cpa = models.PositiveIntegerField(
        'Target Cost per Acquisition (CPA) in £',
        default=0,
        help_text='The average amount you would like to pay for a conversion',
    )
    target_conversion_margin = models.DecimalField(
        'Target Margin in %',
        max_digits=5,
        decimal_places=0,
        default=0,
        help_text='The average margin you would like to achieve',
    )

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='campaigns', on_delete=models.SET_NULL,null=True)
    adwords_campaign_id = models.CharField(max_length=255)
    client_customer_id = models.CharField('Client Customer ID', max_length=255, blank=True)
    advertising_channel_type = models.CharField('Advertising Channel Type', max_length=255, blank=True, null=True)

    # Denormalised from the API
    title = models.CharField(max_length=255, blank=True)

    AD_SCHEDULE_CHOICES = Choices(
        ('', '-None-'),
        ("alldays", 'AllDays',),
        ("weekdays", 'Weekdays',),
        ("weekends", 'Weekends',),
        ("mornings", 'Mornings',),
        ("evenings", 'Evenings',),
    )
    ad_schedule = models.CharField(
        max_length=17,
        default=None,
        choices=AD_SCHEDULE_CHOICES,
        blank=True
    )

    TOP_OF_FIRST_PAGE_BID_FIRST = 'FirstPageCpc'
    TOP_OF_FIRST_PAGE_BID_TOP = 'TopOfPageCpc'
    TOP_OF_FIRST_PAGE_CHOICES = (
        ('', '-None-'),
        (TOP_OF_FIRST_PAGE_BID_FIRST, 'First Page Bid CPC'),
        (TOP_OF_FIRST_PAGE_BID_TOP, 'Top of Page Bid CPC'),
    )
    top_of_first_page_bid = models.CharField(
        'Top of Page or First Page Bid CPC',
        max_length=17,
        choices=TOP_OF_FIRST_PAGE_CHOICES,
        default=None,
        blank=True
    )
    target_conversion_rate = models.DecimalField('Target Conversion Rate', max_digits=12,  decimal_places=2,  default=decimal.Decimal('0.00'))
    target_roas = models.PositiveIntegerField(
        'Target ROAS (Return on Ad Spend)',
        default=0,
    )
    safe_words = models.TextField('Safe-words', null=True, blank=True, help_text='(One keyword per line)',)


class ScriptRun(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    increased_bids = models.PositiveIntegerField()
    decreased_bids = models.PositiveIntegerField()
    unchanged_bids = models.PositiveIntegerField()
    keywords_paused = models.PositiveIntegerField()
    
class CampaignApi(models.Model):
    status = models.CharField('Status', max_length=255)
    name = models.CharField('Name', max_length=255)
    campaign_type = models.CharField('Campaign Type', max_length=255)
