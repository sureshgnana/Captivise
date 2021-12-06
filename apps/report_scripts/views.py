
from datetime import datetime, timedelta, timezone
import simplejson

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import SuspiciousOperation
from django.urls import reverse
from django.views.generic import DetailView, TemplateView, UpdateView
from django.db import connection

from accounts.views import PaidAccountRequiredMixin
from adwords.adapter import Adapter
from campaign_modifiers.models import KeywordEvent, ModifierProcessLog, KeywordActionLog
from website.views import ActiveMenuItemMixin
from django.http import HttpResponseRedirect, JsonResponse

from reports.models import Campaign
import json
from .tables import (
    ReportScriptsScheduleTable,
    ReportScriptsResultTable,
    KeywordTable,
    AdgroupTable,
    OvercpaTable,
    SqagQsTable,
    SqagQsApplyTable,
    AdScheduleTable,
    ZeroSpendTable,
    NegativeKeywordsTable,
    ShoppingSqMatchTable,
    ShoppingBidsTable,
)
from .models import (
    ReportScripts,
    ReportScriptsSchedule,
    ReportScriptsResult,
    ReportScriptsStatus,
    ReportScriptsResultAdgroup,
    ReportScriptsResultOvercpa,
    ReportScriptsResultSqagQs,
    ReportScriptsResultAdSchedule,
    ReportScriptsSafeWords,
    ReportScriptsResultNegativeKeywords,
    ReportScriptsResultShoppingSqMatch,
    ReportScriptsResultShoppingBids,
)
from .forms import SafeWordsForm, ExpandedTextAdForm, ResponsiveSearchAdForm
from django.http import HttpResponseRedirect

from django.shortcuts import render, get_object_or_404

from django_filters.views import FilterView
from django_tables2.views import SingleTableMixin

from django_filters import rest_framework as filters

from django import forms
from django.forms.widgets import TextInput,DateTimeInput

import django_filters
from .filters import (
    ReportFilter,
    ReportResultFilter,
    ReportResultKeywordFilter,
    ReportResultAdgroupFilter,
    ReportResultOvercpaFilter,
    ReportResultSqagQsFilter,
    ReportResultSqagQsApplyFilter,
    ReportResultAdScheduleFilter,
    ReportResultZeroSpendFilter,
    ReportResultNegativeKeywordsFilter,
    ReportResultShoppingSqMatchFilter,
    ReportResultShoppingBidsFilter,
)
import logging
from django.urls import reverse
from django.contrib import messages


      

