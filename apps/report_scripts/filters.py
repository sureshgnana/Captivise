from django.db import connection
from django.shortcuts import render
from django_filters import rest_framework as filters

from django import forms
from django.forms.widgets import TextInput, DateTimeInput
from .models import (
    ReportScriptsSchedule,
    ReportScriptsResult,
    ReportScriptsResultAdgroup,
    ReportScriptsResultOvercpa,
    ReportScriptsResultSqagQs,
    ReportScriptsResultAdSchedule,
    ReportScriptsResultNegativeKeywords,
    ReportScriptsResultShoppingSqMatch,
    ReportScriptsResultShoppingBids,
)
from campaign_modifiers.models import KeywordEvent, ModifierProcessLog, KeywordActionLog

import django_filters
import logging

class DateInput(forms.DateInput):
    input_type = "date"

    def __init__(self, **kwargs):
        kwargs["format"] = "%Y-%m-%d"
        super().__init__(**kwargs)
        
class ReportFilter(django_filters.FilterSet):
    created_at_from = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='gt', label='Created At From', 
        widget=DateInput(attrs={ 'class': 'datepicker','type': 'text', 'data-date-format':'dd/mm/yyyy', 'autocomplete': 'off'}))
    created_at_to = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='lt', label='Created At To', 
         widget=DateInput(attrs={ 'class': 'datepicker', 'type': 'text', 'data-date-format':'dd/mm/yyyy', 'autocomplete': 'off'}))
    status = django_filters.ChoiceFilter(field_name='status', choices=ReportScriptsSchedule.STATUS_CHOICES, label='Status', widget=forms.Select(attrs={ 'class': 'form-control skip_these',}))
    script_name = django_filters.CharFilter(field_name='script_id__name', lookup_expr='icontains', label='Automated Task', widget=TextInput(attrs={ 'class': 'form-control',}))
    campaign = django_filters.CharFilter(field_name='campaign_id__title', lookup_expr='icontains', label='Campaign Name', widget=TextInput(attrs={ 'class': 'form-control',}))
    class Meta:
        model = ReportScriptsSchedule
        fields = ['campaign','script_name','created_at_from','created_at_to','status']
        order_by_field = 'created_at'
    
    @property
    def qs(self):
        parent = super().qs
        user = getattr(self.request, 'user', None)
        return parent.filter(user=user, client_customer_id=user.client_customer_id)
        
class ReportResultFilter(django_filters.FilterSet):

    created_at_from = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='gt', label='Created At From', 
        widget=DateInput(attrs={ 'class': 'datepicker', 'type': 'text', 'data-date-format':'dd/mm/yyyy', 'autocomplete': 'off'}))
    created_at_to = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='lt', label='Created At To', 
         widget=DateInput(attrs={ 'class': 'datepicker', 'type': 'text', 'data-date-format':'dd/mm/yyyy', 'autocomplete': 'off'}))
    script_name = django_filters.CharFilter(field_name='script_id__name', lookup_expr='icontains', label='Automated Task', widget=TextInput(attrs={ 'class': 'form-control',}))
    campaign = django_filters.CharFilter(field_name='campaign_id__title', lookup_expr='icontains', label='Campaign Name', widget=TextInput(attrs={ 'class': 'form-control',}))
    
    class Meta:
        model = ReportScriptsResult
        fields = ['campaign','script_name','created_at_from','created_at_to']
    
    @property
    def qs(self):
        parent = super().qs
        user = getattr(self.request, 'user', None)
        return parent.filter(user=user, client_customer_id=user.client_customer_id)




class ReportResultKeywordFilter(django_filters.FilterSet):

    created_at_from = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='gt', label='Created At From', 
        widget=DateInput(attrs={ 'class': 'datepicker', 'type': 'text', 'data-date-format':'dd/mm/yyyy', 'autocomplete': 'off'}))
    created_at_to = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='lt', label='Created At To', 
         widget=DateInput(attrs={ 'class': 'datepicker', 'type': 'text', 'data-date-format':'dd/mm/yyyy', 'autocomplete': 'off'}))
    script_name = django_filters.CharFilter(field_name='script_id__name', lookup_expr='icontains', label='Automated Task', widget=TextInput(attrs={ 'class': 'form-control',}))
    campaign = django_filters.CharFilter(field_name='campaign_id__title', lookup_expr='icontains', label='Campaign Name', widget=TextInput(attrs={ 'class': 'form-control',}))
    

        
    class Meta:
        model = KeywordActionLog
        fields = ['campaign','script_name','created_at_from','created_at_to']
        
    def __init__(self, result_id=None, *args, **kwargs):
        self.result_id = result_id
        super(ReportResultKeywordFilter, self).__init__(*args,**kwargs)

    @property
    def qs(self):
        parent = super().qs
        #url_parts = self.request.path.split('/')
        #logger = logging.getLogger('django')
        #logger.error(url_parts)
        #result_id = int(url_parts[3])
        result_id = self.result_id
        return parent.filter(script=result_id)


