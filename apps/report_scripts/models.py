from django.db import models
from django.utils.translation import ugettext_lazy as _
from model_utils import Choices
from jsonfield import JSONField
import decimal
# Create your models here.

class ReportScripts(models.Model):
    name = models.CharField(_('Name'), max_length=255)
    status = models.BooleanField(
        'Status',
        default=True,
        choices=((True, 'Enabled'), (False, 'Disabled')),
    )
    report_type = models.CharField('Report Type', max_length=255, null=True, blank=True)
    category_id = models.ManyToManyField(
        'report_scripts.ReportScriptsCategory',
        verbose_name=_('Categories'),
        null=True,
        blank=True,
        
    )
    class Meta:
        db_table = "report_scripts"        
        verbose_name = "Automated Task"
        verbose_name_plural = 'Automated Tasks'


class ReportScriptsSchedule(models.Model):

    STATUS_PENDING = 0
    STATUS_RUNNING = 1
    STATUS_COMPLETE = 2
    STATUS_FAILED = 3
    STATUS_NO_RESULTS = 4
    STATUS_CHOICES = Choices(
        (STATUS_PENDING, 'Pending'),
        (STATUS_RUNNING, 'Running'),
        (STATUS_COMPLETE, 'Complete'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_NO_RESULTS, 'No Results'),
    )
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        'accounts.User',
        verbose_name=_('User'),
        null=True,
        blank=True,
        on_delete=models.SET_NULL, related_name="user_schedule",
    )    
    script = models.ForeignKey(
        'report_scripts.ReportScripts',
        verbose_name=_('Script Id'),
        null=True,
        blank=True,
        on_delete=models.SET_NULL, related_name="script_schedule",
    )
    client_customer_id = models.CharField('Client Customer Id', max_length=255, null=True, blank=True)
    campaign = models.ForeignKey(
        'reports.Campaign',
        verbose_name=_('Campaign Id'),
        null=True,
        blank=True,
        on_delete=models.SET_NULL, related_name="campaign_schedule",
    )
    adwords_campaign_id = models.CharField('Adwords Campaign Id', max_length=255, null=True, blank=True)
    ref_result = models.ForeignKey(
        'report_scripts.ReportScriptsResult',
        verbose_name=_('Result Id'),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="result_schedule",
    )
    status = models.PositiveSmallIntegerField(
       choices=STATUS_CHOICES,
       default=STATUS_PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    scheduled_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)    

    class Meta:
        db_table = "report_scripts_schedule"
        ordering = ['-created_at']

