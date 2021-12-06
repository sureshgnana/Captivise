from django.utils.html import format_html, mark_safe

import django_tables2 as tables
from django_tables2.utils import A

from website.tables import CurrencyColumn, PercentColumn
import decimal


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

        """if record['max_cpc_modified_at'] is not None:
            if value < record['previous_max_cpc']:
                icon = 'decreased'
            elif value > record['previous_max_cpc']:
                icon = 'increased'"""

        icon = 'increased'
        return format_html(
            '<i class="icon icon-{icon}">{icon}</i><span class="value">{value}</span>',
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
        return 'success' if value == "succeeded" else value


class CyclePeriodColumn(tables.Column):

    def render(self, value):
        return format_html('{value} Days', value=super().render(value))


class CustomCheckbox(tables.CheckBoxColumn):

    def render(self, value, record):
        return format_html('<input type="checkbox" name="campaign_id[]" value="{value}"/>', value=value)

class AmountColumn(CurrencyColumn):

    def render(self, value, record):
        amount = decimal.Decimal(value/ 100.0).quantize(decimal.Decimal('0.01'))
        return super().render(amount)


class PaymentTable(tables.Table):
    transaction_id = tables.Column(verbose_name='Transaction ID')
    status = StatusColumn(verbose_name='Status')    
    amount = AmountColumn(verbose_name='Amount')
    id = tables.LinkColumn(
        verbose_name='Invoice',
        viewname='accounts_download_invoice',
        args=[A('id')],
        text='Invoice',
        orderable=False,
    )
    created_at = tables.Column(verbose_name='Created At')
    class Meta:
        attrs = {"class": "table"}   