class ReportScriptsView(
        ActiveMenuItemMixin,
        LoginRequiredMixin,
        PaidAccountRequiredMixin,
        TemplateView):
    template_name = 'report_scripts/report_scripts.html'

    def get_active_menu(self):
        filter_by = self.request.GET.get('filter', 'all')
        return {
            'report_scripts': True,
            'campaigns_filter_all': filter_by == 'all',
            'campaigns_filter_managed': filter_by == 'managed',
            'campaigns_filter_unmanaged': filter_by == 'unmanaged',
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if not self.request.user.has_adwords_account:
            return context

        context['has_adwords_account'] = True

        adapter = Adapter(self.request.user)

        filter_by = self.request.GET.get('filter', None)
        order_by = self.request.GET.get('sort', 'title')
        try:
            page = int(self.request.GET.get('page', 1))
        except ValueError:
            # raise a 400
            raise SuspiciousOperation('Bad request:  GET parameter `page` is not an integer')

        with connection.cursor() as cursor:
            cursor.execute("SELECT rc.title, ad.name AS script_name, ascs.created_at, ascs.status FROM report_scripts_schedule ascs LEFT JOIN reports_campaign rc ON ascs.campaign_id=rc.id LEFT JOIN ads_scripts ad ON ascs.script_id=ad.id WHERE ascs.user_id = %s ORDER BY ascs.id DESC;", [self.request.user.id])
            #data = cursor.fetchall()
            result = []
            columns = tuple( [d[0] for d in cursor.description] )
            for row in cursor:
                result.append(dict(zip(columns, row)))

        table = ReportScriptsScheduleTable(result, order_by=order_by)
        table.paginate(page=page, per_page=20)

        context.update({
            'campaigns': table
            
        })

        return context

class ReportScriptsSchedulesView(
        ActiveMenuItemMixin,
        LoginRequiredMixin,
        PaidAccountRequiredMixin,
        #TemplateView,
        SingleTableMixin,
        FilterView):
    template_name = 'report_scripts/schedules.html'
    filterset_class = ReportFilter
    table_class = ReportScriptsScheduleTable
    model = ReportScriptsSchedule
    table_pagination = {
        "per_page": 20
    }
    
    def get_active_menu(self):
        filter_by = self.request.GET.get('filter', 'all')
        return {
            'report_scripts': True,
            'report_scripts_schedules': True,
            'campaigns_filter_managed': filter_by == 'managed',
            'campaigns_filter_unmanaged': filter_by == 'unmanaged',
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if not self.request.user.has_adwords_account:
            return context

        show_filter = self.request.GET.get('campaign', None)

        if show_filter is not None:
            context['show_filter'] = True

        context['has_adwords_account'] = True

        return context


class ReportScriptsResultsView(
        ActiveMenuItemMixin,
        LoginRequiredMixin,
        PaidAccountRequiredMixin,
        SingleTableMixin,
        FilterView):
    template_name = 'report_scripts/results.html'
    
    filterset_class = ReportResultFilter
    table_class = ReportScriptsResultTable
    model = ReportScriptsResult
    table_pagination = {
        "per_page": 20
    }
    
    def get_active_menu(self):
        filter_by = self.request.GET.get('filter', 'all')
        return {
            'report_scripts': True,
            'report_scripts_results': True,
            'campaigns_filter_managed': filter_by == 'managed',
            'campaigns_filter_unmanaged': filter_by == 'unmanaged',
        }
        
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        if not self.request.user.has_adwords_account:
            return context
        
        show_filter = self.request.GET.get('campaign', None)

        if show_filter is not None:
          context['show_filter'] = True

        context['has_adwords_account'] = True

        return context    
    
class ReportScriptsResultsDetailUpdate(TemplateView):
    
    def post(self, request, *args, **kwargs):

        form_data = self.request.POST.get('form')
        form_array = json.loads(form_data)
        json_data = []   
        output = {}       
        for data in form_array:
            results = ReportScriptsResultSqagQs.objects.get(id=data['sqag_id'])
            if data['new_headline1'] == 'None':
                data['new_headline1'] = ''

            results.new_headline1 = data['new_headline1']
            results.apply = 0
            if 'apply' in data:
              results.apply = True
            results.save()
           
        
        output['result'] = True

        return JsonResponse(output, safe=False)
        
class ReportScriptsResultsDetailSchedule(TemplateView):
    template_name = 'report_scripts/results_detail.html'
    def post(self, request, *args, **kwargs):
        today = datetime.today()
        scheduled_at = today.strftime('%Y-%m-%d 01:01:00')
        result_id = self.request.POST.get('result_id')
        report_result = ReportScriptsResult.objects.get(id=result_id)
        report_schedule = ReportScriptsSchedule.objects.filter(ref_result=result_id)
        
        
        if not report_schedule:

            if report_result.script_id == 11:
                script_id = 12
            if report_result.script_id == 13:
                script_id = 14
            
            script_obj = ReportScripts.objects.get(pk=script_id)
            
            schedule_count = ReportScriptsSchedule.objects.filter(
                user_id=report_result.user_id,
                script_id=script_id,
                campaign_id=report_result.campaign_id,
                ref_result=result_id,
                status=ReportScriptsSchedule.STATUS_PENDING) \
                .count()

            """enable_count = ReportScriptsStatus.objects.filter(
                user_id=report_result.user_id,
                script_id=script_id,
                campaign_id=report_result.campaign_id,
                status=True) \
                .count()"""
            

            if schedule_count < 1:
                ReportScriptsSchedule.objects.create(
                    user_id=report_result.user_id,
                    script_id=script_id,
                    client_customer_id=report_result.client_customer_id,
                    campaign_id=report_result.campaign_id,
                    ref_result_id=result_id,
                    adwords_campaign_id=report_result.adwords_campaign_id,
                    scheduled_at=scheduled_at
                )
                messages.success(request, 'Automated task scheduled successfully.')

            """if enable_count < 1:
                enable_message = "Enable {script_name} automated task to schedule.".format(script_name=script_obj.name)
                messages.error(request, enable_message)
                return HttpResponseRedirect(reverse('reports_campaign_list'))"""
            
            if schedule_count > 0:
                messages.error(request, 'Automated task scheduled already.')
                return HttpResponseRedirect(reverse('report_scripts_results_detail', kwargs={'result_id': result_id}))
        else:
            messages.error(request, 'Automated task scheduled already.')
            

        return HttpResponseRedirect(reverse('report_scripts_results_detail', kwargs={'result_id': result_id}))
               
class ReportScriptsResultsDetailView(
        ActiveMenuItemMixin,
        LoginRequiredMixin,
        PaidAccountRequiredMixin,
        SingleTableMixin,
        FilterView):
    template_name = 'report_scripts/results_detail.html'
    
    filterset_class = ReportResultAdgroupFilter
    table_class = AdgroupTable
    model = ReportScriptsResultAdgroup

    #filterset_class = ReportResultOvercpaFilter
    #table_class = OvercpaTable
    #model = ReportScriptsResultOvercpa

    table_pagination = {
        "per_page": 20
    }
    

    def get_queryset(self):
        qs = super().get_queryset()      
        
        
        report_type = self.get_report_type(self.kwargs['result_id']) 

        self.filterset_class = report_type['table_class']
        self.model = report_type['model_class']
        if 'template_name' in report_type:
            self.template_name = report_type['template_name']

        if report_type['model_class'] == ReportScriptsResult:
            return self.model.objects.filter(pk=self.kwargs['result_id'])
        else:
            return self.model.objects.filter(result=self.kwargs['result_id'])

        return qs
        
        """
        if int(self.kwargs['result_id']) == 6:
           self.filterset_class = ReportResultOvercpaFilter
           self.model = ReportScriptsResultOvercpa
           return self.model.objects.filter(result=self.kwargs['result_id'])
        elif int(self.kwargs['result_id']) == 1:
           self.filterset_class = ReportResultAdgroupFilter
           self.model = ReportScriptsResultAdgroup
           return self.model.objects.filter(result=self.kwargs['result_id'])
        elif int(self.kwargs['result_id']) == 15:
           self.filterset_class = ReportResultSqagQsFilter
           self.model = ReportScriptsResultSqagQs
           return self.model.objects.filter(result=self.kwargs['result_id'])
        return qs
        """
        
    def get_table_class(self):
        
        report_type = self.get_report_type(self.kwargs['result_id'])        

        self.table_class = report_type['table_class']
        """
        if int(self.kwargs['result_id']) == 6:
           self.table_class = OvercpaTable
        elif int(self.kwargs['result_id']) == 1:
           self.table_class = AdgroupTable
        elif int(self.kwargs['result_id']) == 15:
           self.table_class = SqagQsTable
        """
        return self.table_class
             
    def get_table_data(self):
        if hasattr(self, "get_queryset"):
            return self.get_queryset()
                    
    def get_active_menu(self):
        filter_by = self.request.GET.get('filter', 'all')
        return {
            'report_scripts': True,
            'report_scripts_results': True,
            'campaigns_filter_managed': filter_by == 'managed',
            'campaigns_filter_unmanaged': filter_by == 'unmanaged',
        }
        
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        if not self.request.user.has_adwords_account:
            return context
        
        show_filter = self.request.GET.get('campaign', None)

        report_result = get_object_or_404(ReportScriptsResult, pk=int(self.kwargs['result_id']), user=self.request.user, client_customer_id=self.request.user.client_customer_id)    
        result = {
            'campaign_name': report_result.campaign.title,
            'script_name': report_result.script.name,
        }
        if show_filter is not None:
            context['show_filter'] = True
        
        report_type = report_result.script.report_type
        if report_type == 'sqag_qs':
            sqag_qs_results = ReportScriptsResultSqagQs.objects.filter(result=int(self.kwargs['result_id']), apply_status=True)
            if sqag_qs_results.count() > 0:
                context['apply_status'] = True

        context['has_adwords_account'] = True
        context['result_id'] = self.kwargs['result_id']
        context['result'] = result
        return context


    def get_report_type(self, result_id):
        REPORT_TYPES = {
            'ad_group': {
                'table_class': AdgroupTable,
                'filter_class': ReportResultAdgroupFilter,
                'model_class': ReportScriptsResultAdgroup
            },
            'overcpa': {
                'table_class': OvercpaTable,
                'filter_class': ReportResultOvercpaFilter,
                'model_class': ReportScriptsResultOvercpa
            },
            'keyword': {
                'table_class': KeywordTable,
                'filter_class': ReportResultKeywordFilter,
                'model_class': KeywordActionLog
            },
            'sqag_qs': {
                'template_name': 'report_scripts/report_detail_sqag.html',
                'table_class': SqagQsTable,
                'filter_class': ReportResultSqagQsFilter,
                'model_class': ReportScriptsResultSqagQs
            },
            'sqag_qs_apply': {
                'table_class': SqagQsApplyTable,
                'filter_class': ReportResultSqagQsApplyFilter,
                'model_class': ReportScriptsResultSqagQs
            },
            'ad_schedule': {
                'table_class': AdScheduleTable,
                'filter_class': ReportResultAdScheduleFilter,
                'model_class': ReportScriptsResultAdSchedule
            },
            'zero_spend': {
                'table_class': ZeroSpendTable,
                'filter_class': ReportResultZeroSpendFilter,
                'model_class': ReportScriptsResult
            },
            'negative_keywords': {
                'table_class': NegativeKeywordsTable,
                'filter_class': ReportResultNegativeKeywordsFilter,
                'model_class': ReportScriptsResultNegativeKeywords
            },
            'shopping_bids': {
                'table_class': ShoppingBidsTable,
                'filter_class': ReportResultShoppingBidsFilter,
                'model_class': ReportScriptsResultShoppingBids
            },
            'shopping_sq_match': {
                'table_class': ShoppingSqMatchTable,
                'filter_class': ReportResultShoppingSqMatchFilter,
                'model_class': ReportScriptsResultShoppingSqMatch
            },           
        }
        rs_result = ReportScriptsResult.objects.get(pk=result_id)
        report_type = rs_result.script.report_type
        return REPORT_TYPES[report_type]

        

class ReportScriptsSchedulesRemoveView(TemplateView):

    def post(self, request, *args, **kwargs):

        ids = self.request.POST.getlist('id[]')   

        if(ids):
            for id in ids:
                ReportScriptsSchedule.objects.get(pk=id).delete()                      

        return HttpResponseRedirect(reverse('report_scripts_schedules'))


class ReportScriptsSafeWordsView(
        LoginRequiredMixin,
        TemplateView):
   
    template_name = 'report_scripts/safe_words.html'    
    form_class = SafeWordsForm
    
    def post(self, request, *args, **kwargs):
        safe_words = self.request.POST.get('safe_words')
        user_id = self.request.user.id
        client_customer_id = self.request.user.client_customer_id
        account_safe_words = ReportScriptsSafeWords.objects.filter(
            user_id=user_id,
            client_customer_id=client_customer_id
        )                        
        if account_safe_words.exists():
            for account_safe_word in account_safe_words:
                account_safe_word.safe_words = safe_words
                account_safe_word.save()
        else:
            ReportScriptsSafeWords.objects.create(
                user_id=user_id,
                client_customer_id=client_customer_id,
                safe_words=safe_words,
            )
        messages.success(request, 'Updated successfully.')
        return HttpResponseRedirect(reverse('report_scripts_safe_words'))

    def get_active_menu(self):
        filter_by = self.request.GET.get('filter', 'all')
        return {
            'report_scripts': True,
        }
        
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        if not self.request.user.has_adwords_account:
            return context

        initial_dict = { 
            "keywords" : "",           
        }

        account_safe_words = ReportScriptsSafeWords.objects.filter(
            user_id=self.request.user.id,
            client_customer_id=self.request.user.client_customer_id
        )
        print(account_safe_words)
        if account_safe_words.exists():
            for account_safe_word in account_safe_words:
                initial_dict = { 
                    "safe_words" : account_safe_word.safe_words,           
                }
                
        form_class = SafeWordsForm(initial=initial_dict)
        context['form'] = form_class
        context['has_adwords_account'] = True

        return context


class ReportScriptsResultsSingleView(
        LoginRequiredMixin,
        TemplateView):
   
    template_name = 'report_scripts/ad_form.html'    
    form_class = ExpandedTextAdForm
    
    def post(self, request, *args, **kwargs):
        user_id = self.request.user.id
        client_customer_id = self.request.user.client_customer_id

        result_id = self.kwargs['result_id']

        res_obj = ReportScriptsResultSqagQs.objects.get(
            pk=result_id,
        )
        if res_obj.ad_type == 'EXPANDED_TEXT_AD':
            res_obj.headline1 = self.request.POST.get('headline1')
            res_obj.headline2 = self.request.POST.get('headline2')
            res_obj.headline3 = self.request.POST.get('headline3')
            res_obj.description1 = self.request.POST.get('description1')
            res_obj.description2 = self.request.POST.get('description2')
            res_obj.final_url = self.request.POST.get('final_url')
            res_obj.final_mobile_url = self.request.POST.get('final_mobile_url')
            res_obj.path1 = self.request.POST.get('path1')
            res_obj.path2 = self.request.POST.get('path2')

        elif res_obj.ad_type == 'RESPONSIVE_SEARCH_AD':            
            res_obj.headlines = self.request.POST.get('headlines')
            res_obj.descriptions = self.request.POST.get('descriptions')
            res_obj.final_url = self.request.POST.get('final_url')
            res_obj.final_mobile_url = self.request.POST.get('final_mobile_url')
            res_obj.path1 = self.request.POST.get('path1')
            res_obj.path2 = self.request.POST.get('path2')

        apply = True if self.request.POST.get('apply') == 'on' else False
        res_obj.apply = apply
        res_obj.save()
        
        messages.success(request, 'Updated successfully.')
        return HttpResponseRedirect(reverse('report_scripts_results_detail', kwargs={'result_id': res_obj.result_id}))

    def get_active_menu(self):
        filter_by = self.request.GET.get('filter', 'all')
        return {
            'report_scripts': True,
            'report_scripts_results': True,
            'campaigns_filter_managed': filter_by == 'managed',
            'campaigns_filter_unmanaged': filter_by == 'unmanaged',
        }
        
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        if not self.request.user.has_adwords_account:
            return context

        
        rec = ReportScriptsResultSqagQs.objects.filter(
            pk=self.kwargs['result_id'],
        )
        print(rec)
        if rec.exists():
            row = rec[0]          
            
            res = {
                'campaign_name': row.result.campaign.title,
                'script_name': row.result.script.name,
            }
            if row.ad_type == 'EXPANDED_TEXT_AD':
                initial_dict = {
                    'ad_type': row.ad_type,
                    'headline1': row.headline1,
                    'headline2': row.headline2,
                    'headline3': row.headline3,
                    'description1': row.description1,
                    'description2': row.description2,
                    'final_url': row.final_url,
                    'final_mobile_url': row.final_mobile_url,
                    'path1': row.path1,
                    'path2': row.path2,
                    'apply': row.apply
                }
                form_class = ExpandedTextAdForm(initial=initial_dict)
            elif row.ad_type == 'RESPONSIVE_SEARCH_AD':
                initial_dict = {
                    'ad_type': row.ad_type,
                    'headlines': row.headlines,
                    'descriptions': row.descriptions,
                    'final_url': row.final_url,
                    'final_mobile_url': row.final_mobile_url,
                    'path1': row.path1,
                    'path2': row.path2,
                    'apply': row.apply
                }
                form_class = ResponsiveSearchAdForm(initial=initial_dict)
        
        context['form'] = form_class
        context['has_adwords_account'] = True
        context['result'] = row
        context['res'] = res
        

        return context

