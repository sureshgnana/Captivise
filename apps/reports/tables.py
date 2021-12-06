from django.utils.html import format_html, mark_safe

import django_tables2 as tables
from django_tables2.utils import A

from website.tables import CurrencyColumn, PercentColumn


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
        icon = 'unchanged'

        if record['max_cpc_modified_at'] is not None:
            if value < record['previous_max_cpc']:
                icon = 'decreased'
            elif value > record['previous_max_cpc']:
                icon = 'increased'
        
        return format_html(
            '<i class="icon icon-{icon}">{icon}</i> <span class="value">{value}</span>',
            icon=icon,
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
        return format_html('<input type="checkbox" name="campaign_id[]" value="{value}"/>', value=value)

class BootstrapModalLink(tables.Column):

    def render(self, value, record):
        return format_html('<a href="javascript:void(0)" onclick="getScriptStatus({value})" data-id="{value}">View</a>', value=value)


class CampaignTable(tables.Table):
    id = CustomCheckbox(accessor="id",attrs = { "th__input": {"onclick": "toggle(this)"}}, orderable=False)
    status = StatusColumn(verbose_name='Status')
    title = tables.LinkColumn(
        verbose_name='Name',
        viewname='reports_campaign_detail',
        args=[A('id')],
    )
    advertising_channel_type = tables.Column(verbose_name='Campaign Type')
    budget = BudgetColumn(verbose_name='Budget')
    conversion_type = ConversionTypeColumn(verbose_name='Conversion Type')
    target_cpa = TargetCPAColumn(verbose_name='Target CPA')
    target_conversion_margin = TargetConversionMarginColumn(
        verbose_name='Target Conversion Margin')
    is_managed = tables.BooleanColumn(verbose_name='Captivise Management')
    script_status = BootstrapModalLink(accessor="id", verbose_name='Automated Task Status', orderable=False)
    class Meta:
        attrs = {"class": "table"}


class KeywordTable(tables.Table):
    ad_group_name = tables.Column(verbose_name='Ad Group Name')
    keyword = tables.Column(verbose_name='Keyword')
    max_cpc = MaxCPCColumn(verbose_name='Max CPC')
    previous_max_cpc = MicroAmountCurrencyColumn(verbose_name='Previous Max CPC')
    max_cpc_modified_at = tables.DateColumn(verbose_name='Max CPC Last Modified By Captivise')
    conversion_rate = PercentColumn(verbose_name='Conversion Rate')

    class Meta:
        row_attrs = {
            'class': lambda record: 'status-{status}'.format(**record)
        }
        attrs = {"class": "table"}


class RunTable(tables.Table):
    created_at = tables.DateTimeColumn(verbose_name='Date / Time')
    cycle_period = CyclePeriodColumn(verbose_name='Cycle Period')
    bid_decrease_count = tables.Column(verbose_name='Bids Decreased')
    bid_increase_count = tables.Column(verbose_name='Bids Increased')
    paused_count = tables.Column(verbose_name='Keywords Paused')
    no_change_count = tables.Column(verbose_name='Bids Unchanged')
    total_keyword_count = tables.Column(verbose_name='Total Keywords')

    class Meta:        
        attrs = {"class": "table"}


class AdgroupTable(tables.Table):
    ad_group_id = tables.Column(verbose_name='ID')
    ad_group_name = tables.Column(verbose_name='Name')

class ScriptStatusTable(tables.Table):    
    script_name = tables.Column(verbose_name='Script Name')
    status = tables.Column(verbose_name='Status')
    
