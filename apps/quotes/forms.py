from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import ugettext_lazy as _

from .models import Quote


class QuoteEstimateForm(forms.ModelForm):

    class Meta:
        model = Quote
        fields = ('monthly_adwords_spend', )

    def save(self, commit=True):
        self.instance.calculate_quote(commit=False)
        self.instance.set_type_estimate(commit=False)
        return super().save(commit)


class TermsAndConditionsForm(forms.Form):
    terms_and_conditions_accepted = forms.BooleanField()

    def clean_terms_and_conditions_accepted(self):
        if not self.cleaned_data['terms_and_conditions_accepted']:
            raise ValidationError(
                _('You must accept the terms and conditions'), code='ts_cs_unaccepted')