class ReportResultAdgroupFilter(django_filters.FilterSet):

    created_at_from = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='gt', label='Created At From', 
        widget=DateInput(attrs={ 'class': 'datepicker', 'type': 'text', 'data-date-format':'dd/mm/yyyy', 'autocomplete': 'off'}))
    created_at_to = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='lt', label='Created At To', 
         widget=DateInput(attrs={ 'class': 'datepicker', 'type': 'text', 'data-date-format':'dd/mm/yyyy', 'autocomplete': 'off'}))
    ad_group_name = django_filters.CharFilter(field_name='ad_group_name', lookup_expr='icontains', label='Ad Group Name', widget=TextInput(attrs={ 'class': 'form-control',}))   
    

        
    class Meta:
        model = ReportScriptsResultAdgroup
        fields = ['ad_group_name','created_at_from','created_at_to']
        
    def __init__(self, result_id=None, *args, **kwargs):
        self.result_id = result_id
        super(ReportResultAdgroupFilter, self).__init__(*args,**kwargs)

    @property
    def qs(self):
        parent = super().qs
        result_id = self.result_id
        return parent.filter(result=result_id)


class ReportResultOvercpaFilter(django_filters.FilterSet):

    created_at_from = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='gt', label='Created At From', 
        widget=DateInput(attrs={ 'class': 'datepicker', 'type': 'text', 'data-date-format':'dd/mm/yyyy', 'autocomplete': 'off'}))
    created_at_to = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='lt', label='Created At To', 
         widget=DateInput(attrs={ 'class': 'datepicker', 'type': 'text', 'data-date-format':'dd/mm/yyyy', 'autocomplete': 'off'}))
    keyword = django_filters.CharFilter(field_name='keyword', lookup_expr='icontains', label='Keyword', widget=TextInput(attrs={ 'class': 'form-control',}))   
    

        
    class Meta:
        model = ReportScriptsResultOvercpa
        fields = ['keyword','created_at_from','created_at_to']
        
    def __init__(self, result_id=None, *args, **kwargs):
        self.result_id = result_id
        super(ReportResultOvercpaFilter, self).__init__(*args,**kwargs)

    @property
    def qs(self):
        parent = super().qs
        result_id = self.result_id
        return parent.filter(result=result_id)


class ReportResultSqagQsFilter(django_filters.FilterSet):

    created_at_from = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='gt', label='Created At From', 
        widget=DateInput(attrs={ 'class': 'datepicker', 'type': 'text', 'data-date-format':'dd/mm/yyyy', 'autocomplete': 'off'}))
    created_at_to = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='lt', label='Created At To', 
         widget=DateInput(attrs={ 'class': 'datepicker', 'type': 'text', 'data-date-format':'dd/mm/yyyy', 'autocomplete': 'off'}))
    new_ad_group = django_filters.CharFilter(field_name='new_ad_group', lookup_expr='icontains', label='New Ad Group', widget=TextInput(attrs={ 'class': 'form-control',}))   
    ad_type = django_filters.CharFilter(field_name='ad_type', lookup_expr='icontains', label='Ad Type', widget=TextInput(attrs={ 'class': 'form-control',}))
    ad_text = django_filters.CharFilter(field_name='ad_text', lookup_expr='icontains', label='Ad Text', widget=TextInput(attrs={ 'class': 'form-control',}))

        
    class Meta:
        model = ReportScriptsResultSqagQs
        fields = ['new_ad_group', 'ad_type', 'ad_text', 'created_at_from', 'created_at_to']


class ReportResultAdScheduleFilter(django_filters.FilterSet):

    created_at_from = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='gt', label='Created At From', 
        widget=DateInput(attrs={ 'class': 'datepicker', 'type': 'text', 'data-date-format':'dd/mm/yyyy', 'autocomplete': 'off'}))
    created_at_to = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='lt', label='Created At To', 
         widget=DateInput(attrs={ 'class': 'datepicker', 'type': 'text', 'data-date-format':'dd/mm/yyyy', 'autocomplete': 'off'}))    
    schedule_day = django_filters.CharFilter(field_name='schedule_day', lookup_expr='icontains', label='Schedule Day', widget=TextInput(attrs={ 'class': 'form-control',}))

        
    class Meta:
        model = ReportScriptsResultAdSchedule
        fields = ['schedule_day', 'created_at_to']

class ReportResultZeroSpendFilter(django_filters.FilterSet):

    created_at_from = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='gt', label='Created At From', 
        widget=DateInput(attrs={ 'class': 'datepicker', 'type': 'text', 'data-date-format':'dd/mm/yyyy', 'autocomplete': 'off'}))
    created_at_to = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='lt', label='Created At To', 
         widget=DateInput(attrs={ 'class': 'datepicker', 'type': 'text', 'data-date-format':'dd/mm/yyyy', 'autocomplete': 'off'}))   

        
    class Meta:
        model = ReportScriptsResult
        fields = ['created_at_to']

