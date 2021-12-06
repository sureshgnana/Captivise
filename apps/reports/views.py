from datetime import datetime, timedelta, timezone
import simplejson

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import SuspiciousOperation
from django.urls import reverse
from django.views.generic import DetailView, TemplateView, UpdateView
from django.db import connection

from accounts.views import PaidAccountRequiredMixin
from adwords.adapter import Adapter
from campaign_modifiers.models import KeywordEvent, ModifierProcessLog
from website.views import ActiveMenuItemMixin

from .forms import CampaignForm, DateRangeForm
from .models import Campaign
from .tables import (
    CampaignTable,
    KeywordTable,
    RunTable,
)
from report_scripts.models import ReportScripts, ReportScriptsSchedule, ReportScriptsStatus,ReportScriptsCategory
from django.http import HttpResponseRedirect, JsonResponse

from .filters import CampaignApiFilter

import logging
#01/12/20
from website.utils import cms_page_content
from website.models import CmsContent
from django.contrib import messages
from django.http import QueryDict

class DashboardView(
        ActiveMenuItemMixin,
        LoginRequiredMixin,
        PaidAccountRequiredMixin,
        TemplateView):
    template_name = 'reports/dashboard.html'

    def get_active_menu(self):
        date_range = self.request.GET.get('range', 'month')

        return {
            'dashboard': True,
            'dashboard_today': date_range == 'today',
            'dashboard_week': date_range == 'week',
            'dashboard_month': date_range == 'month',
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if not self.request.user.has_adwords_account:
            return context

        context['has_adwords_account'] = True
        conversions_exist = False

        date_range_form = DateRangeForm()
        date_from = date_range_form.fields['date_from'].initial()
        date_to = date_range_form.fields['date_to'].initial()
        should_aggregate = date_range_form.fields['should_aggregate'].initial

        if 'date_from' in self.request.GET and 'date_to' in self.request.GET:
            date_range_form = DateRangeForm(self.request.GET.copy())
            if date_range_form.is_valid():
                date_from = date_range_form.cleaned_data['date_from']
                date_to = date_range_form.cleaned_data['date_to']
                should_aggregate = date_range_form.cleaned_data['should_aggregate']

        context['date_range_form'] = date_range_form
        context['chart_range'] = self.request.GET.get('chart_range', 'last30Days')

        adapter = Adapter(self.request.user)
        kwargs = {'cast_dates': False}
        if context['chart_range'] != 'allTime':
            kwargs['date_range'] = adapter.format_date_range(date_from, date_to)

        metrics = adapter.get_campaign_metrics(**kwargs)

        if should_aggregate:
            metrics = adapter.aggregate_campaign_metrics_to_monthly(
                metrics, date_format='%Y-%m-%d')

        for metric in metrics.values():
            #metric['cpc'] /= 10**6
            if metric['conversions'] > 0 and conversions_exist == False:
                conversions_exist = True

        context['metrics'] = simplejson.dumps(metrics)
        context['conversions_exist'] = conversions_exist

        event_date_range = self.request.GET.get('range', 'month').lower()
        date_range_lengths = {'today': 1, 'week': 7, 'month': 28}
        client_customer_id = self.request.user.client_customer_id

        with connection.cursor() as cursor:
            cursor.execute("SELECT campaign_modifiers_keywordevent.action, COUNT(*) FROM campaign_modifiers_keywordevent INNER JOIN campaign_modifiers_modifierprocesslog ON campaign_modifiers_keywordevent.modifier_process_log_id=campaign_modifiers_modifierprocesslog.id INNER JOIN reports_campaign ON campaign_modifiers_modifierprocesslog.adwords_campaign_id=reports_campaign.adwords_campaign_id WHERE reports_campaign.owner_id = %s AND reports_campaign.client_customer_id = %s AND campaign_modifiers_keywordevent.created_at BETWEEN NOW() - INTERVAL %s DAY AND NOW() GROUP BY campaign_modifiers_keywordevent.action;", [self.request.user.id, client_customer_id, date_range_lengths[event_date_range]])
            events = cursor.fetchall()

        increased = 0
        decreased = 0
        unchanged = 0
        paused = 0

        for event in events:
            if event[0] == "increased_cpc":
                increased = event[1]
            if event[0] == "decreased_cpc":
                decreased = event[1]
            if event[0] == "no_action":
                unchanged = event[1]
            if event[0] == "paused":
                paused = event[1]
        
        script_results = []
        with connection.cursor() as cursor:
            cursor.execute("SELECT rscr.script_id, ANY_VALUE(rs.name) script_name, SUM(total_records), ANY_VALUE(rscr.id) as result_id FROM report_scripts_result rscr INNER JOIN report_scripts rs ON rs.id=rscr.script_id WHERE rscr.user_id = %s AND rscr.client_customer_id = %s AND rscr.created_at BETWEEN NOW() - INTERVAL %s DAY AND NOW() GROUP BY rscr.script_id;", [self.request.user.id, client_customer_id, date_range_lengths[event_date_range]])
            script_results = cursor.fetchall()

        context.update({
            'increased_bid_count': increased,
            'decreased_bid_count': decreased,
            'unchanged_bid_count': unchanged,
            'paused_keywords_count': paused,
            'script_results': script_results,
        })

        return context


class CampaignListView(
        ActiveMenuItemMixin,
        LoginRequiredMixin,
        PaidAccountRequiredMixin,
        TemplateView):
    template_name = 'reports/campaign/list.html'
    filterset_class = CampaignApiFilter
    
    def get_active_menu(self):
        filter_by = self.request.GET.get('filter', 'all')
        return {
            'campaigns': True,
            'campaigns_filter_all': filter_by == 'all',
            'campaigns_filter_managed': filter_by == 'managed',
            'campaigns_filter_unmanaged': filter_by == 'unmanaged',
        }
    def search_data(self,data):
      status = self.request.GET.get('status', None)
      campaign_type = self.request.GET.get('campaign_type', None)
      name = self.request.GET.get('name', None)
      if status:
         data = [x for x in data if status.lower() in x.status.lower()]
      if campaign_type:
         data = [x for x in data if campaign_type.lower() in x.advertising_channel_type.lower()]
      if name:
         data = [x for x in data if name.lower() in x.title.lower()]
      return data
    
        
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if not self.request.user.has_adwords_account:
            return context

        context['has_adwords_account'] = True

        adapter = Adapter(self.request.user)

        filter_by = self.request.GET.get('filter', None)
        search = self.request.GET.get('search', None)
        order_by = self.request.GET.get('sort', 'title')
        try:
            page = int(self.request.GET.get('page', 1))
        except ValueError:
            # raise a 400
            raise SuspiciousOperation('Bad request:  GET parameter `page` is not an integer')

        data = adapter.get_mapped_campaigns(filter_by=filter_by)
        if search == 'Apply Filter':
           data = self.search_data(data)
              
        table = CampaignTable(data, order_by=order_by)
        table.paginate(page=page, per_page=20)
        report_scripts = ReportScripts.objects.filter(status=True).exclude(pk__in=[12, 14])
        report_scripts_category = ReportScriptsCategory.objects.filter()
        
        show_filter = self.request.GET.get('search', None)
        order_by = self.request.GET.get('sort', None)
        page = self.request.GET.get('page', None)

        if show_filter is not None:
           context['show_filter'] = True
        
        data = self.request.GET.copy()
        context['filter'] = CampaignApiFilter(data, queryset=report_scripts)
        context.update({
            'campaigns': table,
            'report_scripts': report_scripts,
            'report_scripts_category': report_scripts_category,
            'order_by': order_by,
            'page': page,
            
        })

        return context


class BaseCampaignView(
        ActiveMenuItemMixin,
        LoginRequiredMixin,
        PaidAccountRequiredMixin,
        DetailView):
    model = Campaign
    pk_url_kwarg = 'campaign_id'
    context_object_name = 'campaign'

    def get_active_menu(self):
        return {
            'campaigns': True,
        }


class CampaignSettingsView(UpdateView, BaseCampaignView):
    template_name = 'reports/campaign/settings.html'
    form_class = CampaignForm
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context.update({
            'page_content_conv_margin': cms_page_content('conversions_by_margin'),
            'page_content_conv_lead': cms_page_content('conversions_by_lead'),
        })   

        return context

    def post(self, request, *args, **kwargs):
        form = CampaignForm(self.request.POST)
        user_id = self.request.user.id
        client_customer_id = self.request.user.client_customer_id
        if form.is_valid():        
            obj = form.save(commit=False)
            is_managed = form['is_managed'].data
            campaign_id = int(self.kwargs['campaign_id'])
            if is_managed == False:
                campaign_obj = Campaign.objects.get(pk=campaign_id)
                campaign_obj.is_managed = False                
                campaign_obj.save()
            else:
                max_cpc_limit = form['max_cpc_limit'].data
                cycle_period_days = form['cycle_period_days'].data
                conversion_type = str(form['conversion_type'].data)
                target_cpa = form['target_cpa'].data
                target_conversion_margin = form['target_conversion_margin'].data
                ad_schedule = str(form['ad_schedule'].data)
                top_of_first_page_bid = str(form['top_of_first_page_bid'].data)
                apply_all_campaign = form['apply_all_campaign'].data
                schedule_script = form['schedule_script'].data
                target_conversion_rate = form['target_conversion_rate'].data
                target_roas = form['target_roas'].data
                safe_words = form['safe_words'].data                  

                campaign_obj = Campaign.objects.get(pk=campaign_id)
                campaign_obj.is_managed = is_managed
                campaign_obj.max_cpc_limit = max_cpc_limit
                campaign_obj.cycle_period_days = cycle_period_days
                campaign_obj.conversion_type = conversion_type
                campaign_obj.target_cpa = target_cpa
                campaign_obj.target_conversion_margin = target_conversion_margin
                campaign_obj.ad_schedule = ad_schedule
                campaign_obj.top_of_first_page_bid = top_of_first_page_bid
                campaign_obj.target_conversion_rate = target_conversion_rate
                campaign_obj.target_roas = target_roas
                campaign_obj.safe_words = safe_words
                campaign_obj.save()

                #logger = logging.getLogger('django')
                #print(form.errors)
                #logger.error(is_managed)
                tcpa_scripts = {
                    '30': 4,
                    '60': 5,
                    '90': 6,
                    '180': 7,
                    '365': 8,
                    '730': 9,
                    '1095': 10
                }

                if apply_all_campaign == True:

                    user_campaigns = Campaign.objects.filter(owner=user_id, client_customer_id=client_customer_id)
                    #logger.error(user_campaigns)
                    for user_campaign in user_campaigns:
                        user_campaign.is_managed = is_managed
                        user_campaign.max_cpc_limit = max_cpc_limit
                        user_campaign.cycle_period_days = cycle_period_days
                        user_campaign.conversion_type = conversion_type
                        user_campaign.target_cpa = target_cpa
                        user_campaign.target_conversion_margin = target_conversion_margin
                        user_campaign.ad_schedule = ad_schedule
                        user_campaign.top_of_first_page_bid = top_of_first_page_bid
                        user_campaign.target_conversion_rate = target_conversion_rate
                        user_campaign.target_roas = target_roas
                        user_campaign.safe_words = safe_words
                        user_campaign.save()
                        
                        if schedule_script == True:                        
                            
                            next_day = datetime.today() + timedelta(days=1)
                            scheduled_at = next_day.strftime('%Y-%m-%d 01:01:00')
                            script_id = tcpa_scripts[cycle_period_days]

                            if not ReportScriptsSchedule.objects.filter(user_id=user_id, script_id=script_id, campaign_id=user_campaign.id, status=0).exists() and ReportScriptsStatus.objects.filter(user_id=user_id, script_id=script_id, campaign_id=user_campaign.id, status=True).exists():
                                
                                ReportScriptsSchedule.objects.create(
                                    user_id=user_id,
                                    script_id=script_id,
                                    client_customer_id=client_customer_id,
                                    campaign_id=user_campaign.id,
                                    adwords_campaign_id=user_campaign.adwords_campaign_id,
                                    scheduled_at=scheduled_at
                                )

                if schedule_script == True and apply_all_campaign != True:                
                    
                    next_day = datetime.today() + timedelta(days=1)
                    scheduled_at = next_day.strftime('%Y-%m-%d 01:00:00')
                    script_id = tcpa_scripts[cycle_period_days]

                    if not ReportScriptsSchedule.objects.filter(user_id=user_id, script_id=script_id, campaign_id=campaign_obj.id,status=0).exists() and ReportScriptsStatus.objects.filter(user_id=user_id, script_id=script_id, campaign_id=campaign_obj.id, status=True).exists():
                        
                        ReportScriptsSchedule.objects.create(
                            user_id=user_id,
                            script_id=script_id,
                            client_customer_id=client_customer_id,
                            campaign_id=campaign_obj.id,
                            adwords_campaign_id=campaign_obj.adwords_campaign_id,
                            scheduled_at=scheduled_at
                        )
            
        else:
            logger = logging.getLogger('django')
            #print(form.errors)
            logger.error(form.errors)
            
        return HttpResponseRedirect(reverse('reports_campaign_detail', args=(self.kwargs['campaign_id'], )))
            

    def get_active_menu(self):
        active = super().get_active_menu()

        active.update({
            'campaign_settings': True,
        })

        return active

    def get_success_url(self):
        return reverse('reports_campaign_detail', args=(self.kwargs['campaign_id'], ))


class BaseCampaignDetailView(BaseCampaignView):

    def get_active_menu(self):
        active = super().get_active_menu()

        active.update({
            'campaign_overview': True,
        })

        return active

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if not self.request.user.has_adwords_account:
            return context

        context['has_adwords_account'] = True
        conversions_exist = False

        date_range_form = DateRangeForm()
        date_from = date_range_form.fields['date_from'].initial()
        date_to = date_range_form.fields['date_to'].initial()
        should_aggregate = date_range_form.fields['should_aggregate'].initial

        if 'date_from' in self.request.GET and 'date_to' in self.request.GET:
            date_range_form = DateRangeForm(self.request.GET.copy())
            if date_range_form.is_valid():
                date_from = date_range_form.cleaned_data['date_from']
                date_to = date_range_form.cleaned_data['date_to']
                should_aggregate = date_range_form.cleaned_data['should_aggregate']

        context['date_range_form'] = date_range_form
        context['chart_range'] = self.request.GET.get('chart_range', 'thisWeek')

        adapter = Adapter(self.request.user)
        kwargs = {'cast_dates': False, 'campaign_id': self.object.adwords_campaign_id}
        if context['chart_range'] != 'allTime':
            kwargs['date_range'] = adapter.format_date_range(date_from, date_to)

        metrics = adapter.get_campaign_metrics(**kwargs)

        if should_aggregate:
            metrics = adapter.aggregate_campaign_metrics_to_monthly(
                metrics, date_format='%Y-%m-%d')

        for metric in metrics.values():
            #metric['cpc'] /= 10**6
            if metric['conversions'] > 0 and conversions_exist == False:
                conversions_exist = True

        context['metrics'] = simplejson.dumps(metrics)
        context['conversions_exist'] = conversions_exist

        return context


class CampaignKeywordView(BaseCampaignDetailView):
    template_name = 'reports/campaign/keywords.html'

    def get_active_menu(self):
        active = super().get_active_menu()

        active.update({
            'campaign_keywords': True,
        })

        return active

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if not self.request.user.has_adwords_account:
            return context

        context['has_adwords_account'] = True

        adapter = Adapter(self.request.user)

        data = adapter.get_mapped_keywords(self.object)
        

        order_by = self.request.GET.get('sort', 'keyword')
        try:
            page = int(self.request.GET.get('page', 1))
        except ValueError:
            # raise a 400
            raise SuspiciousOperation('Bad request:  GET parameter `page` is not an integer')

        table = KeywordTable(data, order_by=order_by)
        table.paginate(page=page, per_page=20)

        context.update({
            'keywords': table,
        })

        return context


class CampaignRunsView(BaseCampaignDetailView):
    template_name = 'reports/campaign/runs.html'

    def get_active_menu(self):
        active = super().get_active_menu()

        active.update({
            'campaign_runs': True,
        })

        return active

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        runs = ModifierProcessLog.objects \
            .filter(adwords_campaign_id=self.object.adwords_campaign_id) \
            .order_by('-started_at') \
            .prefetch_related('keyword_events')

        data = []
        for run in runs:
            increased = run.keyword_events.filter(
                action=KeywordEvent.ACTION_CHOICES.increased_cpc).count()
            decreased = run.keyword_events.filter(
                action=KeywordEvent.ACTION_CHOICES.decreased_cpc).count()
            unchanged = run.keyword_events.filter(
                action=KeywordEvent.ACTION_CHOICES.no_action).count()
            paused = run.keyword_events.filter(action=KeywordEvent.ACTION_CHOICES.paused).count()
            
            cycle_period = None
            if 'cycle_period' in run.parameters:
                cycle_period = run.parameters.get('cycle_period', None)

            data.append({
                'created_at': run.started_at,
                'cycle_period': cycle_period,
                'bid_increase_count': increased,
                'bid_decrease_count': decreased,
                'no_change_count': unchanged,
                'paused_count': paused,
                'total_keyword_count': sum((increased, decreased, unchanged, paused)),
            })

        order_by = self.request.GET.get('sort', '-created_at')
        page = self.request.GET.get('page', 1)

        table = RunTable(data, order_by=order_by)
        table.paginate(page=page, per_page=20)

        context.update({
            'runs': table,
        })

        return context

class CampaignReportScriptsScheduleView(BaseCampaignDetailView):

    def post(self, request, *args, **kwargs):        

        campaign_ids = self.request.POST.getlist('campaign_id[]')
        script_id = self.request.POST.get('script_id')
        user_id = self.request.user.id
        client_customer_id = self.request.user.client_customer_id
        next_day = datetime.today() + timedelta(days=1)
        scheduled_at = next_day.strftime('%Y-%m-%d 01:01:00')
        scheduled = False
        schedule_exist = False
        script_status = True

        return_url = build_url('reports_campaign_list', params=make_url(self, request))

        check_managed = Campaign.objects.values_list('id', flat=True).filter(owner=user_id, is_managed=True, client_customer_id=client_customer_id)
        if len(check_managed) < 1:
            messages.error(request, 'Automated task can not be run on unmanaged campaigns. Please update campaign settings allow to manage by Captivise')
            return HttpResponseRedirect(return_url)       
        

        if script_id == "-1":
            campaign_ids = Campaign.objects.values_list('id', flat=True).filter(owner=user_id, client_customer_id=client_customer_id)

        campaign_unmanaged = []
        campaign_notallow = []

        if campaign_ids:
            if script_id == '0' or script_id == '-1':
                scripts = ReportScripts.objects.filter(status=True).exclude(pk__in=[12, 14])
                for script in scripts:

                    for campaign_id in campaign_ids:

                        schedule_count = ReportScriptsSchedule.objects.filter(user_id=user_id, script_id=script.id, campaign_id=campaign_id, status=0).count()

                        if schedule_count > 0:
                            schedule_exist = True
                        
                        campaign_obj = Campaign.objects.values_list('title', 'adwords_campaign_id', 'is_managed', 'advertising_channel_type', named=True).filter(pk=campaign_id)
                        campaign_obj = campaign_obj[0]
                        campaign_type = campaign_obj.advertising_channel_type.lower()

                        #enable_count =  ReportScriptsStatus.objects.filter(user_id=user_id, script_id=script.id, campaign_id=campaign_id, status=True).count()
                        #if enable_count < 1:
                        #    script_status = False
                        #else:
                        #    if campaign_obj.is_managed is False and campaign_obj.title not in campaign_unmanaged:
                        #        campaign_unmanaged.append(campaign_obj.title)
                        
                        if campaign_obj.is_managed is False and campaign_obj.title not in campaign_unmanaged:
                            campaign_unmanaged.append(campaign_obj.title)

                        script_cats = []
                        script_name = script.name
                        script_obj_cats = script.category_id.all()
                        for cat in script_obj_cats:
                            script_cats.append(cat.category_name.lower())                            

                        if campaign_type not in script_cats:
                            campaign_notallow.append(campaign_obj.title)

                        #if schedule_count < 1 and enable_count > 0 and campaign_type in script_cats:
                        if schedule_count < 1 and campaign_type in script_cats:                   
                            
                            if campaign_obj.is_managed == True:
                                ReportScriptsSchedule.objects.create(
                                    user_id=user_id,
                                    script_id=script.id,
                                    client_customer_id=client_customer_id,
                                    campaign_id=campaign_id,
                                    adwords_campaign_id=campaign_obj.adwords_campaign_id,
                                    scheduled_at=scheduled_at
                                )
                                scheduled = True
                                
            else:

                for campaign_id in campaign_ids:
                    
                    schedule_count = ReportScriptsSchedule.objects.filter(user_id=user_id, script_id=script_id, campaign_id=campaign_id, status=0).count()

                    #enable_count = ReportScriptsStatus.objects.filter(user_id=user_id, script_id=script_id, campaign_id=campaign_id, status=True).count()

                    campaign_obj = Campaign.objects.values_list('title', 'adwords_campaign_id', 'is_managed', 'advertising_channel_type', named=True).filter(pk=campaign_id)
                    campaign_obj = campaign_obj[0]
                    campaign_type = campaign_obj.advertising_channel_type.lower()

                    if schedule_count > 0:
                        schedule_exist = True
                    
                    #if enable_count < 1:
                    #    script_status = False
                    #else:
                    #    if campaign_obj.is_managed is False and campaign_obj.title not in campaign_unmanaged:
                    #        campaign_unmanaged.append(campaign_obj.title)

                    if campaign_obj.is_managed is False and campaign_obj.title not in campaign_unmanaged:
                        campaign_unmanaged.append(campaign_obj.title)

                    script_cats = []
                    script_obj = ReportScripts.objects.get(pk=script_id)
                    script_name = script_obj.name
                    script_obj_cats = script_obj.category_id.all()
                    for cat in script_obj_cats:
                        script_cats.append(cat.category_name.lower())
                        

                    if campaign_type not in script_cats:
                        campaign_notallow.append(campaign_obj.title)                       
                    

                    #if schedule_count < 1 and enable_count > 0 and campaign_type in script_cats:
                    if schedule_count < 1 and campaign_type in script_cats:
                        
                        if campaign_obj.is_managed == True:
                            ReportScriptsSchedule.objects.create(
                                user_id=user_id,
                                script_id=script_id,
                                client_customer_id=client_customer_id,
                                campaign_id=campaign_id,
                                adwords_campaign_id=campaign_obj.adwords_campaign_id,
                                scheduled_at=scheduled_at
                            )
                            scheduled = True
                        

        if schedule_exist == True:
            messages.error(request, 'Some automated tasks scheduled already. Unable to schedule again.')           

        if scheduled == True:
            messages.success(request, 'Automated tasks scheduled successfully.')

        #if script_status == False:
        #    messages.error(request, 'Enable automated tasks to schedule.')
        
        if len(campaign_unmanaged) > 0:
            joined_string = ", ".join(campaign_unmanaged)
            messages.error(request, 'Automated task can not be run on unmanaged campaigns ({campaign_count}) ({joined_string}). Please update campaign settings allow to manage by Captivise'.format(joined_string=joined_string, campaign_count=len(campaign_unmanaged)))

        if len(campaign_notallow) > 0:
            joined_string = ", ".join(campaign_notallow)
            messages.error(request, '{script_name} automated task not allowed to run on campaign type ({campaign_type}) ({joined_string}).'.format(script_name=script_name, campaign_type=campaign_type, joined_string=joined_string))

        return HttpResponseRedirect(return_url)

class CampaignReportScriptsDisableView(BaseCampaignDetailView):

    def post(self, request, *args, **kwargs):

        campaign_ids = self.request.POST.getlist('campaign_id[]')
        script_id = self.request.POST.get('script_id')
        user_id = self.request.user.id
        client_customer_id = self.request.user.client_customer_id
        if script_id == "-1":
            campaign_ids = Campaign.objects.values_list('id', flat=True).filter(owner=user_id, client_customer_id=client_customer_id)      

        if campaign_ids:
            if script_id == '0' or script_id == "-1":
                scripts = ReportScripts.objects.filter(status=True).exclude(pk__in=[12, 14])
                for script in scripts:

                    for campaign_id in campaign_ids:                
                        script_statuses = ReportScriptsStatus.objects.filter(user_id=user_id, script_id=script.id, campaign_id=campaign_id)
                        if script_statuses.exists():
                            for script_status in script_statuses:
                                script_status.status = False
                                script_status.save()
                        else:
                            ReportScriptsStatus.objects.create(
                                user_id=user_id,
                                script_id=script.id,
                                campaign_id=campaign_id,
                                status=False
                            )
                            
            else:
                for campaign_id in campaign_ids:                    
                    script_statuses = ReportScriptsStatus.objects.filter(user_id=user_id, script_id=script_id, campaign_id=campaign_id)
                    if script_statuses.exists():
                        for script_status in script_statuses:
                            script_status.status = False
                            script_status.save()
                    else:
                        ReportScriptsStatus.objects.create(
                            user_id=user_id,
                            script_id=script.id,
                            campaign_id=campaign_id,
                            status=False
                        )                   
        messages.success(request, 'Automated tasks disabled successfully.')

        return_url = build_url('reports_campaign_list', params=make_url(self, request))

        return HttpResponseRedirect(return_url)


class CampaignReportScriptsEnableView(BaseCampaignDetailView):

    def post(self, request, *args, **kwargs):

        campaign_ids = self.request.POST.getlist('campaign_id[]')
        script_id = self.request.POST.get('script_id')
        user_id = self.request.user.id
        client_customer_id = self.request.user.client_customer_id
        scheduled = False  
            
        return_url = build_url('reports_campaign_list', params=make_url(self, request))

        check_managed = Campaign.objects.values_list('id', flat=True).filter(owner=user_id, is_managed=True, client_customer_id=client_customer_id)
        if len(check_managed) < 1:
            messages.error(request, 'Automated task can not be run on unmanaged campaigns. Please update campaign settings allow to manage by Captivise')
            return HttpResponseRedirect(return_url)        

        if script_id == "-1":
            campaign_ids = Campaign.objects.values_list('id', flat=True).filter(owner=user_id, client_customer_id=client_customer_id)       

        if campaign_ids:
            if script_id == '0' or script_id == '-1':
                scripts = ReportScripts.objects.filter(status=True).exclude(pk__in=[12, 14])
                campaign_unmanaged = []
                for script in scripts:

                    for campaign_id in campaign_ids:
                        campaign_obj = Campaign.objects.values_list('title', 'is_managed', named=True).filter(pk=campaign_id)
                        campaign_obj = campaign_obj[0]
                        if campaign_obj.is_managed is True:

                            script_statuses = ReportScriptsStatus.objects.filter(user_id=user_id, script_id=script.id, campaign_id=campaign_id)                        
                            if script_statuses.exists():
                                for script_status in script_statuses:
                                    script_status.status = True
                                    script_status.save()
                            else:
                                ReportScriptsStatus.objects.create(
                                    user_id=user_id,
                                    script_id=script.id,
                                    campaign_id=campaign_id,
                                    status=True
                                )
                        else:
                            if campaign_obj.is_managed is False and campaign_obj.title not in campaign_unmanaged:
                                campaign_unmanaged.append(campaign_obj.title)
            else:
                campaign_unmanaged = []
                for campaign_id in campaign_ids:

                    campaign_obj = Campaign.objects.values_list('title', 'is_managed', named=True).filter(pk=campaign_id)
                    campaign_obj = campaign_obj[0]
                    if campaign_obj.is_managed is True:
                    
                        script_statuses = ReportScriptsStatus.objects.filter(user_id=user_id, script_id=script_id, campaign_id=campaign_id)
                        if script_statuses.exists():
                            for script_status in script_statuses:
                                script_status.status = True
                                script_status.save()
                        else:                         
                            ReportScriptsStatus.objects.create(
                                user_id=user_id,
                                script_id=script_id,
                                campaign_id=campaign_id,
                                status=True
                            )
                        scheduled = True
                    else:
                        if campaign_obj.is_managed is False and campaign_obj.title not in campaign_unmanaged:
                            campaign_unmanaged.append(campaign_obj.title)

            if len(campaign_unmanaged) > 0:
                joined_string = ", ".join(campaign_unmanaged)
                messages.error(request, 'Automated task can not be run on unmanaged campaigns ({campaign_count}) ({joined_string}). Please update campaign settings allow to manage by Captivise'.format(joined_string=joined_string, campaign_count=len(campaign_unmanaged)))
        
        if scheduled is True:
            messages.success(request, 'Automated tasks enabled successfully.')

        return HttpResponseRedirect(return_url)


class CampaignReportScriptsStatusView(TemplateView):

    def post(self, request, *args, **kwargs):

        campaign_id = self.request.POST.get('campaign_id')
        user_id = self.request.user.id 
        scripts = ReportScripts.objects.filter(status=True).exclude(pk__in=[12, 14])
        
        json_data = []          
        for script in scripts:
            status = 'Disabled'
            results = ReportScriptsStatus.objects.filter(user_id=user_id, script_id=script.id, campaign_id=campaign_id)
            if results.exists():
                for result in results:
                    status = 'Disabled' if result.status == 0 else 'Enabled'                   

            json_data.append({
                'script_name': script.name,
                'status': status
            })

        campaign_info = Campaign.objects.get(pk=campaign_id)
        campaign_name = campaign_info.title
        output = {}
        output['result'] = json_data
        output['campaign_name'] = campaign_name

        return JsonResponse(output, safe=False)

class CampaignReportScriptsCategoryView(TemplateView):

    def post(self, request, *args, **kwargs):

        category_id = self.request.POST.get('category_id')
        if category_id == "0":
          scripts = ReportScripts.objects.filter(status=True).exclude(pk__in=[12, 14])
        else:
          scripts = ReportScripts.objects.filter(category_id=category_id, status=True).exclude(pk__in=[12, 14])
        
        json_data = []          
        for script in scripts:

            #results = ReportScriptsStatus.objects.filter(category_id=category_id)
            json_data.append({
                'script_name': script.name,
                'script_id': script.id
            })


        output = {}
        output['result'] = json_data

        return JsonResponse(output, safe=False)
#01/12/20
class CmsContentView(
    ActiveMenuItemMixin,
    LoginRequiredMixin,
    PaidAccountRequiredMixin,
    TemplateView):
    model = CmsContent

    def get_active_menu(self):
        return {
            'information': True,
        }

    template_name = 'website/show_cms_content.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if not self.request.user.has_adwords_account:
            return context

        context['has_adwords_account'] = True

        cms_id = int(self.kwargs['cms_id'])
        cms_content = CmsContent.objects.filter(id=cms_id)
        context.update({
            'cms_ct': cms_content
        })

        return context


def build_url(*args, **kwargs):
    params = kwargs.pop('params', {})
    url = reverse(*args, **kwargs)
    if not params: return url

    qdict = QueryDict('', mutable=True)
    for k, v in params.items():
        if type(v) is list: qdict.setlist(k, v)
        else: qdict[k] = v

    return url + '?' + qdict.urlencode()

def make_url(self, request):

    status = self.request.POST.get('status', None)
    name = self.request.POST.get('name', None)
    campaign_type = self.request.POST.get('campaign_type', None)
    active_menu = self.request.POST.get('active_menu', None)
    order_by = self.request.POST.get('sort', None)
    page = self.request.POST.get('page', None)

    params = {}
    if name:
        params['name'] = name
    if campaign_type:
        params['campaign_type'] = campaign_type
    if status:
        params['status'] = status
    if active_menu:
        params['filter'] = active_menu
    if order_by:
        params['sort'] = order_by
    if page:
        params['page'] = page

    if status or name or campaign_type :
        params['search'] = 'Apply Filter'
    
    return params