class ReportScriptsResult(models.Model):

    id = models.BigAutoField(primary_key=True)
    schedule = models.ForeignKey(
        'report_scripts.ReportScriptsSchedule',
        verbose_name=_('Schedule Id'),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    user = models.ForeignKey(
        'accounts.User',
        verbose_name=_('User'),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )    
    script = models.ForeignKey(
        'report_scripts.ReportScripts',
        verbose_name=_('Script Id'),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    client_customer_id = models.CharField('Customer Id', max_length=255, null=True, blank=True)
    campaign = models.ForeignKey(
        'reports.Campaign',
        verbose_name=_('Campaign Id'),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="campaign_result",
    )
    adwords_campaign_id = models.CharField('Adwords Campaign Id', max_length=255, null=True, blank=True)
    result = JSONField(null=True, blank=True, help_text='Results')
    status = models.BooleanField(_('Status'), default=False)
    total_records = models.PositiveIntegerField(_('Total Records'))
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        db_table = "report_scripts_result"
        ordering = ['-created_at']


class ReportScriptsStatus(models.Model):
    
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        'accounts.User',
        verbose_name=_('User'),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )    
    script = models.ForeignKey(
        'report_scripts.ReportScripts',
        verbose_name=_('Script Id'),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    campaign = models.ForeignKey(
        'reports.Campaign',
        verbose_name=_('Campaign Id'),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    status = models.BooleanField(_('Status'), default=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)  

    class Meta:
        db_table = "report_scripts_status"


class ReportScriptsResultAdgroup(models.Model):        
    
    id = models.BigAutoField(primary_key=True)
    result = models.ForeignKey(
        'report_scripts.ReportScriptsResult',
        verbose_name=_('Result Id'),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="result_adgroup",
    )
    ad_group_name = models.CharField('Ad Group Name', max_length=255, null=True, blank=True)  
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        db_table = "report_scripts_result_adgroup"
        ordering = ['-created_at']


class ReportScriptsResultOvercpa(models.Model):        
    
    id = models.BigAutoField(primary_key=True)
    result = models.ForeignKey(
        'report_scripts.ReportScriptsResult',
        verbose_name=_('Result Id'),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="result_overcpa",
    )
    keyword = models.CharField('Keyword', max_length=255, null=True, blank=True)
    target_cpa = models.PositiveIntegerField(
        'Target CPA',
        default=0,
    )
    cpa = models.PositiveIntegerField(
        'CPA',
        default=0,
    )
    cost = models.PositiveIntegerField(
        'Cost',
        default=0,
    )
    conversions = models.DecimalField(max_digits=12,  decimal_places=2, default=decimal.Decimal('0.00'))
    clicks = models.PositiveIntegerField(
        'Clicks',
        default=0,
    )
    conversion_rate = models.DecimalField(max_digits=12,  decimal_places=2,  default=decimal.Decimal('0.00'))
    impressions = models.PositiveIntegerField(
        'Clicks',
        default=0,
    )
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        db_table = "report_scripts_result_overcpa"
        ordering = ['-created_at']

class ReportScriptsResultSqagQs(models.Model):        
    
    #Search Query Ad Group Generator or Quality Score Search

    id = models.BigAutoField(primary_key=True)
    result = models.ForeignKey(
        'report_scripts.ReportScriptsResult',
        verbose_name=_('Result Id'),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="result_sqag_qs",
    )
    new_ad_group_id = models.CharField('New Ad Group Id', max_length=255, null=True, blank=True)
    source_ad_group_id = models.CharField('Source Ad Group Id', max_length=255, null=True, blank=True)
    source_ad_id = models.CharField('Source Ad Id', max_length=255, null=True, blank=True)
    new_ad_group = models.CharField('New Ad Group', max_length=255, null=True, blank=True)
    apply = models.BooleanField(default=False)
    ad_type = models.CharField('Ad Type', max_length=255, null=True, blank=True)
    final_url = models.CharField('Final URL', max_length=255, null=True, blank=True)
    final_mobile_url = models.CharField('Final Mobile URL', max_length=255, null=True, blank=True)
    headlines = models.TextField('Headlines', null=True, blank=True)
    descriptions = models.TextField('Descriptions', null=True, blank=True)
    headline1 = models.CharField('Headline 1', max_length=255, null=True, blank=True)
    headline2 = models.CharField('Headline 2', max_length=255, null=True, blank=True)
    headline3 = models.CharField('Headline 3', max_length=255, null=True, blank=True)
    description1 = models.CharField('Description 1', max_length=255, null=True, blank=True)
    description2 = models.CharField('Description 2', max_length=255, null=True, blank=True)
    path1 = models.CharField('Path 1', max_length=255, null=True, blank=True)
    path2 = models.CharField('Path 2', max_length=255, null=True, blank=True)
    keyword = models.CharField('Keyword', max_length=255, null=True, blank=True)
    new_ad_id = models.CharField('New Ad Id', max_length=255, null=True, blank=True)
    apply_status = models.BooleanField(default=False)     
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        db_table = "report_scripts_result_sqag_qs"
        ordering = ['-created_at']


class ReportScriptsResultAdSchedule(models.Model):        
    
    #ad schedule creation

    id = models.BigAutoField(primary_key=True)
    result = models.ForeignKey(
        'report_scripts.ReportScriptsResult',
        verbose_name=_('Result Id'),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="result_ad_schedule",
    )
    schedule_day = models.CharField('Schedule Day', max_length=255, null=True, blank=True)
    start_time = models.TimeField('Start Time', auto_now=False, auto_now_add=False, null=True, blank=True)
    end_time = models.TimeField('End Time', auto_now=False, auto_now_add=False, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        db_table = "report_scripts_result_ad_schedule"
        ordering = ['-created_at']
        
class ReportScriptsCategory(models.Model):
    id = models.BigAutoField(primary_key=True)
    category_name = models.CharField(_('Category Name'), max_length=255)
    class Meta:
        db_table = "report_scripts_category"        
        verbose_name = "Category Name"
        verbose_name_plural = 'Categories'
    def __str__(self):
        return self.category_name

class ReportScriptsSafeWords(models.Model):        

    user = models.ForeignKey(
        'accounts.User',
        verbose_name=_('User'),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    client_customer_id = models.CharField('Customer Id', max_length=255, null=True, blank=True)
    safe_words = models.TextField('Safe-words', null=True, blank=True, help_text='(One keyword per line)')


    class Meta:
        db_table = "report_scripts_safe_words"
        ordering = ['-id']

class ReportScriptsResultNegativeKeywords(models.Model):        
    
    #Add automated negative keywords from search term analysis

    id = models.BigAutoField(primary_key=True)
    result = models.ForeignKey(
        'report_scripts.ReportScriptsResult',
        verbose_name=_('Result Id'),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="result_neg_keywords",
    )
    keyword = models.CharField('Keyword', max_length=255, null=True, blank=True)
    keyword_list_name = models.CharField('Keyword List Name', max_length=255, null=True, blank=True)
    keyword_list_id = models.CharField('Source Ad Id', max_length=255, null=True, blank=True)
    cost = models.PositiveIntegerField(
        'Cost',
        default=0,
    )
    conversions = models.DecimalField(max_digits=12,  decimal_places=2, default=decimal.Decimal('0.00'))
    clicks = models.PositiveIntegerField(
        'Clicks',
        default=0,
    )
    conversion_rate = models.DecimalField(max_digits=12,  decimal_places=2,  default=decimal.Decimal('0.00'))
    cpa = models.PositiveIntegerField(
        'CPA',
        default=0,
    )     
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        db_table = "report_scripts_result_negative_keywords"
        ordering = ['-created_at']


class ReportScriptsResultShoppingSqMatch(models.Model):        
    #Shopping - Search Query vs Title / Description Match - Alert
    id = models.BigAutoField(primary_key=True)
    result = models.ForeignKey(
        'report_scripts.ReportScriptsResult',
        verbose_name=_('Result Id'),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="result_shopping_sq_match",
    )
    ad_group_name = models.CharField('Ad Group Name', max_length=255, null=True, blank=True)
    search_query = models.CharField('Search Query', max_length=255, null=True, blank=True)    
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        db_table = "report_scripts_result_shopping_sq_match"
        ordering = ['-created_at']


class ReportScriptsResultShoppingBids(models.Model):        
    #Shopping - Automated Product Listing Bids
    
    id = models.BigAutoField(primary_key=True)
    result = models.ForeignKey(
        'report_scripts.ReportScriptsResult',
        verbose_name=_('Result Id'),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="result_shopping_bids",
    )
    ad_group_name = models.CharField('Ad Group Name', max_length=255, null=True, blank=True)
    ad_group_id = models.CharField('Ad Group ID', max_length=255, null=True, blank=True)
    product_group_id = models.CharField('Product Group ID', max_length=255, null=True, blank=True)
    product_group = models.CharField('Product Group', max_length=255, null=True, blank=True)
    previous_max_cpc = models.PositiveIntegerField()
    new_max_cpc = models.PositiveIntegerField()   
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        db_table = "report_scripts_result_shopping_bids"
        ordering = ['-created_at']
