from django.db import connection
from django.shortcuts import render
from django_filters import rest_framework as filters

from django import forms
from django.forms.widgets import TextInput, DateTimeInput,Select
from .models import CampaignApi

import django_filters
import logging

class DateInput(forms.DateInput):
    input_type = "date"

    def __init__(self, **kwargs):
        kwargs["format"] = "%Y-%m-%d"
        super().__init__(**kwargs)
        
STATUS_CHOICES = (('enabled', 'Enabled'),('paused', 'Paused'),('removed', 'Removed'))
CAMPAIGN_CHOICES = (('display', 'Display'),('express', 'Express'),('multi Channel', 'Multi Channel'),('search', 'Search'),('shopping', 'Shopping'),('unknown', 'Unknown'),('video', 'Video'))

class CampaignApiFilter(django_filters.FilterSet):
    
    status = django_filters.ChoiceFilter(choices=STATUS_CHOICES, label='Status', widget=Select(attrs={ 'class': 'form-control skip_these',}))
    name = django_filters.CharFilter(field_name='name', lookup_expr='icontains', label='Name', widget=TextInput(attrs={ 'class': 'form-control',}))
    campaign_type = django_filters.ChoiceFilter(field_name='campaign_type',choices=CAMPAIGN_CHOICES, label='Campaign Type', widget=Select(attrs={ 'class': 'form-control skip_these',}))

    def __init__(self,data, *args, **kwargs):
        super(CampaignApiFilter, self).__init__(*args, **kwargs)

        if len(data) != 0 and data.get('search') is not None:
            if data.get('status') is not None:
                self.form.initial['status'] = data['status']
            if data.get('name') is not None:
                self.form.initial['name'] = data['name']
            if data.get('campaign_type') is not None:
                self.form.initial['campaign_type'] = data['campaign_type']
      
    class Meta:
        model = CampaignApi
        fields = ['status', 'name', 'campaign_type']
