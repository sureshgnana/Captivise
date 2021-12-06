from django.utils.html import format_html, mark_safe

import django_tables2 as tables
from django_tables2.utils import A

from website.tables import CurrencyColumn, PercentColumn
import json
from django.urls import reverse
from django.conf import settings
from urllib.parse import urljoin
from .models import (
    ReportScripts,
    ReportScriptsSchedule, 
    ReportScriptsResult,
    ReportScriptsResultAdgroup,
    ReportScriptsResultOvercpa,
    ReportScriptsResultSqagQs,
    ReportScriptsResultAdSchedule,
    ReportScriptsSafeWords,
    ReportScriptsResultNegativeKeywords,
    ReportScriptsResultShoppingSqMatch,
    ReportScriptsResultShoppingBids,
)


class MicroAmountCurrencyColumn(CurrencyColumn):

    def render(self, value):
        return super().render(value / 10**6)

class BudgetColumn(MicroAmountCurrencyColumn):

    def render(self, value, record):
        value = super().render(value)

        if record.title == record.budget_name:
            return value

        return format_html(
            '<span>{budget_name}</span><br />{value}',
            budget_name=record.budget_name,
            value=value,
        )

    def value(self, value):
        return value


class TargetCPAColumn(MicroAmountCurrencyColumn):

    def render(self, value, record):
        if record.conversion_type == record.CONVERSION_TYPE_MARGIN:
            return mark_safe('&mdash;')

        return super().render(value)


class TargetConversionMarginColumn(PercentColumn):

    def render(self, value, record):
        if record.conversion_type == record.CONVERSION_TYPE_CPA:
            return mark_safe('&mdash;')

        return super().render(value)


class MaxCPCColumn(MicroAmountCurrencyColumn):

    def render(self, value, record): 
        
        return format_html(
            '<span class="value">{value}</span>',
            value=super().render(value),
        )


class ConversionTypeColumn(tables.Column):

    def render(self, value, record):
        choices = dict(record.CONVERSION_TYPE_CHOICES)
        if value == choices.get(record.CONVERSION_TYPE_MARGIN, object()):
            return 'Margin'
        elif value == choices.get(record.CONVERSION_TYPE_CPA, object()):
            return 'Lead Value'
        else:
            return mark_safe('&mdash;')


class StatusColumn(tables.Column):

    def render(self, value, record):
        return format_html('<i class="icon icon-{icon}">{icon}</i>', icon=value)


class CyclePeriodColumn(tables.Column):

    def render(self, value):
        return format_html('{value} Days', value=super().render(value))


class CustomCheckbox(tables.CheckBoxColumn):

    def render(self, value, record):
        return format_html('<input type="checkbox" name="id[]" value="{value}"/>', value=value)

class ResultJsonColumn(tables.Column):

    def render(self, value, record):
        if value !="":
            json_object = json.loads(value)
            json_list = []
            total_records = len(json_object)
            for row in json_object:
                if 'name' in row:                
                    json_list.append(row['name'])
                if 'result' in row:  
                    json_list.append(row['result'])
            return format_html("Total Records: {total_records}<br />" + "<br /> ".join(json_list), total_records=total_records)

class ReportFileColumn(tables.Column):

    def render(self, value, record):
        
        if value !="":
            report_file = urljoin(settings.MEDIA_URL, 'report', value)
            report_file = "/".join((report_file, value))
            return format_html('<a href="{report_file}">Download</a>', report_file=report_file)


class ReportScriptsScheduleTable(tables.Table):
    id = CustomCheckbox(accessor="id",attrs = { "th__input": {"onclick": "toggle(this)"}}, orderable=False)    
    campaign_name = tables.LinkColumn(
        verbose_name='Campaign Name',
        viewname='reports_campaign_detail',
        args=[A('campaign_id')],
        accessor="campaign.title"
    )    
    script_name = tables.Column(verbose_name='Automated Task', accessor="script.name")    
    status = tables.Column(verbose_name='Status')
    created_at = tables.DateTimeColumn(verbose_name='Created At')
    scheduled_at = tables.DateTimeColumn(verbose_name='Scheduled At')
    
    class Meta:        
        attrs = {"class": "table"}


class ReportScriptsResultTable(tables.Table):
    
    campaign_name = tables.LinkColumn(
        verbose_name='Campaign Name',
        viewname='reports_campaign_detail',
        args=[A('campaign_id')],
        accessor="campaign.title",
    )
    
    script_name = tables.LinkColumn(
        verbose_name='Automated Task',
        viewname='report_scripts_results_detail',
        args=[A('id')],
        accessor="script.name",
    )
    result = ResultJsonColumn(verbose_name='Results')
    created_at = tables.DateTimeColumn(verbose_name='Date / Time')

    class Meta:
        attrs = {"class": "table"}

