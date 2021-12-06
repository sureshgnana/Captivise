import calendar
import datetime
import decimal

from django import forms
from django.core.exceptions import ValidationError

from website.utils import months_difference

from .models import Campaign
from .validators import validate_micro_amount
from .utils import micro_amount_to_decimal
from django.forms.widgets import PasswordInput, TextInput, DateInput


class MicroAmountInput(forms.widgets.NumberInput):
    # Some browsers get rid of trailing zeros in "number" input
    # types...
    input_type = 'text'

    def __init__(self, attrs=None):
        attrs = attrs or {}
        attrs['step'] = '0.01'

        super().__init__(attrs)

    def format_value(self, value):
        if value is None:
            return value

        value = micro_amount_to_decimal(value, raise_errors=False)
        return super().format_value(value)

    def value_from_datadict(self, data, files, name):
        value = data.get(name, None)
        if value is None:
            return None

        try:
            value = decimal.Decimal(value)
        except decimal.InvalidOperation:
            return value

        value *= 10**6
        return value


class ConversionTypeSelect(forms.RadioSelect):
    option_template_name = 'reports/campaign/widgets/conversion_type_choice_widget.html'


class CampaignForm(forms.ModelForm):

    #max_cpc_limit = forms.CharField(widget=TextInput(attrs={'class': 'form-control',}), label='Maximum CPC (Cost Per Click) limit e.g. £1.00',)
    apply_all_campaign = forms.BooleanField(required=False, label='Apply for all campaigns',)
    schedule_script = forms.BooleanField(required=False, label='Enable as automated task',)
      

    class Media:
        js = (
            'reports/campaign/conversion_type_switcher.js',
            'reports/campaign/form_remainder_hider.js',
        )

    class Meta:
        model = Campaign
        exclude = ('owner', 'adwords_campaign_id', 'title', 'client_customer_id', 'advertising_channel_type' )
        widgets = {
            'target_cpa': MicroAmountInput(),
            'max_cpc_limit': MicroAmountInput(),
            'conversion_type': ConversionTypeSelect(),
            'is_managed': forms.RadioSelect(),
        }
        error_messages = {
            'target_cpa': {'invalid': 'Enter a valid amount'},
            'max_cpc_limit': {'invalid': 'Enter a valid amount'},
        }

    def clean_target_cpa(self):
        return validate_micro_amount(self.cleaned_data['target_cpa'])

    def clean_max_cpc_limit(self):
        return validate_micro_amount(self.cleaned_data['max_cpc_limit'])


class DateRangeForm(forms.Form):
    date_from = forms.DateField(initial=lambda: datetime.date.today() - datetime.timedelta(30), widget=DateInput(attrs={'class': ' ',}))
    date_to = forms.DateField(initial=datetime.date.today, widget=DateInput(attrs={'class': ' ',}))
    should_aggregate = forms.BooleanField(initial=False, required=False)

    def clean(self):
        cleaned_data = super().clean()

        date_from = cleaned_data.get("date_from")
        date_to = cleaned_data.get("date_to")

        if date_from and date_to:
            if date_to <= date_from:
                raise ValidationError('Start date must be after end date.')

            if datetime.date.today() < date_to:
               raise ValidationError('End date must not be in the future.')

            if months_difference(date_from, date_to) >= 6:
              cleaned_data['date_from'] = datetime.date(date_from.year, date_from.month, 1)

              _, last_of_the_month = calendar.monthrange(date_to.year, date_to.month)
              cleaned_data['date_to'] = datetime.date(date_to.year, date_to.month, last_of_the_month)

              cleaned_data['should_aggregate'] = True

        return cleaned_data
