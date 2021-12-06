from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import ugettext_lazy as _

from .models import ReportScriptsSafeWords, ReportScriptsResultSqagQs
from django.forms.widgets import PasswordInput, TextInput, Select, Textarea


class SafeWordsForm(forms.ModelForm):

    class Meta:
        model = ReportScriptsSafeWords
        fields = ('safe_words', )


class ExpandedTextAdForm(forms.ModelForm):

    headline1 = forms.CharField(help_text="max 30 characters", max_length=30, widget=TextInput(attrs={'class': 'form-control',}))
    headline2 = forms.CharField(help_text="max 30 characters", max_length=30, widget=TextInput(attrs={'class': 'form-control',}))
    headline3 = forms.CharField(required=False, help_text="max 30 characters", max_length=30, widget=TextInput(attrs={'class': 'form-control',}))
    description1 = forms.CharField(help_text="max 90 characters", max_length=90, widget=TextInput(attrs={'class': 'form-control',}))
    description2 = forms.CharField(required=False, help_text="max 90 characters", max_length=90, widget=TextInput(attrs={'class': 'form-control',}))
    final_url = forms.CharField(widget=TextInput(attrs={'class': 'form-control',}))
    final_mobile_url = forms.CharField(required=False, widget=TextInput(attrs={'class': 'form-control',}))
    path1 = forms.CharField(required=False, help_text="max 15 characters", max_length=15, widget=TextInput(attrs={'class': 'form-control',}))
    path2 = forms.CharField(required=False, help_text="max 15 characters", max_length=15, widget=TextInput(attrs={'class': 'form-control',}))
    apply = forms.BooleanField(required=False, label='Apply',)

    class Meta:
        model = ReportScriptsResultSqagQs
        fields = ('headline1', 'headline2', 'headline3', 'description1', 'description2', 'final_url', 'final_mobile_url', 'path1', 'path2', 'apply')


class ResponsiveSearchAdForm(forms.ModelForm):

    headlines = forms.CharField(help_text="30 characters per line", widget=Textarea(attrs={'class': 'form-control',}))
    descriptions = forms.CharField(help_text="90 characters per line", widget=Textarea(attrs={'class': 'form-control',}))
    final_url = forms.CharField(widget=TextInput(attrs={'class': 'form-control',}))
    final_mobile_url = forms.CharField(required=False, widget=TextInput(attrs={'class': 'form-control',}))
    path1 = forms.CharField(required=False, help_text="max 15 characters", max_length=15, widget=TextInput(attrs={'class': 'form-control',}))
    path2 = forms.CharField(required=False, help_text="max 15 characters", max_length=15, widget=TextInput(attrs={'class': 'form-control',}))
    apply = forms.BooleanField(required=False, label='Apply',)

    class Meta:
        model = ReportScriptsResultSqagQs
        fields = ('headlines', 'descriptions', 'final_url', 'final_mobile_url', 'path1', 'path2', 'apply')