class KeywordTable(tables.Table):
    ad_group_name = tables.Column(verbose_name='Ad Group Name')
    keyword = tables.Column(verbose_name='Keyword')
    action = tables.Column(verbose_name='Action')
    new_max_cpc = MaxCPCColumn(verbose_name='Max CPC')
    previous_max_cpc = MicroAmountCurrencyColumn(verbose_name='Previous Max CPC')
    conversion_rate = PercentColumn(verbose_name='Conversion Rate')
    created_at = tables.DateColumn(verbose_name='Created At')    

    class Meta:
        
        attrs = {"class": "table"}

class AdgroupTable(tables.Table):
    ad_group_name = tables.Column(verbose_name='Ad Group Name')   
    created_at = tables.DateColumn(verbose_name='Created At')

    class Meta:
        
        attrs = {"class": "table"}

class OvercpaTable(tables.Table):
    keyword = tables.Column(verbose_name='Keyword')
    target_cpa = MicroAmountCurrencyColumn(verbose_name='Target CPA')
    cpa = MicroAmountCurrencyColumn(verbose_name='CPA')
    cost = MicroAmountCurrencyColumn(verbose_name='Cost')
    conversions = tables.Column(verbose_name='Conversions')
    clicks = tables.Column(verbose_name='Clicks')
    conversion_rate = PercentColumn(verbose_name='Conversion Rate')
    impressions = tables.Column(verbose_name='Impressions')
    created_at = tables.DateColumn(verbose_name='Created At')

    class Meta:
        
        attrs = {"class": "table"}


class SqagQsTable(tables.Table):
    new_ad_group = tables.Column(verbose_name='Ad Group')
    keyword = tables.Column(verbose_name='Keyword')  
    apply = tables.BooleanColumn(verbose_name='Apply', orderable=False)      
    ad_type = tables.LinkColumn(
        verbose_name='Ad Type',
        viewname='report_scripts_results_single',
        args=[A('id')],
    )
    created_at = tables.DateColumn(verbose_name='Created At')
    
    class Meta:
        
        attrs = {"class": "table"}


class SqagQsApplyTable(tables.Table):
    
    new_ad_group = tables.Column(verbose_name='Ad Group')
    keyword = tables.Column(verbose_name='Keyword')
    apply = tables.BooleanColumn(verbose_name='Apply')
    ad_type = tables.Column(verbose_name='Ad Type')
    created_at = tables.DateColumn(verbose_name='Created At')    
    class Meta:
        
        attrs = {"class": "table"}

class AdScheduleTable(tables.Table):
    schedule_day = tables.Column(verbose_name='Schedule Day')
    start_time = tables.Column(verbose_name='Start Time')
    end_time = tables.Column(verbose_name='End Time')
    created_at = tables.DateColumn(verbose_name='Created At')

    class Meta:
        
        attrs = {"class": "table"}

class ZeroSpendTable(tables.Table):
    result = ResultJsonColumn(verbose_name='Result')
    created_at = tables.DateColumn(verbose_name='Created At')

    class Meta:
        
        attrs = {"class": "table"}


class NegativeKeywordsTable(tables.Table):
    keyword = tables.Column(verbose_name='Keyword')
    keyword_list_name = tables.Column(verbose_name='List Name')    
    cpa = MicroAmountCurrencyColumn(verbose_name='CPA')
    cost = MicroAmountCurrencyColumn(verbose_name='Cost')
    conversions = tables.Column(verbose_name='Conversions')
    clicks = tables.Column(verbose_name='Clicks')
    conversion_rate = PercentColumn(verbose_name='Conversion Rate')
    created_at = tables.DateColumn(verbose_name='Created At')

    class Meta:
        
        attrs = {"class": "table"}

class ShoppingSqMatchTable(tables.Table):
    
    ad_group_name = tables.Column(verbose_name='Ad Group Name')
    search_query = tables.Column(verbose_name='Search Query')
    created_at = tables.DateColumn(verbose_name='Created At')    
    class Meta:
        
        attrs = {"class": "table"}

class ShoppingBidsTable(tables.Table):
    
    ad_group_name = tables.Column(verbose_name='Ad Group Name')
    product_group = tables.Column(verbose_name='Product Group')
    previous_max_cpc = tables.Column(verbose_name='Previous Max CPC')
    new_max_cpc = tables.Column(verbose_name='New Max CPC')
    created_at = tables.DateColumn(verbose_name='Created At')    
    class Meta:
        
        attrs = {"class": "table"}