class ReportResultNegativeKeywordsFilter(django_filters.FilterSet):

    created_at_from = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='gt', label='Created At From', 
        widget=DateInput(attrs={ 'class': 'datepicker', 'type': 'text', 'data-date-format':'dd/mm/yyyy', 'autocomplete': 'off'}))
    created_at_to = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='lt', label='Created At To', 
         widget=DateInput(attrs={ 'class': 'datepicker', 'type': 'text', 'data-date-format':'dd/mm/yyyy', 'autocomplete': 'off'}))
    keyword = django_filters.CharFilter(field_name='keyword', lookup_expr='icontains', label='Keyword', widget=TextInput(attrs={ 'class': 'form-control',}))   
    

        
    class Meta:
        model = ReportScriptsResultNegativeKeywords
        fields = ['keyword','created_at_from','created_at_to']
        
    def __init__(self, result_id=None, *args, **kwargs):
        self.result_id = result_id
        super(ReportResultNegativeKeywordsFilter, self).__init__(*args,**kwargs)

    @property
    def qs(self):
        parent = super().qs
        result_id = self.result_id
        return parent.filter(result=result_id)


class ReportResultSqagQsApplyFilter(django_filters.FilterSet):

    created_at_from = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='gt', label='Created At From', 
        widget=DateInput(attrs={ 'class': 'datepicker', 'type': 'text', 'data-date-format':'dd/mm/yyyy', 'autocomplete': 'off'}))
    created_at_to = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='lt', label='Created At To', 
         widget=DateInput(attrs={ 'class': 'datepicker', 'type': 'text', 'data-date-format':'dd/mm/yyyy', 'autocomplete': 'off'}))
    new_ad_group = django_filters.CharFilter(field_name='new_ad_group', lookup_expr='icontains', label='New Ad Group', widget=TextInput(attrs={ 'class': 'form-control',}))   
    ad_type = django_filters.CharFilter(field_name='ad_type', lookup_expr='icontains', label='Ad Type', widget=TextInput(attrs={ 'class': 'form-control',}))
    ad_text = django_filters.CharFilter(field_name='ad_text', lookup_expr='icontains', label='Ad Text', widget=TextInput(attrs={ 'class': 'form-control',}))

        
    class Meta:
        model = ReportScriptsResultSqagQs
        fields = ['new_ad_group', 'ad_type', 'ad_text', 'created_at_from', 'created_at_to']


class ReportResultShoppingSqMatchFilter(django_filters.FilterSet):

    created_at_from = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='gt', label='Created At From', 
        widget=DateInput(attrs={ 'class': 'datepicker', 'type': 'text', 'data-date-format':'dd/mm/yyyy', 'autocomplete': 'off'}))
    created_at_to = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='lt', label='Created At To', 
         widget=DateInput(attrs={ 'class': 'datepicker', 'type': 'text', 'data-date-format':'dd/mm/yyyy', 'autocomplete': 'off'}))
    search_query = django_filters.CharFilter(field_name='search_query', lookup_expr='icontains', label='Search Query', widget=TextInput(attrs={ 'class': 'form-control',}))   
    

        
    class Meta:
        model = ReportScriptsResultShoppingSqMatch
        fields = ['search_query','created_at_from','created_at_to']
        
    def __init__(self, result_id=None, *args, **kwargs):
        self.result_id = result_id
        super(ReportResultShoppingSqMatchFilter, self).__init__(*args,**kwargs)

    @property
    def qs(self):
        parent = super().qs
        result_id = self.result_id
        return parent.filter(result=result_id)


class ReportResultShoppingBidsFilter(django_filters.FilterSet):

    created_at_from = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='gt', label='Created At From', 
        widget=DateInput(attrs={ 'class': 'datepicker', 'type': 'text', 'data-date-format':'dd/mm/yyyy', 'autocomplete': 'off'}))
    created_at_to = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='lt', label='Created At To', 
         widget=DateInput(attrs={ 'class': 'datepicker', 'type': 'text', 'data-date-format':'dd/mm/yyyy', 'autocomplete': 'off'}))
    product_group = django_filters.CharFilter(field_name='product_group', lookup_expr='icontains', label='Product Group', widget=TextInput(attrs={ 'class': 'form-control',}))   
    

        
    class Meta:
        model = ReportScriptsResultShoppingBids
        fields = ['product_group','created_at_from','created_at_to']
        
    def __init__(self, result_id=None, *args, **kwargs):
        self.result_id = result_id
        super(ReportResultShoppingBidsFilter, self).__init__(*args,**kwargs)

    @property
    def qs(self):
        parent = super().qs
        result_id = self.result_id
        return parent.filter(result=result_id)
