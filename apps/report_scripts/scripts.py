# TODO:  Loading services in serial has poor performance, especially
# when doing it more than once.  Can we cache them globally somehow?
# They won't change per user without the server resetting, so
# repeatedly loading the endpoint info is wasteful.

from collections import defaultdict, namedtuple
import csv
import datetime
import logging
from decimal import Decimal
from functools import wraps
from urllib.error import HTTPError
from xml.etree import ElementTree
from django.core.mail import send_mail

from django.conf import settings
from django.db import connection
from django.db.utils import OperationalError

from campaign_modifiers.models import KeywordEvent
from reports.models import Campaign
from reports.utils import decimal_to_micro_amount, micro_amount_to_decimal
from website.utils import get_adwords_client
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

from .exceptions import NonManagerAccountSelected, UserNotLinkedError
import json
import re
import os
import decimal
import hashlib
from campaign_modifiers.models import ModifierProcessLog, KeywordActionLog
from constance import config
import locale
from .products import GoogleMerchantConnect

locale.setlocale(locale.LC_ALL, 'en_GB.utf8')


ALL_TIME = 'ALL_TIME'

BUDGETS_ALL = 'BUDGETS_ALL'

CAMPAIGNS_ALL = 'CAMPAIGNS_ALL'
CAMPAIGNS_MANAGED = 'CAMPAIGNS_MANAGED'
CAMPAIGNS_UNMANAGED = 'CAMPAIGNS_UNMANAGED'

logger = logging.getLogger('adwords.adapter')

def _require_linked_account(func):
    @wraps(func)
    def inner(self, *args, **kwargs):
        if not self._user.has_adwords_account:
            raise UserNotLinkedError('Currently logged in user has no linked AdWords account')

        return func(self, *args, **kwargs)
    return inner


def _get_error_from_xml(xml, version):
    namespace = {
        'envelope': 'http://schemas.xmlsoap.org/soap/envelope/',
        'mcm': 'https://adwords.google.com/api/adwords/mcm/{version}'.format(version=version),
        'cm': 'https://adwords.google.com/api/adwords/cm/{version}'.format(version=version),
    }

    # Descend through the XML.
    body = xml.find('envelope:Body', namespace)
    fault = body.find('envelope:Fault', namespace)
    detail = fault.find('detail')
    api_exception_fault = detail.find('mcm:ApiExceptionFault', namespace)
    errors = api_exception_fault.find('cm:errors', namespace)

    # Get the elements we actually want.
    api_error_type = errors.find('cm:ApiError.Type', namespace)
    reason = errors.find('cm:reason', namespace)

    error = namedtuple('error', ('api_error_type', 'reason'))
    return error(api_error_type.text, reason.text)


class ScriptAdapter:
    adwords_api_version = 'v201809'

    def __init__(self, user):
        self._user = user
        self._cached_values = {}
        self.is_dry_run = user.is_adwords_dry_run

    @property
    def should_mutate(self):
        return True
        if settings.SHOULD_MUTATE_GOOGLE_ADS:
            if not self.is_dry_run:
                return True

        return False

    @staticmethod
    def format_filters(filters, single=False):
        OPERATORS = {
            # Map google predicate operators to django-like ones.
            'eq': 'EQUALS',
            'ne': 'NOT_EQUALS',
            'in': 'IN',
            'not_in': 'NOT_IN',
            'gt': 'GREATER_THAN',
            'gte': 'GREATER_THAN_EQUALS',
            'lt': 'LESS_THAN',
            'lte': 'LESS_THAN_EQUALS',
            'startswith': 'STARTS_WITH',
            'istartswith': 'STARTS_WITH_IGNORE_CASE',
            'contains': 'CONTAINS',
            'icontains': 'CONTAINS_IGNORE_CASE',
            'not_contains': 'DOES_NOT_CONTAIN',
            'not_icontains': 'DOES_NOT_CONTAIN_IGNORE_CASE',
            'contains_list': 'CONTAINS_ANY',
            'contains_list_all': 'CONTAINS_ALL',
            'not_contains_list': 'CONTAINS_NONE',
            'unknown': 'UNKNOWN',
        }

        formatted_filters = []

        if filters is None:
            return formatted_filters

        for field, value in filters.items():
            field, *operator = field.split('__')
            if operator:
                operator = OPERATORS[operator[-1]]
            else:
                operator = OPERATORS['eq']

            if single:
                formatted_filter = {
                    'field': field,
                    'operator': operator,
                    'values': value,
                }
            else:
                formatted_filter = {
                    'field': field,
                    'operator': operator,
                    'values': [value],
                }
            formatted_filters.append(formatted_filter)

        return formatted_filters

    @staticmethod
    def format_date_range(date_from, date_to):
        return {
            'min': date_from.strftime('%Y%m%d'),
            'max': date_to.strftime('%Y%m%d'),
        }

    def get_conversion_trackers(self):
        adwords_service = self.get_adwords_service('ConversionTrackerService')
        selector = {
            'fields': ['Status'],
            'predicates': self.format_filters({'Status__eq': 'ENABLED'}),
        }

        try:
            self._cached_values['conversion_trackers'] = adwords_service.get(selector).entries
        except AttributeError:
            self._cached_values['conversion_trackers'] = []

        return self._cached_values['conversion_trackers']

    def get_adwords_service(self, service_name):
        adwords_client = self.get_adwords_client()

        return adwords_client.GetService(service_name, version=self.adwords_api_version)

    def get_report_downloader(self):
        report_downloader = self.get_adwords_client()

        return report_downloader.GetReportDownloader(version=self.adwords_api_version)

    def get_report(
            self,
            name,
            report_type,
            date_range_type,
            selector,
            skip_headers=True,
            include_zero_impressions=True):
        parameters = {
            'reportName': name,
            'reportType': report_type,
            'dateRangeType': date_range_type,
            'downloadFormat': 'CSV',
            'selector': selector,
        }
        report_downloader = self.get_report_downloader()
        response = report_downloader.DownloadReportAsStream(
            parameters,
            skip_report_header=True,
            skip_report_summary=True,
          #  include_zero_impressions=include_zero_impressions
        )


        report = csv.reader((line.decode() for line in response))        
        
        if skip_headers:
            next(report)

        reports = list(report)
        return reports

        return (row for row in report if row)

    @classmethod
    def get_customers(cls, refresh_token):
        # Will be called outside of a view with no reasonable access to
        # a `User` instance.  Provide a `refresh_token` manually.
        client = get_adwords_client(refresh_token)
        customer_service = client.GetService('CustomerService')
        try:
            customers = customer_service.getCustomers()
        except HTTPError as e:
            if not hasattr(e, 'fp'):
                raise

            data = e.fp.read()
            xml = ElementTree.fromstring(data)
            error = _get_error_from_xml(xml, cls.adwords_api_version)
            if error.api_error_type == 'AuthenticationError' and error.reason == 'NOT_ADS_USER':
                logger.debug(datetime.datetime.now().strftime("%I:%M%p on %B %d, %Y") + "- NonManagerAccountSelected - NOT_ADS_USER - adapter.py line 207")
                raise NonManagerAccountSelected
            else:
                raise

        try:
            managed_customers = []
            for customer in customers:
                customer_id = customer.customerId

                # Get a new client with all the data we need.
                client = get_adwords_client(refresh_token, customer_id)
                managed_customer_service = client.GetService('ManagedCustomerService')
                selector = {
                    'fields': [
                        'CustomerId',
                        'Name',
                        'CanManageClients',
                    ],
                    # No pagination; we will always want all customers.
                }
                try:
                    managed_customers.extend(managed_customer_service.get(selector).entries)
                except:
                    pass
        except:
            logger.debug(datetime.datetime.now().strftime("%I:%M%p on %B %d, %Y") + "- NonManagerAccountSelected - adapter.py line 231")
            raise NonManagerAccountSelected

        return managed_customers

    def get_customer(refresh_token):
        # Will be called outside of a view with no reasonable access to
        # a `User` instance.  Provide a `refresh_token` manually.       
        # CustomerService.get() method no longer exists, 
        # getting list of customers and checking if there's only one.
        # This method should only be run in the event of a failure to get a manager account.
        client = get_adwords_client(refresh_token)
        customer_service = client.GetService('CustomerService')
        try:
            customers = customer_service.getCustomers()
            if len(customers) == 1:
                for customer in customers:
                    return customer
            else:
                logger.debug(datetime.datetime.now().strftime("%I:%M%p on %B %d, %Y") + "- NonManagerAccountSelected - adapter.py line 250")
                raise NonManagerAccountSelected
        except:
            logger.debug(datetime.datetime.now().strftime("%I:%M%p on %B %d, %Y") + "- NonManagerAccountSelected - adapter.py line 253")
            raise NonManagerAccountSelected

        return customer

    @_require_linked_account
    def get_adwords_client(self):
        print("%s : : %s" %(self._user.refresh_token, self._user.client_customer_id))
        return get_adwords_client(self._user.refresh_token, self._user.client_customer_id)

    def _get_campaign_instance(self, campaign):
        campaign = campaign.copy()
        adwords_campaign_id = campaign.pop('id')
        title = campaign.pop('title')
        instance, _ = Campaign.objects.update_or_create(
            adwords_campaign_id=adwords_campaign_id,
            defaults={'owner': self._user, 'title': title},
        )

        for key, value in campaign.items():
            # Set attributes on the campaign for the leftover keys; the
            # API-only data.
            setattr(instance, key, value)

        return instance

    def _inject_campaign_predicates(self, selector, campaigns_to_get):
        """
        Mutate `selector` to include predicates for filtering campaigns
        based on their management status.  Returns whether the input
        has been mutated or not as a boolean, or if more a complicated
        response is needed, a string:

            * 'SHOW_NONE' - The filter would be 'in []', so the caller
            should short-circuit the API and return its zero-result
            response.
            * 'SHOW_ALL' - The filter would be 'not in []', so the
            caller should do no further filtering.
        """
        adwords_campaign_ids = Campaign.objects.filter(owner=self._user, is_managed=True) \
            .values_list('adwords_campaign_id', flat=True)
        adwords_campaign_ids = list(adwords_campaign_ids)

        if campaigns_to_get == CAMPAIGNS_MANAGED:
            if not adwords_campaign_ids:
                return 'SHOW_NONE'

            operator = 'in'

        elif campaigns_to_get == CAMPAIGNS_UNMANAGED:
            if not adwords_campaign_ids:
                return 'SHOW_ALL'

            operator = 'not_in'

        else:
            return False  # We don't understand `campaigns_to_show`

        predicates = self.format_filters({'BaseCampaignId__' + operator: adwords_campaign_ids})

        selector['predicates'] = selector.get('predicates', [])
        selector['predicates'].extend(predicates)

        return True

    @_require_linked_account
    def get_budgets(self, budgets_to_get_ids=BUDGETS_ALL, date_range=ALL_TIME):
        budget_selector = {
            'fields': [
                'BudgetId',
                'Amount',
                'BudgetName',
            ],
        }

        if budgets_to_get_ids != BUDGETS_ALL:
            budget_selector['predicates'] = self.format_filters({
                'BudgetId__in': list(budgets_to_get_ids),
            }, single=True)

        if date_range != ALL_TIME:
            budget_selector['dateRange'] = date_range
            date_range = 'CUSTOM_DATE'
        
        report = self.get_report(
            'Budgets report',
            'BUDGET_PERFORMANCE_REPORT',
            date_range,
            budget_selector,
        )

        return (
            {'id': int(id_), 'amount': int(amount), 'name': name}
            for id_, amount, name in report
        )

    @_require_linked_account
    def get_spend_for_period(self, date_from, date_to):
        """
        Data is only available up to the previous day, from 3AM the
        following day.
        """
        selector = {
            'fields': [
                'Cost',
            ],
            'dateRange': self.format_date_range(date_from, date_to)
        }
        (spend,), = self.get_report(
            'Account Report',
            'ACCOUNT_PERFORMANCE_REPORT',
            'CUSTOM_DATE',
            selector,
        )
        return int(spend)

    @_require_linked_account
    def get_monthly_spend(self):
        date_to = datetime.datetime.now()
        date_from = date_to - datetime.timedelta(days=30)
        try:
            spend = self.get_spend_for_period(date_from, date_to)
        except:
            print("Error Occured!")
            spend = 0
        return spend

    @_require_linked_account
    def get_campaigns(self, campaigns_to_get=CAMPAIGNS_ALL, date_range=ALL_TIME, get_budgets=True):
        campaign_selector = {
            'fields': [
                'BaseCampaignId',
                'CampaignName',
                'CampaignStatus',
                'BudgetId',
                'ClickAssistedConversions',
            ],
        }

        if campaigns_to_get != CAMPAIGNS_ALL:
            mutation_result = self._inject_campaign_predicates(campaign_selector, campaigns_to_get)
            if mutation_result == 'SHOW_NONE':
                return []
            elif not mutation_result:
                # Treat as a list of raw id values.
                campaign_selector['predicates'] = self.format_filters({
                    'BaseCampaignId__in': campaigns_to_get,
                })

        if date_range != ALL_TIME:
            campaign_selector['dateRange'] = date_range
            date_range = 'CUSTOM_DATE'

        report = self.get_report(
            'Campaigns report',
            'CAMPAIGN_PERFORMANCE_REPORT',
            date_range,
            campaign_selector,
        )

        campaigns = [
            {
                'id': int(id_),
                'title': title,
                'status': status,
                'budget_id': int(budget_id),
                'click_assisted_conversions': int(click_assisted_conversions)
            }
            for (
                id_,
                title,
                status,
                budget_id,
                click_assisted_conversions,
            ) in report
        ]

        if get_budgets and campaigns:
            # Add the budget amounts in.
            budget_ids = (campaign['budget_id'] for campaign in campaigns)
            budgets = self.get_budgets(budget_ids)

            for budget in budgets:
                campaigns_to_mutate = [
                    campaign for campaign in campaigns
                    if campaign['budget_id'] == budget['id']
                ]

                for campaign in campaigns_to_mutate:
                    campaign['budget'] = budget['amount']
                    campaign['budget_name'] = budget['name']

            # TODO:  If the API returns no budgets for an ID that a
            # campaign has, at this point, the campaign will be missing the
            # `'budget'` key.  Is this a possibility on the API side?

        return campaigns

    def get_mapped_campaigns(self, filter_by=None):
        campaigns_to_show = CAMPAIGNS_ALL
        if isinstance(filter_by, str):
            filter_by = filter_by.lower()
            if filter_by == 'managed':
                campaigns_to_show = CAMPAIGNS_MANAGED
            elif filter_by == 'unmanaged':
                campaigns_to_show = CAMPAIGNS_UNMANAGED

        data = self.get_campaigns(campaigns_to_show)

        return [
            self._get_campaign_instance(campaign)
            for campaign
            in data
        ]

    @staticmethod
    def get_metrics_shape(metrics):
        if hasattr(metrics, 'values') and callable(metrics.values):
            metrics = list(metrics.values())

        if not metrics:
            return {}

        keys = metrics[0].keys()

        return {key: 0 for key in keys}

    @classmethod
    def _aggregate_metrics(cls, metrics, average_columns=()):
        initial = cls.get_metrics_shape(metrics)
        divisor = len(metrics)

        for metric in metrics:
            for key, value in metric.items():
                if key in average_columns:
                    value /= divisor

                initial[key] += value

        return initial

    @classmethod
    def aggregate_metrics_to_monthly(cls, metrics, date_format=datetime.date, average_columns=()):
        cast_dates = True
        if type(date_format) is type and issubclass(date_format, datetime.date):
            cast_dates = False

        categorised = defaultdict(list)
        for date, metric in metrics.items():
            if cast_dates:
                date = datetime.datetime.strptime(date, date_format).date()

            first_of_the_month = datetime.date(date.year, date.month, 1)
            categorised[first_of_the_month].append(metric)

        if cast_dates:
            return {
                month.strftime(date_format): cls._aggregate_metrics(
                    metrics, average_columns=average_columns)
                for month, metrics in categorised.items()
            }
        else:
            return {
                month: cls._aggregate_metrics(metrics, average_columns=average_columns)
                for month, metrics in categorised.items()
            }

    @classmethod
    def aggregate_campaign_metrics_to_monthly(cls, metrics, date_format=datetime.date):
        return cls.aggregate_metrics_to_monthly(
            metrics,
            date_format=date_format,
            average_columns=('cpc', ),
        )

    def get_campaign_metrics(
            self,
            date_range=ALL_TIME,
            campaign_id=CAMPAIGNS_ALL,
            cast_dates=True):
        campaign_selector = {
            'fields': [
                'Conversions',
                'Date',
                'Cost',
            ],
        }

        if date_range != ALL_TIME:
            campaign_selector['dateRange'] = date_range
            date_range = 'CUSTOM_DATE'

        if campaign_id != CAMPAIGNS_ALL:
            campaign_selector['predicates'] = self.format_filters({'BaseCampaignId': campaign_id})

        report = self.get_report(
            'Campaign report',
            'CAMPAIGN_PERFORMANCE_REPORT',
            date_range,
            campaign_selector,
        )

        by_date = defaultdict(
            lambda: {'conversions': Decimal(), 'cpc': Decimal(), 'cost': Decimal()})
        for click_assisted_conversions, date, cost in report:
            if cast_dates:
                date = datetime.datetime.strptime(date, '%Y-%m-%d').date()
            by_date[date]['conversions'] += Decimal(click_assisted_conversions)
            by_date[date]['cost'] += int(cost)
            if by_date[date]['conversions']:
                by_date[date]['cpc'] = by_date[date]['cost'] / by_date[date]['conversions']

        return by_date

    def get_keywords(
            self,
            predicates=None,
            enabled_only=False,
            date_range=ALL_TIME):
        if enabled_only:
            filters = {'Status':'ENABLED'}

        keyword_selector = {
            'fields': [
                'BaseCampaignId',
                'AdGroupName',
                'AdGroupId',
                'Id',
                'Criteria',
                'AveragePosition',
                'Clicks',
                'CpcBid',
                'ClickAssistedConversions',
                'ConversionRate',
                'Cost',
                'Impressions',
                'Ctr',
                'CostPerConversion',
                'Status',
                'ValuePerConversion',
            ],
        }
        predicates = {'Conversions__lt': '1','Status':'ENABLED'}

        if predicates is not None:
            keyword_selector['predicates'] = self.format_filters(predicates, single=True)

        if date_range != ALL_TIME:
            keyword_selector['dateRange'] = date_range
            date_range = 'CUSTOM_DATE'
        
        report = self.get_report(
            'Keywords report',
            'KEYWORDS_PERFORMANCE_REPORT',
            date_range,
            keyword_selector,
        )

        def percentage(value):
            return Decimal(value[:-1])  # Cut off the '%'.

        def cast(value, to_type):
            try:
                return to_type(value)
            except Exception:
                return None

        return (
            {
                'campaign_id': int(campaign_id),
                'ad_group_name': ad_group_name,
                'ad_group_id': int(ad_group_id),
                'id': int(id_),
                'keyword': keyword,
                'average_position': average_position,
                'clicks': int(clicks),
                'max_cpc': cast(max_cpc, int),
                'click_assisted_conversions': int(click_assisted_conversions),
                'conversion_rate': percentage(conversion_rate),
                'cost': int(cost),
                'impressions': int(impressions),
                'click_through_rate': percentage(click_through_rate),
                'cpa': int(cpa),
                'status': status,
                'value_per_conversion': decimal_to_micro_amount(
                    cast(value_per_conversion, Decimal)),
            }
            for (
                campaign_id,
                ad_group_name,
                ad_group_id,
                id_,
                keyword,
                average_position,
                clicks,
                max_cpc,
                click_assisted_conversions,
                conversion_rate,
                cost,
                impressions,
                click_through_rate,
                cpa,
                status,
                value_per_conversion,
            ) in report
        )

    def get_keywords_for_campaign(
            self,
            adwords_campaign_id,
            enabled_only=False,
            date_range=ALL_TIME):
        return self.get_keywords({'BaseCampaignId': adwords_campaign_id}, enabled_only, date_range)

    def get_mapped_keywords(self, campaign):
        data = self.get_keywords_for_campaign(campaign.adwords_campaign_id)
        # We'll iterate over the data twice for database query reasons,
        # so evaluate it.
        data = list(data)

        # Avoid hitting the database for every keyword.
        keyword_ids = [keyword['id'] for keyword in data]
        # `DISTINCT ON` doesn't exist in MySQL, so replace
        # `.order_by('-created_at').distinct('adwords_keyword_id')`
        if keyword_ids:
            with connection.cursor() as cursor:
                query = (
                    'SELECT MAX(created_at), {{id_col}} '
                    'FROM {table} '
                    'WHERE adwords_keyword_id IN %s '
                    'GROUP BY adwords_keyword_id').format(table=KeywordEvent._meta.db_table)
                try:
                    cursor.execute(query.format(id_col='ANY_VALUE(id)'), (keyword_ids,))
                except OperationalError:  # MySQL < v5.7
                    cursor.execute(query.format(id_col='id'), (keyword_ids,))

                rows = cursor.fetchall()
                ids = [id_ for _created_at, id_ in rows]
        else:
            ids = keyword_ids

        keyword_events = KeywordEvent.objects.filter(pk__in=ids)
        list(keyword_events)

        keywords = []
        for keyword in data:
            keyword = keyword.copy()

            try:
                previous_max_cpc = keyword_events.get(adwords_keyword_id=keyword['id'])
            except KeywordEvent.DoesNotExist:
                keyword['previous_max_cpc'] = None
                keyword['max_cpc_modified_at'] = None
            else:  # noexcept
                keyword['previous_max_cpc'] = previous_max_cpc.previous_max_cpc
                keyword['max_cpc_modified_at'] = previous_max_cpc.created_at

            keywords.append(keyword)

        return keywords

    def get_adgroups_for_campaign(self, adwords_campaign_id):
        filters = {'BaseCampaignId': adwords_campaign_id, 'AdGroupStatus': 'ENABLED'}
        adgroups_selector = {
            'fields': [
                'AdGroupId',
            ],
            'predicates': self.format_filters(filters)
        }

        report = self.get_report(
            'Adgroups report',
            'ADGROUP_PERFORMANCE_REPORT',
            ALL_TIME,
            adgroups_selector,
        )

        return (
            {
                'id': int(id_),
            }
            for (
                id_,
            ) in report
        )

    def set_keyword_max_cpc(self, ad_group_id, keyword_id, max_cpc):
        ad_group_criterion_service = self.get_adwords_service('AdGroupCriterionService')
        operations = [{
            'operator': 'SET',
            'operand': {
                'xsi_type': 'BiddableAdGroupCriterion',
                'adGroupId': ad_group_id,
                'criterion': {
                    'id': keyword_id,
                },
                'biddingStrategyConfiguration': {
                    'bids': [
                        {
                            'xsi_type': 'CpcBid',
                            'bid': {
                                'microAmount': max_cpc,
                            },
                        },
                    ],
                },
            },
        }]

        if self.should_mutate:
            return ad_group_criterion_service.mutate(operations)

    def set_keyword_paused(self, ad_group_id, keyword_id):
        ad_group_criterion_service = self.get_adwords_service('AdGroupCriterionService')
        operations = [{
            'operator': 'SET',
            'operand': {
                'xsi_type': 'BiddableAdGroupCriterion',
                'adGroupId': ad_group_id,
                'criterion': {
                    'id': keyword_id,
                },
                'userStatus': 'PAUSED',
            },
        }]

        if self.should_mutate:
            return ad_group_criterion_service.mutate(operations)

    def set_ad_groups_paused(self, ad_group_ids):
        ad_group_service = self.get_adwords_service('AdGroupService')
        operations = [{
            'operator': 'SET',
            'operand': {
                'id': ad_group_id,
                'status': 'PAUSED',
            }
        } for ad_group_id in set(ad_group_ids)]

        if self.should_mutate:
            return ad_group_service.mutate(operations)

    #Pause Empty Adgroups
    def pause_empty_adgroups(self, script_schedule, campaign_obj):

        schedule_id = script_schedule.id
        script_id = script_schedule.script_id
        campaign_id = script_schedule.campaign_id
        adwords_campaign_id = script_schedule.adwords_campaign_id        

        ad_group_service = self.get_adwords_service('AdGroupService')

        offset = 0
        page_size = 1000
        keyword_offset = 0
        keyword_page_size = 1
        total_records = 0

        # Let's start by getting all of the active AdGroups
        selector = {
            'fields': ['Id', 'Name', 'Status'],
            'predicates': [
                {
                    'field': 'CampaignId',
                    'operator': 'EQUALS',
                    'values': [adwords_campaign_id]
                },
                {
                    'field': 'CampaignStatus',
                    'operator': 'EQUALS',
                    'values': ['ENABLED']
                },
                {
                    'field': 'Status',
                    'operator': 'EQUALS',
                    'values': ['ENABLED']
                },
            ],
            'paging': {
                'startIndex': str(offset),
                'numberResults': str(page_size)
            }
        }
        more_pages = True
        while more_pages:
            page = ad_group_service.get(selector)

            # Display results.
            if 'entries' in page:
                for ad_group in page['entries']:                    
                    
                    # check at least 1 keyword in the AdGroup

                    ad_group_criterion_service = self.get_adwords_service('AdGroupCriterionService')                    
                    adgroup_id = ad_group['id']
                    keyword_selector = {
                        'fields': ['Id', 'CriteriaType', 'KeywordMatchType', 'KeywordText'],
                        'predicates': [
                            {
                                'field': 'AdGroupId',
                                'operator': 'EQUALS',
                                'values': [adgroup_id]
                            },
                            {
                                'field': 'CriteriaType',
                                'operator': 'EQUALS',
                                'values': ['KEYWORD']
                            },
                            {
                                'field': 'Status',
                                'operator': 'EQUALS',
                                'values': ['ENABLED']
                            },
                            
                        ],
                        'paging': {
                            'startIndex': str(keyword_offset),
                            'numberResults': str(keyword_page_size)
                        },
                        'ordering': [{'field': 'KeywordText', 'sortOrder': 'ASCENDING'}]
                    }

                    keyword_found = False
                    keyword_page = ad_group_criterion_service.get(keyword_selector)
                    if 'entries' in keyword_page and len(keyword_page['entries']) > 0:
                        keyword_found = True                        

                    if keyword_found == False:                        
                        ad_group_ids = {ad_group['id'],}
                        self.set_ad_groups_paused(ad_group_ids)

                        if total_records == 0:
                            report_result = ReportScriptsResult.objects.create(
                                schedule=script_schedule,
                                user_id=self._user.id,
                                script_id=script_id,
                                client_customer_id=self._user.client_customer_id,
                                campaign_id=campaign_id,
                                adwords_campaign_id=adwords_campaign_id,
                                total_records=total_records,
                            )

                        ReportScriptsResultAdgroup.objects.create(
                            result=report_result,
                            ad_group_name=ad_group['name'],
                        )
                        
                        total_records +=1                                             

            offset += page_size
            selector['paging']['startIndex'] = str(offset)
            more_pages = offset < int(page['totalNumEntries'])

            if total_records > 0:
                ReportScriptsResult.objects.filter(pk=report_result.id).update(total_records=total_records)

        return {
            'total_records': total_records,
        }

    # Pause Zero Conversions Keywords

    def pause_zero_conversion_keywords(self, script_schedule, campaign_obj):

        schedule_id = script_schedule.id
        script_id = script_schedule.script_id
        campaign_id = script_schedule.campaign_id
        adwords_campaign_id = script_schedule.adwords_campaign_id 

        conversion_types = [campaign_obj.CONVERSION_TYPE_CPA, campaign_obj.CONVERSION_TYPE_MARGIN]
        if campaign_obj.conversion_type not in conversion_types:
            return False
        
        #Pauses keywords at cost 3x tcpa and 0 conversions
        script_obj = ReportScripts.objects.get(pk=script_id)        
        effect_label_name = 'Paused by zc'
        effect_label_id = self.get_label_id(effect_label_name)
        total_records = 0

        if campaign_obj.conversion_type == campaign_obj.CONVERSION_TYPE_CPA:
            target_cpa = campaign_obj.target_cpa
            cost_check = int(target_cpa * 3)  

        if campaign_obj.conversion_type == campaign_obj.CONVERSION_TYPE_MARGIN:
            target_conversion_margin = campaign_obj.target_conversion_margin

            date_range = ALL_TIME         

            predicates = {
                'BaseCampaignId': adwords_campaign_id,
                'Status':'ENABLED'
            }            

            keyword_selector = {
                'fields': [
                    'CostPerConversion',
                ],
            }

            if predicates is not None:
                keyword_selector['predicates'] = self.format_filters(predicates, single=True)        
        
            report = self.get_report(
                'Keywords report',
                'KEYWORDS_PERFORMANCE_REPORT',
                date_range,
                keyword_selector,
            )
            average_cpa = sum(int(keyword[0]) for keyword in report) / len(report)
            cost_check = 2 * average_cpa               
        
        if cost_check > 0:   

            predicates = {
                'BaseCampaignId': adwords_campaign_id,
                'Conversions__lt': '1',
                'Status':'ENABLED',
                'Cost__gt': str(cost_check),
                'AdGroupStatus__ne': 'REMOVED'
            }

            keyword_selector = {
                'fields': [
                    'BaseCampaignId',
                    'AdGroupName',
                    'AdGroupId',
                    'Id',
                    'Criteria',
                    'Cost',
                    'Conversions',
                    'CpcBid',
                    'ConversionRate',
                    'Labels',
                ],
            }

            if predicates is not None:
                keyword_selector['predicates'] = self.format_filters(predicates, single=True)        
        
            report = self.get_report(
                'Keywords report',
                'KEYWORDS_PERFORMANCE_REPORT',
                date_range,
                keyword_selector,
            )                
            
            if len(report) > 0:               
                process_log = self.process_log_create(adwords_campaign_id, is_dry_run=False, parameters='')
                modifier_log = process_log.start_modifier_log(script_obj.name)
                
            for row in report:
                ad_group_name = row[1]
                ad_group_id = row[2]                
                keyword_id = row[3]
                keyword = row[4]
                cpc_bid = self.find_number(row[7], int)
                conversion_rate = self.percentage(row[8])
                
                
                if total_records == 0:
                    report_result = ReportScriptsResult.objects.create(
                        schedule=script_schedule,
                        user_id=self._user.id,
                        script_id=script_id,
                        client_customer_id=self._user.client_customer_id,
                        campaign_id=campaign_id,
                        adwords_campaign_id=adwords_campaign_id,
                        total_records=total_records,
                    )

                keyword_labels_str = row[9]
                keyword_labels = []
                if keyword_labels_str[0] == "[" and keyword_labels_str[-1] == "]":
                    keyword_labels = json.loads(keyword_labels_str)

                self.set_keyword_paused(ad_group_id, keyword_id)                
                
                modifier_data = {
                    'target_cpa': target_cpa,
                    'max_cpc': cpc_bid,
                }

                if modifier_log is not None:
                    modifier_log.log_paused_keyword(
                        keyword_id, cpc_bid, keyword, ad_group_name, conversion_rate, modifier_data=modifier_data,)

                total_records +=1
                if effect_label_name not in keyword_labels:
                    self.apply_keyword_label(ad_group_id, keyword_id, effect_label_id)                
            
            if total_records > 0:
                ReportScriptsResult.objects.filter(pk=report_result.id).update(total_records=total_records)           
                KeywordActionLog.objects.filter(modifier_log=modifier_log).update(result=report_result)
                if modifier_log is not None:
                    modifier_log.set_complete()                
                if process_log is not None:
                    process_log.set_complete()                  

        return {
            'total_records': total_records,
        }

    
    #Over CPA Alert - Sends an alert with keywords over cpa

    def over_cpa_alert(self, script_schedule, campaign_obj):                
               
        
        schedule_id = script_schedule.id
        script_id = script_schedule.script_id
        campaign_id = script_schedule.campaign_id
        adwords_campaign_id = script_schedule.adwords_campaign_id
        keywords = []

        if campaign_obj.conversion_type == campaign_obj.CONVERSION_TYPE_CPA:
            script_obj = ReportScripts.objects.get(pk=script_id)
            total_records = 0          
            date_range = 'LAST_30_DAYS'                  
            target_cpa = campaign_obj.target_cpa           
            predicates = {
                'BaseCampaignId': adwords_campaign_id,
                'Conversions__gt': '1',
                'Status':'ENABLED'
            }
                        
            keyword_selector = {
                'fields': [
                    'CampaignName',
                    'Criteria',
                    'Conversions',
                    'Cost',
                    'Clicks',
                    'ConversionRate',
                    'Impressions',
                ],
            }

            if predicates is not None:
                keyword_selector['predicates'] = self.format_filters(predicates, single=True)        
            
            report = self.get_report(
                'Keywords report',
                'KEYWORDS_PERFORMANCE_REPORT',
                date_range,
                keyword_selector,
            )            

            for row in report:
                campaign_name = row[0]
                keyword = row[1]
                conversions = self.cast(row[2], Decimal)
                cost = self.cast(row[3], int)
                clicks = row[4]
                conversion_rate = self.percentage(row[5])
                impressions = row[6]
                cpa = round((cost / conversions), 2) if conversions != 0 else 0
                
                if cpa > target_cpa:
                    keywords.append(keyword)
                    if total_records == 0:
                        report_result = ReportScriptsResult.objects.create(
                            schedule=script_schedule,
                            user_id=self._user.id,
                            script_id=script_id,
                            client_customer_id=self._user.client_customer_id,
                            campaign_id=campaign_id,
                            adwords_campaign_id=adwords_campaign_id,
                            total_records=total_records,
                        )

                    ReportScriptsResultOvercpa.objects.create(
                        result=report_result,
                        keyword=keyword,
                        target_cpa=target_cpa,
                        cpa=cpa,
                        cost=cost,
                        conversions=conversions,
                        clicks=clicks,
                        conversion_rate=conversion_rate,
                        impressions=impressions,
                    )

                    total_records +=1                    

            if total_records > 0:
                ReportScriptsResult.objects.filter(pk=report_result.id).update(total_records=total_records)
                message = 'Campaign name: {campaign_name} <br />The following Keywords are over TCPA:<br />{keywords}'.format(
                    keywords='<br />'.join(keywords),
                    campaign_name=campaign_name
                    )
                send_mail(
                    'Captivise - Alert: Keywords Over TCPA',
                    message,
                    settings.DEFAULT_FROM_EMAIL,
                    [self._user.email],
                    fail_silently=False,
                    html_message=message,
                )

        return {
            'total_records': total_records,
        }


    #bid adjusts keywords based on a given TCPA

    def tcpa_bids(self, script_schedule, campaign_obj, report_days):

        conversion_types = [campaign_obj.CONVERSION_TYPE_CPA, campaign_obj.CONVERSION_TYPE_MARGIN]
        if campaign_obj.conversion_type not in conversion_types:
            return False

        effect_label_name = 'Bid changed by tcpa{report_days}'.format(report_days=report_days)

        if campaign_obj.conversion_type == campaign_obj.CONVERSION_TYPE_CPA:
            target_cpa = campaign_obj.target_cpa            
        elif campaign_obj.conversion_type == campaign_obj.CONVERSION_TYPE_MARGIN:
            target_cpa = campaign_obj.target_conversion_margin
        
        schedule_id = script_schedule.id
        script_id = script_schedule.script_id
        campaign_id = script_schedule.campaign_id
        adwords_campaign_id = script_schedule.adwords_campaign_id
        max_cpc_limit = campaign_obj.max_cpc_limit

        if campaign_obj.cycle_period_days != report_days :
            Campaign.objects.filter(pk=campaign_id).update(cycle_period_days=report_days)       

        total_records = 0
        if report_days == 30:
            date_range = 'LAST_30_DAYS'
        else:
            date_range = 'CUSTOM_DATE'
            date_to = datetime.datetime.now()
            date_from = date_to - datetime.timedelta(days=report_days)        
        
        effect_label_id = self.get_label_id(effect_label_name)
        script_obj = ReportScripts.objects.get(pk=script_id)
            
        predicates = {
            'BaseCampaignId': adwords_campaign_id,
            'Conversions__gt': '2',
            'Status':'ENABLED',
            'AdGroupStatus__ne': 'REMOVED'
        }
                    
        keyword_selector = {
            'fields': [
                'CampaignName',
                'AdGroupId',
                'AdGroupName',
                'Id',
                'Criteria',
                'ConversionRate',
                'Labels',
                'ValuePerConversion',
                'CpcBid',
            ],
        }

        if predicates is not None:
            keyword_selector['predicates'] = self.format_filters(predicates, single=True)

        if date_range =='CUSTOM_DATE':
            keyword_selector['dateRange'] = self.format_date_range(date_from, date_to)
        
        report = self.get_report(
            'Keywords report',
            'KEYWORDS_PERFORMANCE_REPORT',
            date_range,
            keyword_selector,
        )       
        
        
        if len(report) > 0:
            parameters = {
                'target_cpa': target_cpa,
                'max_cpc_limit': max_cpc_limit,
                'cycle_period': report_days,
            }               
            process_log = self.process_log_create(
                adwords_campaign_id,
                is_dry_run=False,
                parameters=parameters)
            modifier_log = process_log.start_modifier_log(script_obj.name)

        for row in report:
            campaign_name = row[0]            
            ad_group_id = row[1]
            ad_group_name = row[2]
            keyword_id = row[3]
            keyword = row[4]                
            conversion_rate = self.percentage(row[5])
            keyword_labels_str = row[6]
            value_per_conversion = decimal_to_micro_amount(self.cast(row[7], Decimal))
            max_cpc = self.find_number(row[8], int)
            keyword_labels = []
            if keyword_labels_str[0] == "[" and keyword_labels_str[-1] == "]":
                keyword_labels = json.loads(keyword_labels_str)                        


            if campaign_obj.conversion_type == campaign_obj.CONVERSION_TYPE_CPA:
                target_cpa = campaign_obj.target_cpa                
                new_target_cpa = target_cpa * conversion_rate
                if isinstance(max_cpc_limit, (int, float)):
                    new_max_cpc = round(min(new_target_cpa, max_cpc_limit), -4)
            elif campaign_obj.conversion_type == campaign_obj.CONVERSION_TYPE_MARGIN:
                target_conversion_margin = campaign_obj.target_conversion_margin
                target_cpa = target_conversion_margin
                new_max_cpc = round(
                    int(min(
                        decimal.Decimal(
                            value_per_conversion * (target_conversion_margin / 100)
                        ) *
                        conversion_rate, max_cpc_limit
                    )),
                    -4,
                )            
            
            
            cpc_result = ''
            if new_max_cpc > 0:
                cpc_result = self.set_keyword_max_cpc(ad_group_id, keyword_id, new_max_cpc)

                if total_records == 0:
                    report_result = ReportScriptsResult.objects.create(
                        schedule=script_schedule,
                        user_id=self._user.id,
                        script_id=script_id,
                        client_customer_id=self._user.client_customer_id,
                        campaign_id=campaign_id,
                        adwords_campaign_id=adwords_campaign_id,
                        total_records=total_records,
                    )
                
                modifier_data = {
                    'cycle_period': report_days,
                    'target_cpa': target_cpa,
                    'max_cpc_limit': max_cpc_limit,
                    'max_cpc': max_cpc,
                    'conversion_rate': conversion_rate,
                    'new_max_cpc': new_max_cpc,
                }

                if modifier_log is not None:
                    if new_max_cpc == max_cpc:
                        modifier_log.log_ignored_keyword(keyword_id, max_cpc, keyword, ad_group_name, conversion_rate, modifier_data=modifier_data)
                    elif new_max_cpc > max_cpc:
                        modifier_log.log_increased_keyword_cpc(
                            keyword_id, max_cpc, new_max_cpc, keyword, ad_group_name, conversion_rate, modifier_data=modifier_data)
                    elif new_max_cpc < max_cpc:
                        modifier_log.log_decreased_keyword_cpc(
                            keyword_id, max_cpc, new_max_cpc, keyword, ad_group_name, conversion_rate, modifier_data=modifier_data)

                if effect_label_name not in keyword_labels:
                    #apply label
                    self.apply_keyword_label(ad_group_id, keyword_id, effect_label_id)              
            
                total_records +=1            
            

        if total_records > 0:           

            if modifier_log is not None:
                modifier_log.set_complete()                
            if process_log is not None:
                process_log.set_complete()
            
            ReportScriptsResult.objects.filter(pk=report_result.id).update(total_records=total_records)           
            KeywordActionLog.objects.filter(modifier_log=modifier_log).update(result=report_result)

        return {
            'total_records': total_records,
        }
            

    def sqag_generator(self, script_schedule, campaign_obj):

        script_id = script_schedule.script_id
        campaign_id = script_schedule.campaign_id
        adwords_campaign_id = script_schedule.adwords_campaign_id
        
        total_records = 0
        script_obj = ReportScripts.objects.get(pk=script_id)
        predicates = {
            'CampaignId': adwords_campaign_id,
            'CampaignStatus': 'ENABLED',
            'AdGroupStatus': 'ENABLED',
            'QueryTargetingStatus': 'NONE',
            'QueryMatchTypeWithVariant__ne': 'EXACT',
            'Conversions__gt':'2'
        }
        date_range = 'CUSTOM_DATE'
        date_to = datetime.datetime.now()
        date_from = date_to - datetime.timedelta(days=90)
                        
        sq_selector = {
            'fields': [
                'CampaignName',
                'AdGroupName',
                'CampaignId',
                'AdGroupId',
                'KeywordId',
                'Query',
            ],
        }

        if predicates is not None:
            sq_selector['predicates'] = self.format_filters(predicates, single=True)

        sq_selector['dateRange'] = self.format_date_range(date_from, date_to)
        
        report = self.get_report(
            'Search Query report',
            'SEARCH_QUERY_PERFORMANCE_REPORT',
            date_range,
            sq_selector,
            True,
            False
        )        

        if len(report) > 0:
            for row in report:
                campaign_name = row[0]
                ad_group_name = row[1]
                ad_campaign_id = row[2]
                ad_group_id = row[3]
                keyword_id = row[4]
                query = row[5]
                match_type = 'exact'

                keyword_info = self.get_keyword(ad_group_id, keyword_id)

                if keyword_info == False:
                    continue
                
                cpc = keyword_info['cpc']
                final_urls = keyword_info['final_urls']

                best_ad = self.get_best_ad(ad_group_id)
                target_ad_id = best_ad['id']
                target_ad_type = best_ad['ad_type']
                target_ad_info = best_ad['ad_info']
                
                if target_ad_id < 0:
                    continue         
                               
                
                if target_ad_id > 0:
                    new_ad_group_name = "[[{query}]] - Search Query Extracted".format(query=query)
                    ad_group_res = self.add_ad_group(adwords_campaign_id, new_ad_group_name)
                    #ad_group_res = True
                    if ad_group_res != False:
                        new_ad_group_id = ad_group_res
                        res = self.add_keywords(new_ad_group_id, query, cpc, final_urls)
                        
                        if total_records == 0:
                            report_result = ReportScriptsResult.objects.create(
                                schedule=script_schedule,
                                user_id=self._user.id,
                                script_id=script_id,
                                client_customer_id=self._user.client_customer_id,
                                campaign_id=campaign_id,
                                adwords_campaign_id=adwords_campaign_id,
                                total_records=total_records,
                            )

                        final_url = target_ad_info['finalUrls'][0] if len(target_ad_info['finalUrls']) > 0 else ''
                        final_mobile_url = target_ad_info['finalMobileUrls'][0] if len(target_ad_info['finalMobileUrls']) > 0 else ''
                        path1 = target_ad_info['path1'] if target_ad_info['path1'] != None else ''
                        path2 = target_ad_info['path2'] if target_ad_info['path2'] != None else ''

                        if target_ad_type == "EXPANDED_TEXT_AD":

                            headline1 = target_ad_info['headline1'] if target_ad_info['headline1'] != None else ''
                            headline2 = target_ad_info['headline2'] if target_ad_info['headline2'] != None else ''
                            headline3 = target_ad_info['headline3'] if target_ad_info['headline3'] != None else ''
                            description1 = target_ad_info['description1'] if target_ad_info['description1'] != None else ''
                            description2 = target_ad_info['description2'] if target_ad_info['description2'] != None else ''

                            ReportScriptsResultSqagQs.objects.create(
                                result=report_result,
                                new_ad_group_id=new_ad_group_id,
                                source_ad_group_id=ad_group_id,
                                source_ad_id=str(target_ad_id),
                                new_ad_group=new_ad_group_name,                                
                                ad_type=target_ad_type,
                                headline1=headline1,
                                headline2=headline2,
                                headline3=headline3,
                                description1=description1,
                                description2=description2,
                                final_url=final_url,
                                final_mobile_url=final_mobile_url,
                                path1=path1,
                                path2=path2,
                                keyword=query,
                            )
                        elif target_ad_type == "RESPONSIVE_SEARCH_AD":
                            headlines = "\r\n".join(target_ad_info['headlines']) if target_ad_info['headlines'] != None else ''
                            descriptions = "\r\n".join(target_ad_info['descriptions']) if target_ad_info['descriptions'] != None else ''                    

                            ReportScriptsResultSqagQs.objects.create(
                                result=report_result,
                                new_ad_group_id=new_ad_group_id,
                                source_ad_group_id=ad_group_id,
                                source_ad_id=str(target_ad_id),
                                new_ad_group=new_ad_group_name,
                                ad_type=target_ad_type,
                                headlines=headlines,
                                descriptions=descriptions,
                                final_url=final_url,
                                final_mobile_url=final_mobile_url,
                                path1=path1,
                                path2=path2,
                                keyword=query,                               
                            )
                        else:
                            continue

                        total_records +=1

        if total_records > 0:
            ReportScriptsResult.objects.filter(pk=report_result.id).update(total_records=total_records)            

        return {
            'total_records': total_records,
        }                       


    #Quality Score Search
    def quality_score_search(self, script_schedule, campaign_obj):
        
        total_records = 0
        script_id = script_schedule.script_id
        campaign_id = script_schedule.campaign_id
        adwords_campaign_id = script_schedule.adwords_campaign_id
       
        ignore_label_name = 'QS Optimise Ignore'        
        
        ignore_label_id = self.get_label_id(ignore_label_name)
        
        predicates = {
            'CampaignId': adwords_campaign_id,
            'CampaignStatus': 'ENABLED',
            'AdGroupStatus': 'ENABLED',
            'Status': 'ENABLED',
            'QualityScore__lte': '3',
            'PostClickQualityScore': 'BELOW_AVERAGE',
            'LabelIds__not_contains_list': ignore_label_id

        }

        #date_range = 'CUSTOM_DATE'       
        #date_to = datetime.datetime.now()
        #date_from = date_to - datetime.timedelta(days=1000) 
        
        date_range = 'TODAY'          
                        
        kw_selector = {
            'fields': [
                'CampaignName',
                'AdGroupName',
                'CampaignId',
                'AdGroupId',
                'Id',
                'Criteria',
                'KeywordMatchType'
            ],
        }

        if predicates is not None:
            kw_selector['predicates'] = self.format_filters(predicates, single=True)
        if date_range == 'CUSTOM_DATE':
            kw_selector['dateRange'] = self.format_date_range(date_from, date_to)
        
        
        report = self.get_report(
            'Keywords report',
            'KEYWORDS_PERFORMANCE_REPORT',
            date_range,
            kw_selector
        )
        for row in report:
            campaign_name = row[0]
            ad_group_name = row[1]
            kw_campaign_id = row[2]
            ad_group_id = row[3]
            keyword_id = row[4]
            keyword = row[5]
            keyword_match_type = row[6]

            best_ad = self.get_best_ad(ad_group_id)
            target_ad_id = best_ad['id']
            target_ad_type = best_ad['ad_type']
            target_ad_info = best_ad['ad_info']
            if target_ad_id < 0:
                continue 
            
            if target_ad_id > 0:  
                keyword_info = self.get_keyword(ad_group_id, keyword_id)

                if keyword_info == False:
                    continue

                keyword_text = keyword_info['keyword_text']                
                cpc = keyword_info['cpc']
                final_urls = keyword_info['final_urls']

                self.apply_keyword_label(ad_group_id, keyword_id, ignore_label_id) 
                
                new_ad_group_name = "[{keyword_text}] - QS Optimised".format(keyword_text=keyword_text)
                ad_group_res = self.add_ad_group(adwords_campaign_id, new_ad_group_name)
                #ad_group_res = True
                if ad_group_res != False:                        
                    new_ad_group_id = ad_group_res
                    self.add_keywords(new_ad_group_id, keyword_text, cpc, final_urls)                    
                    
                    if total_records == 0:
                        report_result = ReportScriptsResult.objects.create(
                            schedule=script_schedule,
                            user_id=self._user.id,
                            script_id=script_id,
                            client_customer_id=self._user.client_customer_id,
                            campaign_id=campaign_id,
                            adwords_campaign_id=adwords_campaign_id,
                            total_records=total_records,
                        )

                    final_url = target_ad_info['finalUrls'][0] if len(target_ad_info['finalUrls']) > 0 else ''
                    final_mobile_url = target_ad_info['finalMobileUrls'][0] if len(target_ad_info['finalMobileUrls']) > 0 else ''
                    path1 = target_ad_info['path1'] if target_ad_info['path1'] != None else ''
                    path2 = target_ad_info['path2'] if target_ad_info['path2'] != None else ''

                    if target_ad_type == "EXPANDED_TEXT_AD":

                        headline1 = target_ad_info['headline1'] if target_ad_info['headline1'] != None else ''
                        headline2 = target_ad_info['headline2'] if target_ad_info['headline2'] != None else ''
                        headline3 = target_ad_info['headline3'] if target_ad_info['headline3'] != None else ''
                        description1 = target_ad_info['description1'] if target_ad_info['description1'] != None else ''
                        description2 = target_ad_info['description2'] if target_ad_info['description2'] != None else ''

                        ReportScriptsResultSqagQs.objects.create(
                            result=report_result,
                            new_ad_group_id=new_ad_group_id,
                            source_ad_group_id=ad_group_id,
                            source_ad_id=str(target_ad_id),
                            new_ad_group=new_ad_group_name,                                
                            ad_type=target_ad_type,
                            headline1=headline1,
                            headline2=headline2,
                            headline3=headline3,
                            description1=description1,
                            description2=description2,
                            final_url=final_url,
                            final_mobile_url=final_mobile_url,
                            path1=path1,
                            path2=path2,
                            keyword=keyword_text,
                        )
                    elif target_ad_type == "RESPONSIVE_SEARCH_AD":
                        headlines = "\r\n".join(target_ad_info['headlines']) if target_ad_info['headlines'] != None else ''
                        descriptions = "\r\n".join(target_ad_info['descriptions']) if target_ad_info['descriptions'] != None else ''                    

                        ReportScriptsResultSqagQs.objects.create(
                            result=report_result,
                            new_ad_group_id=new_ad_group_id,
                            source_ad_group_id=ad_group_id,
                            source_ad_id=str(target_ad_id),
                            new_ad_group=new_ad_group_name,
                            ad_type=target_ad_type,
                            headlines=headlines,
                            descriptions=descriptions,
                            final_url=final_url,
                            final_mobile_url=final_mobile_url,
                            path1=path1,
                            path2=path2,
                            keyword=keyword_text,                               
                        )
                    else:
                        continue                                            

                    total_records +=1

        if total_records > 0:
            ReportScriptsResult.objects.filter(pk=report_result.id).update(total_records=total_records)

        return {
            'total_records': total_records,
        }


    # Top of Page &amp; First Page Bid
    def top_of_page_and_first_page_bid(self, script_schedule, campaign_obj):

        qualifying_conversions = 2-0.01
        qualifying_clicks = config.KEYWORD_QUALIFYING_CLICKS

        total_records = 0
        schedule_id = script_schedule.id
        script_id = script_schedule.script_id
        campaign_id = script_schedule.campaign_id
        adwords_campaign_id = script_schedule.adwords_campaign_id
        cycle_period_days = campaign_obj.cycle_period_days
        target_cpa = campaign_obj.target_cpa
        max_cpc_limit = campaign_obj.max_cpc_limit
        target_bid_col = campaign_obj.top_of_first_page_bid
        

        if target_bid_col in ['FirstPageCpc', 'TopOfPageCpc',]:
        
            results = []
            effect_label_name = ' '.join(['Bid changed by ', target_bid_col])
            effect_label_id = self.get_label_id(effect_label_name)
            
            script_obj = ReportScripts.objects.get(pk=script_id)

            predicates = {
                'CampaignId': adwords_campaign_id,
                'CampaignStatus': 'ENABLED',
                'AdGroupStatus': 'ENABLED',
                'Status': 'ENABLED',
                'Conversions__gt': str(qualifying_conversions),
                'Clicks__gt': str(qualifying_clicks),      
            }
            date_range = 'CUSTOM_DATE'
            date_to = datetime.datetime.now()
            date_from = date_to - datetime.timedelta(days=cycle_period_days)                  
            

            kw_selector = {
                'fields': [
                    'CampaignName',
                    'AdGroupName',
                    'CampaignId',
                    'AdGroupId',
                    'Id',
                    'Criteria',
                    'KeywordMatchType',
                    str(target_bid_col),
                    'CpcBid',
                    'ConversionRate',
                    'Labels',
                ],
            }


            if predicates is not None:
                kw_selector['predicates'] = self.format_filters(predicates, single=True)
            if date_range == 'CUSTOM_DATE':
                kw_selector['dateRange'] = self.format_date_range(date_from, date_to)
            
            
            report = self.get_report(
                'Keywords report',
                'KEYWORDS_PERFORMANCE_REPORT',
                date_range,
                kw_selector
            )            
            
            if len(report) > 0:
                parameters = {
                    'target_cpa': target_cpa,
                    'max_cpc_limit': max_cpc_limit,
                    'cycle_period': cycle_period_days,
                }               
                process_log = self.process_log_create(
                    adwords_campaign_id,
                    is_dry_run=False,
                    parameters=parameters)
                modifier_log = process_log.start_modifier_log(script_obj.name)
            
            for row in report:
                campaign_name = row[0]
                ad_group_name = row[1]
                kw_campaign_id = int(row[2])
                ad_group_id = row[3]
                keyword_id = row[4]
                keyword = row[5]
                keyword_match_type = row[6]
                max_cpc = self.find_number(row[8], int)
                conversion_rate = self.percentage(row[9])
                keyword_labels_str = row[10]
                keyword_labels = []
                if keyword_labels_str[0] == "[" and keyword_labels_str[-1] == "]":
                    keyword_labels = json.loads(keyword_labels_str)

                select_bid = self.cast(row[7], float)
                
                new_max_cpc = min(select_bid, max_cpc_limit)
     
                #new_max_cpc = 600000
                if new_max_cpc > max_cpc:
                    self.set_keyword_max_cpc(ad_group_id, keyword_id, new_max_cpc)

                    if total_records == 0:
                        report_result = ReportScriptsResult.objects.create(
                            schedule=script_schedule,
                            user_id=self._user.id,
                            script_id=script_id,
                            client_customer_id=self._user.client_customer_id,
                            campaign_id=campaign_id,
                            adwords_campaign_id=adwords_campaign_id,
                            total_records=total_records,
                        )
                        
                        process_log = self.process_log_create(
                            adwords_campaign_id,
                            is_dry_run=False,
                            parameters=parameters)
                        modifier_log = process_log.start_modifier_log(script_obj.name)

                    modifier_data = {
                        'cycle_period': cycle_period_days,
                        'target_cpa': target_cpa,
                        'max_cpc_limit': max_cpc_limit,
                        'max_cpc': max_cpc,
                        'conversion_rate': conversion_rate,
                        'new_max_cpc': new_max_cpc,
                    }

                    if modifier_log is not None:
                        if new_max_cpc == max_cpc:
                            modifier_log.log_ignored_keyword(keyword_id, max_cpc, keyword, ad_group_name, conversion_rate, modifier_data=modifier_data)
                        elif new_max_cpc > max_cpc:
                            modifier_log.log_increased_keyword_cpc(
                                keyword_id, max_cpc, new_max_cpc, keyword, ad_group_name, conversion_rate, modifier_data=modifier_data)
                        elif new_max_cpc < max_cpc:
                            modifier_log.log_decreased_keyword_cpc(
                                keyword_id, max_cpc, new_max_cpc, keyword, ad_group_name, conversion_rate, modifier_data=modifier_data)

                    if effect_label_name not in keyword_labels:
                        #apply label
                        self.apply_keyword_label(ad_group_id, keyword_id, effect_label_id)                    
                    
                    total_records +=1

            if total_records > 0:       

                if modifier_log is not None:
                    modifier_log.set_complete()                
                if process_log is not None:
                    process_log.set_complete()
                
                ReportScriptsResult.objects.filter(pk=report_result.id).update(total_records=total_records)           
                KeywordActionLog.objects.filter(modifier_log=modifier_log).update(result=report_result)

        return {
            'total_records': total_records,
        }

    #Zero Campaign Spend - Alert

    def zero_spend_alert(self, script_schedule, campaign_obj):
        
        script_id = script_schedule.script_id
        campaign_id = script_schedule.campaign_id
        adwords_campaign_id = script_schedule.adwords_campaign_id
        alert_days = config.ZERO_SPEND_ALERT_DAYS

        customer = self.get_adwords_account_details(self._user)
        account_name = customer['descriptiveName']

        predicates = None

        if alert_days <= 1:
            date_range = 'YESTERDAY'
            message = "{account_name} Google Ads Account is Zero Spend in last 1 day".format(account_name=account_name)           
        else:
            date_range = 'CUSTOM_DATE'
            date_to = datetime.datetime.now()
            date_from = date_to - datetime.timedelta(days=alert_days)
            message = "{account_name} Google Ads Account is Zero Spend in last {alert_days} days".format(account_name=account_name, alert_days=alert_days)
            

        selector = {
            'fields': [
                'AccountCurrencyCode',
                'AccountDescriptiveName',
                'Cost'                
            ],
        }

        if date_range == 'CUSTOM_DATE':
            selector['dateRange'] = self.format_date_range(date_from, date_to) 

        if predicates is not None:
            selector['predicates'] = self.format_filters(predicates, single=True)        
        
        report = self.get_report(
            'Account report',
            'ACCOUNT_PERFORMANCE_REPORT',
            date_range,
            selector
        )
        cost = 0
        low_spend = False
        if len(report) == 0:
            low_spend = True
        elif len(report) > 0:
            row = report[0]
            cost = self.cast(row[2], float)
            account_name = row[1]
            if cost < 1:
                low_spend = True
        
        if low_spend == True:
            
            send_mail(
                'Captivise - Google Ads Account Zero Spend Alert',
                message,
                settings.DEFAULT_FROM_EMAIL,
                [self._user.email],
                fail_silently=False,
            )
            total_records = 1
            result = [{
                'name': 'Account is Zero Spend',
            }]
            results_json = json.dumps(result)
            ReportScriptsResult.objects.create(
                user_id=self._user.id,
                script_id=script_id,
                client_customer_id=self._user.client_customer_id,
                campaign_id=campaign_id,
                adwords_campaign_id=adwords_campaign_id,
                result=results_json,
                total_records=total_records
            )

        return {
            'total_records': total_records,
        }

    #Automated Negative Keywords
    
    def automated_negatives(self, script_schedule, campaign_obj):

        total_records = 0

        LOOK_BACK_DAYS = 365
        CPA_TOLERANCE = 5 # Factor to determine CPA threshold {i.e. actual cpa > (target cpa * cpa tolerance) }
        CR_TOLERANCE = 0.3 # Factor to determine CPA threshold {i.e. actual cr < (target cr * cr tolerance) }
        ZERO_CONVERSIONS_CLICKS_THRESHOLD = 100       
        #Handles situation where zero conversions but many clicks {e.g. zero conversions and cost > (target cpa * cpa tolerance)}
        #or {zero conversions and clicks> ZERO_CONVERSIONS_CLICKS_THRESHOLD=100)
        EXCLUDE_WORDS = ["is", "and", "the", "it", "with", "to", "for", "a", "that"]
        
        script_id = script_schedule.script_id
        campaign_id = script_schedule.campaign_id
        adwords_campaign_id = script_schedule.adwords_campaign_id
        campaign_safe_words = campaign_obj.safe_words.splitlines()
        target_cpa = campaign_obj.target_cpa
        target_conversion_rate = self.cast(campaign_obj.target_conversion_rate, float)
        
        safe_words = []
        safe_words.extend(campaign_safe_words)
        account_safe_words = self.get_account_safe_words()
        if account_safe_words != False:
            account_safe_words = account_safe_words.splitlines()
            safe_words.extend(account_safe_words)
        
        keyword_list_id = ''
        keyword_list_name = ''

        res = self.get_campaign_negative_keyword_lists(adwords_campaign_id)
        if res != False and 'sharedSetId' in res:
            keyword_list_id = res['sharedSetId']
            keyword_list_name = res['sharedSetName']        

        
        metrics = self.search_query_report(safe_words, adwords_campaign_id)
        target_cpa_threshold = 0
        tcr_threshold = 0
        target_cpa = 0
        if target_cpa > 0:
            target_cpa_threshold = target_cpa*CPA_TOLERANCE
        elif target_conversion_rate > 0:
            tcr_threshold = target_conversion_rate*CR_TOLERANCE

        if target_cpa == 0 and target_conversion_rate == 0:
            return False

        keywords = []
        for key in metrics:
            metric = metrics[key]           
            
            if target_cpa_threshold > 0:
                if metric['cpa'] > target_cpa_threshold:
                    keywords.append(key)
                elif metric['cost'] > target_cpa_threshold and metric['conversions'] == 0:                    
                    keywords.append(key)
                    

            if tcr_threshold > 0:
                if metric['conv_rate'] > 0:
                    if metric['conv_rate'] < tcr_threshold:
                        keywords.append(key)                            
                elif metric['clicks'] > ZERO_CONVERSIONS_CLICKS_THRESHOLD:
                    keywords.append(key)

        if len(keywords) > 0:
            res = self.add_negative_keywords(adwords_campaign_id, keyword_list_id, keywords)
            if res == True:

                report_result = ReportScriptsResult.objects.create(
                    schedule=script_schedule,
                    user_id=self._user.id,
                    script_id=script_id,
                    client_customer_id=self._user.client_customer_id,
                    campaign_id=campaign_id,
                    adwords_campaign_id=adwords_campaign_id,
                    total_records=total_records,
                )

                for keyword in keywords:
                    metric = metrics[keyword]

                    ReportScriptsResultNegativeKeywords.objects.create(
                        result=report_result,
                        keyword=keyword,
                        keyword_list_name=keyword_list_name,
                        keyword_list_id=keyword_list_id,
                        cost=metric['cost'],
                        conversions=metric['conversions'],
                        clicks=metric['clicks'],
                        conversion_rate=metric['conv_rate'],
                        cpa=metric['cpa'],
                    )                        

                    total_records +=1

                if total_records > 0:
                    ReportScriptsResult.objects.filter(pk=report_result.id).update(total_records=total_records)

        return {
            'total_records': total_records,
        }


            
    def ad_schedule_creation(self, script_schedule, campaign_obj):

        total_records = 0
        schedule_id = script_schedule.id
        script_id = script_schedule.script_id
        campaign_id = script_schedule.campaign_id
        adwords_campaign_id = script_schedule.adwords_campaign_id
        schedule_option = campaign_obj.ad_schedule

        script_obj = ReportScripts.objects.get(pk=script_id)

        schedule_map = {
            "alldays": {
                "Days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
                "Times": ["0:00", "6:00", "9:00", "12:00", "14:00", "18:00", "24:00"]
            },
            "weekdays": {
                "Days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
                "Times": ["0:00", "6:00", "9:00", "12:00", "14:00", "18:00", "24:00"]
            },
            "weekends": {
                "Days": ["Saturday", "Sunday"],
                "Times": ["0:00", "6:00", "9:00", "12:00", "14:00", "18:00", "24:00"]
            },
            "workdays": {
                "Days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
                "Times": ["9:00", "10:30", "12:00", "13:30", "15:00", "16:00", "17:00"]
            },
            "mornings": {
                "Days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
                "Times": ["6:00", "7:00", "8:00", "9:00", "10:00", "11:00", "12:00"]
            },
            "evenings": {
                "Days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
                "Times": ["18:00", "19:00", "20:00", "21:00", "22:00", "23:00", "24:00"]
            }
        }

        minute_interval = {
            '00': 'ZERO',
            '15': 'FIFTEEN',
            '30': 'THIRTY',
            '45': 'FORTY_FIVE'
        }        
        
        if schedule_option:
            schedule_days = schedule_map[schedule_option]["Days"]
            schedule_times = schedule_map[schedule_option]["Times"]
            operations = []            
           
            for schedule_day in schedule_days:
                i = 0
                schedule_day = schedule_day.upper()
                for schedule_time in schedule_times:
                    end_index = i+1
                    if end_index == len(schedule_times):
                        continue
                    
                    start_hours = schedule_time.split(":")
                    start_hour = start_hours[0]
                    start_minute = minute_interval[start_hours[1]]
                    next_time =  schedule_times[end_index]
                    end_hours = next_time.split(":")
                    end_hour = end_hours[0]
                    end_minute = minute_interval[end_hours[1]]
                    i += 1

                    operation = [{
                        'operator': 'ADD',
                        'operand': {
                            'campaignId': adwords_campaign_id,
                            'criterion': {
                                'xsi_type': 'AdSchedule',
                                'dayOfWeek': schedule_day,
                                'startHour': start_hour,
                                'startMinute': start_minute,
                                'endHour': end_hour,
                                'endMinute': end_minute,
                            },
                            'bidModifier': 1.0
                        }
                    }]
                    operations.append(operation)

                    start_time = ':'.join([start_hour, start_hours[1], '00'])
                    end_hour_db = '00' if end_hour == '24' else end_hour
                    end_time = ':'.join([end_hour_db, end_hours[1], '00'])                        
                    
                    if total_records == 0:
                        report_result = ReportScriptsResult.objects.create(
                            schedule=script_schedule,
                            user_id=self._user.id,
                            script_id=script_id,
                            client_customer_id=self._user.client_customer_id,
                            campaign_id=campaign_id,
                            adwords_campaign_id=adwords_campaign_id,
                            total_records=total_records,
                        )

                    ReportScriptsResultAdSchedule.objects.create(
                        result=report_result,
                        schedule_day=schedule_day,
                        start_time=start_time,
                        end_time=end_time,                            
                    )

                    total_records +=1

                if len(operations) > 0:
                    campaign_criterion_service = self.get_adwords_service('CampaignCriterionService')
                    output = campaign_criterion_service.mutate(operations)
                    if total_records > 0:
                        ReportScriptsResult.objects.filter(pk=report_result.id).update(total_records=total_records)                    

        return {
            'total_records': total_records,
        }

    
    def shopping_automated_product_listing_bids(self, script_schedule, campaign_obj, user_obj):
        total_records = 0
        look_back_days = 90
        schedule_id = script_schedule.id
        script_id = script_schedule.script_id
        campaign_id = script_schedule.campaign_id
        adwords_campaign_id = script_schedule.adwords_campaign_id

        target_cpa = campaign_obj.target_cpa
        target_conversion_margin = campaign_obj.target_conversion_margin
        max_cpc_limit = campaign_obj.max_cpc_limit
        target_roas = campaign_obj.target_roas

        date_range = 'CUSTOM_DATE'
        date_to = datetime.datetime.now()
        date_from = date_to - datetime.timedelta(days=look_back_days)
        operations = []

        #if target_cpa is None or target_cpa <= 0:
        #    return False

        product_text = ''

        #Target CPA Bid Changes
        #need new script
        
        """predicates = {
            'CampaignId': adwords_campaign_id,
            'AdGroupStatus': 'ENABLED',
            'Conversions__gt': '0'
        }        
                        
        selector = {
            'fields': [
                'AdGroupName',
                'AdGroupId',
                'Conversions',
                'Clicks',
            ],
        }

        if predicates is not None:
            selector['predicates'] = self.format_filters(predicates, single=True)

        selector['dateRange'] = self.format_date_range(date_from, date_to)
        
        
        report = self.get_report(
            'Ad Groups report',
            'ADGROUP_PERFORMANCE_REPORT',
            date_range,
            selector,
            True,
            False
        )
        for row in report:

            ad_group_name = row[0]
            ad_group_id = row[1]
            conversions = self.cast(row[2], float)
            clicks = self.cast(row[3], int)
            #LISTING_GROUP            

            if clicks == 0:
                continue

            if max_cpc_limit <= 0:
                continue

            newbid = (target_cpa*conversions)/clicks
            newbid = self.cast(min(newbid, max_cpc_limit), int)
            
            print('newbid')
            print(target_cpa, conversions, clicks)

            #if newbid <= 0:
            #    continue
            print('newbid')
            print(newbid)
            product_groups = self.get_biddable_product_groups(adwords_campaign_id, ad_group_id)
            print(product_groups)
            for product_group in product_groups:

                criterion_id = product_group['criterion']['id']
                product_group_val = ''
                if 'criterion' in product_group and 'caseValue' in product_group['criterion']:
                    if product_group['criterion']['caseValue']['value'] is not None:
                        product_group_val = str(product_group['criterion']['caseValue']['value'])
                        
                previous_max_cpc = 0
                if 'biddingStrategyConfiguration' in product_group and 'bids' in product_group['biddingStrategyConfiguration']:
                    if len(product_group['biddingStrategyConfiguration']['bids']) > 0:
                        previous_max_cpc = product_group['biddingStrategyConfiguration']['bids'][0]['bid']['microAmount']
                else:
                    continue

                operation = [{
                    'operator': 'SET',
                    'operand': {
                        'xsi_type': 'BiddableAdGroupCriterion',
                        'adGroupId': ad_group_id,
                        'criterion': {
                            'id': criterion_id,
                        },
                        'biddingStrategyConfiguration': {
                            'bids': [
                                {
                                    'xsi_type': 'CpcBid',
                                    'bid': {
                                        'microAmount': newbid,
                                    },
                                },
                            ],
                        },
                    },
                }]
                operations.append(operation)

                if total_records == 0:
                    report_result = ReportScriptsResult.objects.create(
                        schedule=script_schedule,
                        user_id=self._user.id,
                        script_id=script_id,
                        client_customer_id=self._user.client_customer_id,
                        campaign_id=campaign_id,
                        adwords_campaign_id=adwords_campaign_id,
                        total_records=total_records,
                    )

                ReportScriptsResultShoppingBids.objects.create(
                    result=report_result,
                    ad_group_name=ad_group_name,
                    ad_group_id=ad_group_id,
                    product_group_id=criterion_id,
                    product_group=product_group_val,
                    previous_max_cpc=previous_max_cpc,
                    new_max_cpc=newbid,                           
                )

                total_records +=1
        
        if len(operations) > 0:
            ad_group_criterion_service = self.get_adwords_service('AdGroupCriterionService')
            #output = ad_group_criterion_service.mutate(operations)
            print(operations)
        """

        if target_roas is None or target_roas <= 0:
            return False

        #Target ROAS Bid Changes
        if target_roas > 0:
            predicates_r = {
                'CampaignId': adwords_campaign_id,
                'AdGroupStatus': 'ENABLED',
                'Conversions__gt': '1',
                'Cost__gt': '0'
            }        
                            
            selector_r = {
                'fields': [
                    'AdGroupName',
                    'AdGroupId',
                    'ConversionValue',
                    'Cost',
                ],
            }

            if predicates_r is not None:
                selector_r['predicates'] = self.format_filters(predicates_r, single=True)

            selector_r['dateRange'] = self.format_date_range(date_from, date_to)
            
            
            report_r = self.get_report(
                'Ad Groups report',
                'ADGROUP_PERFORMANCE_REPORT',
                date_range,
                selector_r,
                True,
                False
            )
            
            revenue_by_id = {}
            ad_group_name_by_id = {}
            for row in report_r:

                ad_group_name = row[0]
                ad_group_id = row[1]
                conversion_value = row[2]

                if ad_group_id not in revenue_by_id:
                    revenue_by_id[ad_group_id] = 0.0

                revenue_by_id[ad_group_id] += self.cast(conversion_value, float)
                ad_group_name_by_id[ad_group_id] = ad_group_name
            
            gmc = GoogleMerchantConnect(user_obj)
            prices_by_id = gmc.get_products_id_price()

            campaign_stat = self.campaign_performance(adwords_campaign_id, date_from, date_to)
            campaign_conversion_rate = campaign_stat['conversion_rate']
            operations = []
            if len(revenue_by_id) > 0:
                for ad_group_id, conversion_value in revenue_by_id.items():
                    ad_group_name = ad_group_name_by_id[ad_group_id]

                    product_groups = self.get_biddable_product_groups(adwords_campaign_id, ad_group_id)
                    if product_groups is not False:
                        for product_group in product_groups:
                            
                            criterion_id = product_group['criterion']['id']
                            product_group_val = ''
                            if 'caseValue' in product_group:
                                product_group_val = product_group['caseValue']['value']
                            elif 'caseValue' in product_group['criterion']:
                                product_group_val = str(product_group['criterion']['caseValue']['value'])
                            
                            previous_max_cpc = 0
                            if 'biddingStrategyConfiguration' in product_group and len(product_group['biddingStrategyConfiguration']['bids']) > 0:
                                previous_max_cpc = product_group['biddingStrategyConfiguration']['bids'][0]['bid']['microAmount']
                            
                            if 'dimension' in product_group and product_group['dimension'] != "ITEM_ID":                    
                                continue

                            newbid = 0
                            pg_group_stat = self.product_group_performance(adwords_campaign_id, ad_group_id, criterion_id, date_from, date_to)
                            conversions = pg_group_stat['conversions']
                            conversion_rate = pg_group_stat['conversion_rate']
                            if conversions > 0:
                                newbid = ((conversion_value/conversions) * (1/target_roas)) * conversion_rate
                            elif product_group_val in prices_by_id:
                                pr_price = self.cast(prices_by_id[product_group_val], float)
                                newbid = (pr_price * (1/target_roas)) * campaign_conversion_rate
                            else:
                                continue

                            if newbid <= 0:                    
                                continue

                            if isinstance(max_cpc_limit, (int, float)):
                                max_cpc_limit = micro_amount_to_decimal(max_cpc_limit)
                                newbid = min(newbid, max_cpc_limit)
                                if newbid <= 0:
                                    continue

                                newbid = decimal_to_micro_amount(newbid)

                                if previous_max_cpc != newbid:

                                    operation = [{
                                        'operator': 'SET',
                                        'operand': {
                                            'xsi_type': 'BiddableAdGroupCriterion',
                                            'adGroupId': ad_group_id,
                                            'criterion': {
                                                'id': criterion_id,
                                            },
                                            'biddingStrategyConfiguration': {
                                                'bids': [
                                                    {
                                                        'xsi_type': 'CpcBid',
                                                        'bid': {
                                                            'microAmount': newbid,
                                                        },
                                                    },
                                                ],
                                            },
                                        },
                                    }]
                                    operations.append(operation)

                                    if total_records == 0:
                                        report_result = ReportScriptsResult.objects.create(
                                            schedule=script_schedule,
                                            user_id=self._user.id,
                                            script_id=script_id,
                                            client_customer_id=self._user.client_customer_id,
                                            campaign_id=campaign_id,
                                            adwords_campaign_id=adwords_campaign_id,
                                            total_records=total_records,
                                        )

                                    ReportScriptsResultShoppingBids.objects.create(
                                        result=report_result,
                                        ad_group_name=ad_group_name,
                                        ad_group_id=ad_group_id,
                                        product_group_id=criterion_id,
                                        product_group=product_group_val,
                                        previous_max_cpc=previous_max_cpc,
                                        new_max_cpc=newbid,                           
                                    )

                                    total_records +=1

        if len(operations) > 0:
            ad_group_criterion_service = self.get_adwords_service('AdGroupCriterionService')
            output = ad_group_criterion_service.mutate(operations)                       

        
        if total_records > 0:
            ReportScriptsResult.objects.filter(pk=report_result.id).update(total_records=total_records)

        return {
            'total_records': total_records,
        }


    def shopping_sq_title_description_match(self, script_schedule, campaign_obj, user_obj):
        
        total_records = 0
        look_back_days = 180
        qualifying_conversions = 2

        adjusted_conversions = qualifying_conversions-1

        schedule_id = script_schedule.id
        script_id = script_schedule.script_id
        campaign_id = script_schedule.campaign_id
        adwords_campaign_id = script_schedule.adwords_campaign_id
        campaign_name = campaign_obj.title

        if not user_obj.merchant_id or not user_obj.merchant_refresh_token:
            return False

        date_range = 'CUSTOM_DATE'
        date_to = datetime.datetime.now()
        date_from = date_to - datetime.timedelta(days=look_back_days)

        gmc = GoogleMerchantConnect(user_obj)
        product_text = gmc.get_products_text()

        if product_text is False:
            return False

        predicates = {
            'CampaignId': adwords_campaign_id,
            'CampaignStatus': 'ENABLED',
            'Conversions__gt': str(adjusted_conversions)
        }        
                        
        selector = {
            'fields': [
                'AdGroupName',
                'AdGroupId',
                'Query',
            ],
        }

        if predicates is not None:
            selector['predicates'] = self.format_filters(predicates, single=True)

        selector['dateRange'] = self.format_date_range(date_from, date_to)
        
        report = self.get_report(
            'Search Query report',
            'SEARCH_QUERY_PERFORMANCE_REPORT',
            date_range,
            selector,
            True,
            False
        )
        search_arr = []
        searches_not_found = []
        if len(report) > 0:
            for row in report:
                ad_group_name = row[0]
                ad_group_id = row[1]
                query = row[2]
                if query not in search_arr:
                    if product_text.find(query) !=-1:                        
                        continue
                    else:
                        search = [ad_group_name, query]
                        searches_not_found.append(search)
                    search_arr.append(query)                   
        
        if len(searches_not_found) > 0:
            searches = []
            for ad_group_name, search_query  in searches_not_found:                
                
                if total_records == 0:
                    report_result = ReportScriptsResult.objects.create(
                        schedule=script_schedule,
                        user_id=self._user.id,
                        script_id=script_id,
                        client_customer_id=self._user.client_customer_id,
                        campaign_id=campaign_id,
                        adwords_campaign_id=adwords_campaign_id,
                        total_records=total_records,
                    )

                ReportScriptsResultShoppingSqMatch.objects.create(
                    result=report_result,
                    ad_group_name=ad_group_name,
                    search_query=search_query,
                )

                total_records +=1
                mail_string = '<tr><td align="left">{ad_group_name}</td><td align="left">{search_query}</td></tr>'.format(ad_group_name=ad_group_name, search_query=search_query)
                searches.append(mail_string)
        
        if total_records > 0:
            ReportScriptsResult.objects.filter(pk=report_result.id).update(total_records=total_records)
            table_html = "".join(searches)
            message = 'Campaign name: {campaign_name} <br />The following converting searches do not appear in shopping copy:<br /><table style="width:600px;" cellpadding="5" cellspacing="5"><tr><th align="left">Ad Group Name</th><th align="left">Search Query</th></tr>{table_html}</table>'.format(
                table_html=table_html,
                campaign_name=campaign_name
            )
            send_mail(
                'Captivise - Alert: Shopping - Search Query vs Title / Description Match',
                message,
                settings.DEFAULT_FROM_EMAIL,
                [self._user.email],
                fail_silently=False,
                html_message=message,
            )

        return {
            'total_records': total_records,
        }
    

    def apply_keyword_label(self, ad_group_id, keyword_id, label_id):

        try:
            ad_group_criterion_service = self.get_adwords_service('AdGroupCriterionService')
            operations = [
                {
                    'operator': 'ADD',
                    'operand': {
                        'adGroupId': ad_group_id,
                        'criterionId': keyword_id,                    
                        'labelId': label_id,
                    }
                },      
            ]

            result = ad_group_criterion_service.mutateLabel(operations)

        except Exception:
            return False 


    def check_label(self, label_name):

        label_service = self.get_adwords_service('LabelService')

        selector = {
            'fields': ['LabelId', 'LabelName', 'LabelStatus'], 
            'ordering': {
                'field': 'LabelName',
                'sortOrder': 'ASCENDING'
            },
            'paging': {
                'startIndex': '0',
                'numberResults': '1'
            },            
            'predicates': [                
                {
                    'field': 'LabelName',
                    'operator': 'EQUALS',
                    'values': [label_name]
                },
                {
                    'field': 'LabelStatus',
                    'operator': 'EQUALS',
                    'values': ['ENABLED']
                },
            ]
        }
        page = label_service.get(selector)
        if 'entries' in page and len(page['entries']) > 0:
            for label in page['entries']:                                    
                if label_name in label['name']:
                    return label                                    
        else:
            return False            
        

    def create_label(self, label_name):
        label_service = self.get_adwords_service('LabelService')
        operations = [
            {
                'operator': 'ADD',
                'operand': {
                    'xsi_type': 'TextLabel',
                    'name': label_name,
                    'status': 'ENABLED',                    
                }
            },      
        ]

        result = label_service.mutate(operations)
        if 'value' in result:
            return result['value'][0]

    def get_label_id(self, label_name):

        label = self.check_label(label_name)
        if label == False:
            label = self.create_label(label_name)
            label_id = label['id']
        else:
            label_id = label['id']
        
        return label_id

    def add_ad_group(self, campaign_id, ad_group_name):
        try:
            ad_group_service = self.get_adwords_service('AdGroupService')
            # Construct operations and add ad groups.
            operations = [
                {
                    'operator': 'ADD',
                    'operand': {
                        'campaignId': campaign_id,
                        'name': ad_group_name,
                        'status': 'PAUSED',   

                    }
                } 
            ]
            ad_groups = ad_group_service.mutate(operations)
            if 'value' in ad_groups:
                for ad_group in ad_groups['value']:
                    return ad_group['id']
            else:
                return False
                
        except Exception:
            return False

    
    def add_keywords(self, ad_group_id, keyword, cpc, final_urls):
        try:
            ad_group_criterion_service = self.get_adwords_service('AdGroupCriterionService')

            keyword1 = {
                'xsi_type': 'BiddableAdGroupCriterion',
                'adGroupId': ad_group_id,
                'criterion': {
                    'xsi_type': 'Keyword',
                    'matchType': 'BROAD',
                    'text': keyword
                },
                'biddingStrategyConfiguration': {
                    'bids': [
                        {
                            'xsi_type': 'CpcBid',
                            'bid': {
                                'microAmount': cpc,
                            },
                        },
                    ],
                },
            
            }
            if final_urls is not None:
                keyword1['finalUrls'] = {
                    'urls': [final_urls]
                }

            operations = [
                {
                    'operator': 'ADD',
                    'operand': keyword1
                },      
            ]
            ad_group_criteria = ad_group_criterion_service.mutate(operations)
            return ad_group_criteria
        except Exception:
            return False

    
    def get_adwords_account_details(self, user):
        adwords_client = get_adwords_client(user.refresh_token, user.client_customer_id)

        customers = adwords_client.GetService('CustomerService').getCustomers()

        for customer in customers:
            if customer.customerId == int(user.client_customer_id):
                return customer
    
    def update_ad_group_status(self, ad_group_id, status):
        ad_group_service = self.get_adwords_service('AdGroupService')
        operations = [{
            'operator': 'SET',
            'operand': {
                'id': ad_group_id,
                'status': status,
            }
        }]
        
        return ad_group_service.mutate(operations)

    def add_expanded_text_ad(self, result):  
        
        headline3 = result.headline3
        description2 = result.description2
        path1 = result.path1
        path2 = result.path2
        final_mobile_url = result.final_mobile_url
        ad_group_id = result.new_ad_group_id

        ad_info = {
            'xsi_type': 'ExpandedTextAd',
            'headlinePart1': result.headline1,
            'headlinePart2': result.headline2,
            'description': result.description1,
            'finalUrls': [result.final_url],
        }
        if headline3 and headline3.strip():            
            ad_info['headlinePart3'] = headline3        
        if description2 and description2.strip():            
            ad_info['description2'] = description2
        if path1 and path1.strip():            
            ad_info['path1'] = path1
        if path2 and path2.strip():            
            ad_info['path2'] = path2        
        if final_mobile_url and final_mobile_url.strip():            
            ad_info['finalMobileUrls'] = [final_mobile_url]        
        

        operations = [
            {
                'operator': 'ADD',
                'operand': {
                    'xsi_type': 'AdGroupAd',
                    'adGroupId': ad_group_id,
                    'ad': ad_info,
                }
            }
        ]
        ad_group_ad_service = self.get_adwords_service('AdGroupAdService')
        ads = ad_group_ad_service.mutate(operations)
        if 'value' in ads:
            for ad in ads['value']:
                return ad
        else:
            return False      


    def add_responsive_search_ad(self, result):
        
        
        headlines_all = []
        rec = 0
        headlines = result.headlines.splitlines()
        descriptions = result.descriptions.splitlines()
        final_url = result.final_url
        final_mobile_url = result.final_mobile_url
        path1 = result.path1
        path2 = result.path2
        final_mobile_url = result.final_mobile_url
        ad_group_id = result.new_ad_group_id

        for head_text in headlines:
            rec +=1
            if rec == 1:
                headline = {
                    'asset': {
                        'xsi_type': 'TextAsset',
                        'assetText': head_text
                    },
                    'pinnedField': 'HEADLINE_1'
                }                             
            else:
                headline = {
                    'asset': {
                        'xsi_type': 'TextAsset',
                        'assetText': head_text,
                    }
                }
            
            headlines_all.append(headline)

        description_all = []
        for desc_text in descriptions:
            if desc_text.strip():            
                description = {
                    'asset': {
                        'xsi_type': 'TextAsset',
                        'assetText': desc_text,
                    }
                }
                
                description_all.append(description)

        ad_info = {
            'xsi_type': 'ResponsiveSearchAd',
            'finalUrls': [final_url],
            'headlines': [*headlines_all],
            'descriptions': [*description_all],
        }
        if path1 and path1.strip():            
            ad_info['path1'] = path1
        if path2 and path2.strip():            
            ad_info['path2'] = path2
        
        if final_mobile_url and final_mobile_url.strip():            
            ad_info['finalMobileUrls'] = [final_mobile_url]
            
        responsive_search_ad = {
            'xsi_type': 'AdGroupAd',
            'adGroupId': ad_group_id,
            'ad': ad_info,
        }

        # Create the operations.
        operations = [{
            'operator': 'ADD',
            'operand': responsive_search_ad
        }]
        # Create the ad on the server.
        ad_group_ad_service = self.get_adwords_service('AdGroupAdService')
        ads = ad_group_ad_service.mutate(operations)

        if 'value' in ads:
            for ad in ads['value']:
                return ad
        else:
            return False


    def get_best_ad(self, ad_group_id):

        ad_group_ad_service = self.get_adwords_service('AdGroupAdService')

        # Construct selector and get all ads for a given ad group.
        lowest_cpa = -1
        target_ad_id = -1
        highest_ctr = 0
        target_ad_type = ""
        target_ad_info = "No ads to copy. Please create manually"
        
        AD_PAGE_SIZE = 1000
        ad_offset = 0
        ad_selector = {
            'fields': [
                'Id',
                'AdGroupId',
                'Status',
                'AdType',
                'HeadlinePart1',
                'HeadlinePart2',
                'Path1',
                'Path2',
                'ExpandedTextAdHeadlinePart3',
                'Description',
                'ExpandedTextAdDescription2',
                'ResponsiveSearchAdDescriptions',
                'ResponsiveSearchAdHeadlines',
                'ResponsiveSearchAdPath1',
                'ResponsiveSearchAdPath2',
                'CreativeFinalUrls',
                'CreativeFinalMobileUrls',
            ],
            'predicates': [
                {
                    'field': 'AdGroupId',
                    'operator': 'EQUALS',
                    'values': [ad_group_id]
                },
                {
                    'field': 'Status',
                    'operator': 'EQUALS',
                    'values': ['ENABLED']
                }                        
            ],
            'paging': {
                'startIndex': str(ad_offset),
                'numberResults': str(AD_PAGE_SIZE)
            },
            'ordering': [
                {
                    'field': 'Id',
                    'sortOrder': 'ASCENDING'
                }
            ]
        }
        ad_more_pages = True
        while ad_more_pages:
            ad_page = ad_group_ad_service.get(ad_selector)

            # Display results.
            if 'entries' in ad_page:
                for ad in ad_page['entries']:
                        
                    ad_type = ad['ad']['type']
                    if ad_type == "EXPANDED_TEXT_AD":                        
                        
                        ad_info = {
                            'headlinePart1': ad['ad']['headlinePart1'],
                            'headlinePart2': ad['ad']['headlinePart2'],
                            'headlinePart3': ad['ad']['headlinePart3'],
                            'description': ad['ad']['description'],
                            'description2': ad['ad']['description2'],
                            'path1': ad['ad']['path1'],
                            'path2': ad['ad']['path2'],
                            'finalUrls': ad['ad']['finalUrls'],
                            'finalMobileUrls': ad['ad']['finalMobileUrls'],                           
                        }
                    elif ad_type == "RESPONSIVE_SEARCH_AD":
                        headlines = []
                        for headline in ad['ad']['headlines']:
                            headlines.append(headline['asset']['assetText'])
                        
                        descriptions = []
                        for description in ad['ad']['descriptions']:
                            descriptions.append(description['asset']['assetText'])
                        
                        ad_info = {
                            'headlines': headlines,
                            'descriptions': descriptions,
                            'path1': ad['ad']['path1'],
                            'path2': ad['ad']['path2'],
                            'finalUrls': ad['ad']['finalUrls'],
                            'finalMobileUrls': ad['ad']['finalMobileUrls'],                           
                        }                        
                    else:
                        continue

                    adp_predicates = {
                        'Id': ad['ad']['id'],
                        'Status': 'ENABLED',
                    }
                    adp_date_range = 'LAST_30_DAYS'
                                    
                    adp_selector = {
                        'fields': [
                            'Id',
                            'Cost',
                            'Conversions',
                            'Ctr'
                        ],
                    }

                    if adp_predicates is not None:
                        adp_selector['predicates'] = self.format_filters(adp_predicates, single=True)
                    
                    adp_report = self.get_report(
                        'Ad Performance report',
                        'AD_PERFORMANCE_REPORT',
                        adp_date_range,
                        adp_selector,
                        True,
                        False
                    )

                    if len(adp_report) > 0:
                        for adp_row in adp_report:
                            ad_id = self.cast(adp_row[0], int)
                            cost = self.cast(adp_row[1], float)
                            conversions = self.cast(adp_row[2], float)
                            ctr = self.cast(adp_row[3].replace("%", ""), float)
                            cpa = 0
                            if (conversions > 0):
                                cpa = cost / conversions
                            
                            if (cpa > 0):
                                if cpa < lowest_cpa or lowest_cpa < 0:
                                    lowest_cpa = cpa
                                    target_ad_id = ad_id
                                    target_ad_type = ad_type
                                    target_ad_info = ad_info                      
                            elif ctr > highest_ctr or highest_ctr == 0:
                                highest_ctr = ctr
                                target_ad_id = ad_id
                                target_ad_type = ad_type
                                target_ad_info = ad_info          
                    
            else:
                continue
            ad_offset += AD_PAGE_SIZE
            ad_selector['paging']['startIndex'] = str(ad_offset)
            ad_more_pages = ad_offset < int(ad_page['totalNumEntries'])
        
        ad_result = {
            'id': target_ad_id,
            'ad_type': target_ad_type,
            'ad_info': target_ad_info            
        }
        return ad_result    
    
    
    def get_keyword(self, ad_group_id, keyword_id):

        kw_offset = 0
        PAGE_SIZE = 1
        kw_selector = {
            'fields': ['Id', 'CriteriaType', 'KeywordMatchType', 'KeywordText', 'FinalUrls', 'CpcBid'],
            'predicates': [
                {
                    'field': 'AdGroupId',
                    'operator': 'EQUALS',
                    'values': [ad_group_id]
                },
                {
                    'field': 'Id',
                    'operator': 'EQUALS',
                    'values': [keyword_id]
                },
                {
                    'field': 'CriteriaType',
                    'operator': 'EQUALS',
                    'values': ['KEYWORD']
                }
            ],
            'paging': {
                'startIndex': str(kw_offset),
                'numberResults': str(PAGE_SIZE)
            },
            'ordering': [{'field': 'KeywordText', 'sortOrder': 'ASCENDING'}]
        }
        ad_group_criterion_service = self.get_adwords_service('AdGroupCriterionService')

        kw_more_pages = True
        while kw_more_pages:
            kw_page = ad_group_criterion_service.get(kw_selector)
            # Display results.
            if 'entries' in kw_page and len(kw_page['entries']) > 0:
                for keyword in kw_page['entries']:                    
                    keyword_text = keyword['criterion']['text']
                    final_urls = None
                    if keyword['finalUrls'] is not None:
                        final_urls = keyword['finalUrls']['urls'][0]                            
                    cpc = 0
                    if len(keyword['biddingStrategyConfiguration']['bids']) > 0:
                        cpc = keyword['biddingStrategyConfiguration']['bids'][0]['bid']['microAmount']                    
            else:
                return False
                
            kw_offset += PAGE_SIZE
            kw_selector['paging']['startIndex'] = str(kw_offset)
            kw_more_pages = kw_offset < int(kw_page['totalNumEntries'])
        
        keyword_result = {
            'keyword_text': keyword_text,
            'final_urls': final_urls,
            'cpc': cpc
        }
        return keyword_result
    

    def get_ad_schedule(self, adwords_campaign_id):

        offset = 0
        PAGE_SIZE = 10
        selector = {
            'fields': ['Id', 'CriteriaType', 'DayOfWeek'],
            'predicates': [
                {
                    'field': 'CampaignId',
                    'operator': 'EQUALS',
                    'values': [adwords_campaign_id]
                },
                {
                    'field': 'CriteriaType',
                    'operator': 'EQUALS',
                    'values': ['AD_SCHEDULE']
                }
            ],
            'paging': {
                'startIndex': str(offset),
                'numberResults': str(PAGE_SIZE)
            },
            'ordering': [{'field': 'DayOfWeek', 'sortOrder': 'ASCENDING'}]
        }
        campaign_criterion_service = self.get_adwords_service('CampaignCriterionService')

        page = campaign_criterion_service.get(selector)
        
        # Display results.
        if 'entries' in page and len(page['entries']) > 0:                              
            return page['entries']                                    
        else:
            return False


    def get_campaign_negative_keyword_lists(self, adwords_campaign_id):
        
        offset = 0
        PAGE_SIZE = 1000
        selector = {
            'fields': ['SharedSetId', 'CampaignId', 'CampaignName', 'SharedSetName', 'SharedSetType'],
            'predicates': [
                {
                    'field': 'SharedSetType',
                    'operator': 'EQUALS',
                    'values': ['NEGATIVE_KEYWORDS']
                },
                {
                    'field': 'CampaignId',
                    'operator': 'EQUALS',
                    'values': [adwords_campaign_id]
                },
            ],
            'paging': {
                'startIndex': str(offset),
                'numberResults': str(PAGE_SIZE)
            },
            'ordering': [{'field': 'CampaignName', 'sortOrder': 'ASCENDING'}]
        }

        campaign_shared_set_service = self.get_adwords_service('CampaignSharedSetService')

        page = campaign_shared_set_service.get(selector)
        if 'entries' in page and len(page['entries']) > 0:                              
            return page['entries'][0]                                    
        else:
            return False


    def search_query_report(self, safe_words, adwords_campaign_id):

        EXCLUDE_WORDS = ["is", "and", "the", "it", "with", "to", "for", "a", "that"]

        predicates = {
            'CampaignId': adwords_campaign_id,
            'Clicks__gt':'0'
        }
        date_range = 'CUSTOM_DATE'
        date_to = datetime.datetime.now()
        date_from = date_to - datetime.timedelta(days=365)   
                        
        selector = {
            'fields': [
                'CampaignId',
                'Query',
                'Cost',
                'Clicks',
                'Conversions',
            ],
        }

        if predicates is not None:
            selector['predicates'] = self.format_filters(predicates, single=True)

        selector['dateRange'] = self.format_date_range(date_from, date_to)
        
        report = self.get_report(
            'Search Query report',
            'SEARCH_QUERY_PERFORMANCE_REPORT',
            date_range,
            selector,
            True,
            False
        )
        metrics_byngram = {}
        for row in report:
            campaign_id = row[0]
            query = row[1]
            cost = self.cast(row[2], float) 
            clicks = self.cast(row[3], int) 
            conversions = self.cast(row[4], float) 
            words = query.split()
            words.sort()
            word_length = len(words)
            for i in range(word_length):                
                if words[i] in EXCLUDE_WORDS:
                    continue
                ngram_key = words[i]
                if ngram_key in safe_words:
                    continue              
                
                
                if ngram_key not in metrics_byngram:
                    metrics_byngram[ngram_key] = {'clicks':0, 'conversions':0.0, 'cost':0.0, 'cpa':0.0, 'conv_rate':0.0}
                
                metrics_byngram[ngram_key]['clicks'] += clicks
                metrics_byngram[ngram_key]['conversions'] += conversions
                metrics_byngram[ngram_key]['cost'] += cost 
                
                for j in range(i+1, word_length):
                    if words[j] in EXCLUDE_WORDS:
                        continue
                    
                    if words[i] == words[j]:
                        continue

                    ngram_key = " ".join([words[i], words[j]])
                    if ngram_key in safe_words:                        
                        continue
                    
                    if ngram_key not in metrics_byngram:
                        metrics_byngram[ngram_key] = {'clicks':0, 'conversions':0.0, 'cost':0.0, 'cpa':0.0, 'conv_rate':0.0}
                    
                    metrics_byngram[ngram_key]['clicks'] += clicks
                    metrics_byngram[ngram_key]['conversions'] += conversions
                    metrics_byngram[ngram_key]['cost'] += cost
                
                    for k in range(j+1, word_length):

                        if words[k] in EXCLUDE_WORDS:
                            continue
                    
                        if words[j] == words[k]:
                            continue

                        ngram_key = " ".join([words[i], words[j], words[k]])
                        if ngram_key in safe_words:                        
                            continue
                    
                        if ngram_key not in metrics_byngram:
                            metrics_byngram[ngram_key] = {'clicks': 0, 'conversions': 0.0, 'cost': 0.0, 'cpa': 0.0, 'conv_rate':0.0}
                    
                        metrics_byngram[ngram_key]['clicks'] += clicks
                        metrics_byngram[ngram_key]['conversions'] += conversions
                        metrics_byngram[ngram_key]['cost'] += cost


        #Loop though and calculate the cpa & rate
        for key in metrics_byngram:

            if metrics_byngram[key]['conversions'] > 0:
                metrics_byngram[key]['cpa'] = metrics_byngram[key]['cost'] / metrics_byngram[key]['conversions']
            if metrics_byngram[key]['clicks'] > 0:
                metrics_byngram[key]['conv_rate'] = metrics_byngram[key]['conversions'] / metrics_byngram[key]['clicks']
        return metrics_byngram  



    def add_negative_keywords(self, adwords_campaign_id, keyword_list_id, keywords):

        shared_criterion_service = self.get_adwords_service('SharedCriterionService')
        campaign_shared_set_service = self.get_adwords_service('CampaignSharedSetService')
        campaign_criterion_service = self.get_adwords_service('CampaignCriterionService')

        if keyword_list_id == '':
            # Add negative keywords to shared set.
            
            shared_criteria = [
                {
                    'xsi_type': 'NegativeCampaignCriterion',
                    'campaignId': adwords_campaign_id,
                    'criterion': {
                        'xsi_type': 'Keyword',
                        'text': keyword,
                        'matchType': 'BROAD'
                    },
                    
                } for keyword in keywords
            ]

            operations = [
                {
                    'operator': 'ADD',
                    'operand': criterion
                } for criterion in shared_criteria
            ]

            result = campaign_criterion_service.mutate(operations)
            
        elif keyword_list_id != '':
            shared_criteria = [
                {
                    'criterion': {
                        'xsi_type': 'Keyword',
                        'text': keyword,
                        'matchType': 'BROAD'
                    },
                    'negative': True,
                    'sharedSetId': keyword_list_id
                } for keyword in keywords
            ]

            operations = [
                {
                    'operator': 'ADD',
                    'operand': criterion
                } for criterion in shared_criteria
            ]

            response = shared_criterion_service.mutate(operations)            

            # Attach the articles to the campaign.
            campaign_set = {
                'campaignId': adwords_campaign_id,
                'sharedSetId': keyword_list_id
            }

            operations = [
                {
                    'operator': 'ADD',
                    'operand': campaign_set
                }
            ]

            result = campaign_shared_set_service.mutate(operations)

        if 'value' in result:
            return True
        else:
            return False


    def cast(self, value, to_type):
        try:
            return to_type(value)
        except Exception:
            return None

    def find_number(self, value, to_type=None):
        find_number = [float(s) for s in re.findall(r'-?\d+\.?\d*', value)]

        if len(find_number):
            if to_type is not None:
                try:
                    return to_type(find_number[0])
                except Exception:
                    return None
            else:
                return find_number[0]
        else:
            return False


    def percentage(self, value):
        return Decimal(value[:-1])


    def sqag_qs_apply(self, script_schedule, campaign_obj):

        schedule_id = script_schedule.id
        script_id = script_schedule.script_id
        campaign_id = script_schedule.campaign_id
        adwords_campaign_id = script_schedule.adwords_campaign_id
        ref_result_id = script_schedule.ref_result_id
        
        total_records = 0
        script_obj = ReportScripts.objects.get(pk=script_id)

        sqag_qs_results = ReportScriptsResultSqagQs.objects.filter(result=ref_result_id, apply=True)
        if sqag_qs_results.exists():
            for sqag_qs_result in sqag_qs_results:

                new_ad_group_id = sqag_qs_result.new_ad_group_id
                source_ad_group_id = sqag_qs_result.source_ad_group_id
                source_ad_id = sqag_qs_result.source_ad_id
                new_ad_group = sqag_qs_result.new_ad_group
                ad_type = sqag_qs_result.ad_type
                apply = sqag_qs_result.apply
                if apply == True:
                    if int(source_ad_id) < 0:
                        continue                    

                    if ad_type == 'EXPANDED_TEXT_AD':                        
                        ad_result = self.add_expanded_text_ad(sqag_qs_result)
                    elif ad_type == 'RESPONSIVE_SEARCH_AD':
                        ad_result = self.add_responsive_search_ad(sqag_qs_result)
                    else:
                        continue
                        

                    if ad_result is not False:                                                
                        self.update_ad_group_status(new_ad_group_id, 'ENABLED')

                        if total_records == 0:
                            report_result = ReportScriptsResult.objects.create(
                                schedule=script_schedule,
                                user_id=self._user.id,
                                script_id=script_id,
                                client_customer_id=self._user.client_customer_id,
                                campaign_id=campaign_id,
                                adwords_campaign_id=adwords_campaign_id,
                                total_records=total_records,
                            )

                        final_url = sqag_qs_result.final_url
                        final_mobile_url = sqag_qs_result.final_mobile_url
                        path1 = sqag_qs_result.path1
                        path2 = sqag_qs_result.path2
                        keyword = sqag_qs_result.keyword

                        if ad_type == "EXPANDED_TEXT_AD":

                            headline1 = sqag_qs_result.headline1
                            headline2 = sqag_qs_result.headline2
                            headline3 = sqag_qs_result.headline3
                            description1 = sqag_qs_result.description1
                            description2 = sqag_qs_result.description2                        
                            
                            ReportScriptsResultSqagQs.objects.create(
                                result=report_result,
                                new_ad_group_id=new_ad_group_id,
                                source_ad_group_id=source_ad_group_id,
                                source_ad_id=source_ad_id,
                                new_ad_group=new_ad_group,                                
                                ad_type=ad_type,
                                headline1=headline1,
                                headline2=headline2,
                                headline3=headline3,
                                description1=description1,
                                description2=description2,
                                final_url=final_url,
                                final_mobile_url=final_mobile_url,
                                path1=path1,
                                path2=path2,
                                keyword=keyword,
                                apply=apply,
                                new_ad_id=ad_result['ad']['id'],
                            )
                        elif ad_type == "RESPONSIVE_SEARCH_AD":
                            headlines = sqag_qs_result.headlines
                            descriptions = sqag_qs_result.descriptions

                            ReportScriptsResultSqagQs.objects.create(
                                result=report_result,
                                new_ad_group_id=new_ad_group_id,
                                source_ad_group_id=source_ad_group_id,
                                source_ad_id=source_ad_id,
                                new_ad_group=new_ad_group,
                                ad_type=ad_type,
                                headlines=headlines,
                                descriptions=descriptions,
                                final_url=final_url,
                                final_mobile_url=final_mobile_url,
                                path1=path1,
                                path2=path2,
                                keyword=keyword,
                                apply=apply,
                                new_ad_id=ad_result['ad']['id'],                         
                            )

                        total_records +=1
                        sqag_qs_result.apply_status=True
                        sqag_qs_result.save()
        
        if total_records > 0:
            ReportScriptsResult.objects.filter(pk=report_result.id).update(total_records=total_records)
        
        return {
            'total_records': total_records,
        }
    

    def get_account_safe_words(self):
        
        results = ReportScriptsSafeWords.objects.filter(user_id=self._user.id, client_customer_id=self._user.client_customer_id)
        if results.exists():
            for result in results:

                return result.safe_words

        return False
    
    def get_biddable_product_groups(self, adwords_campaign_id, ad_group_id):

        offset = 0
        PAGE_SIZE = 1000
        selector = {
            'fields': ['Id', 'AdGroupName', 'CriteriaType', 'CpcBid', 'CaseValue'],
            'predicates': [
                {
                    'field': 'CampaignId',
                    'operator': 'EQUALS',
                    'values': [adwords_campaign_id]
                },
                {
                    'field': 'AdGroupId',
                    'operator': 'EQUALS',
                    'values': [ad_group_id]
                },
                {
                    'field': 'CriteriaType',
                    'operator': 'EQUALS',
                    'values': ['PRODUCT_PARTITION']
                },
                {
                    'field': 'Status',
                    'operator': 'EQUALS',
                    'values': ['ENABLED']
                },
            ],
            'paging': {
                'startIndex': str(offset),
                'numberResults': str(PAGE_SIZE)
            },
            'ordering': [{'field': 'AdGroupId', 'sortOrder': 'ASCENDING'}]
        }
        ad_group_criterion_service = self.get_adwords_service('AdGroupCriterionService')

        page = ad_group_criterion_service.get(selector)
        #print(page)
        # Display results.
        if 'entries' in page and len(page['entries']) > 0:                              
            return page['entries']                                    
        else:
            return False


    def ad_group_performance(self, adwords_campaign_id, ad_group_id):

        predicates = {
            'CampaignId': adwords_campaign_id,
            'AdGroupId': ad_group_id,
            'AdGroupStatus': 'ENABLED',
        }        
                        
        selector = {
            'fields': [
                'AdGroupName',
                'AdGroupId',
                'Conversions',
                'ConversionRate',
                'Clicks',
            ],
        }

        if predicates is not None:
            selector['predicates'] = self.format_filters(predicates, single=True)

        selector['dateRange'] = self.format_date_range(date_from, date_to)
        
        
        report = self.get_report(
            'Ad Groups report',
            'ADGROUP_PERFORMANCE_REPORT',
            date_range,
            selector,
            True,
            False
        )
        if len(report) > 0:

            return (
                {
                    'ad_group_name': ad_group_name,
                    'ad_group_id': ad_group_id,
                    'conversions': self.cast(conversions, int),
                    'conversion_rate': self.percentage(conversion_rate),
                    'clicks': int(clicks),
                }
                for (
                    ad_group_name,
                    ad_group_id,
                    conversions,
                    conversion_rate,
                    clicks,    
                ) in report
            )
        else:
            return False

        
    def product_group_performance(self, adwords_campaign_id, ad_group_id, criterion_id, date_from, date_to):

        date_range = 'CUSTOM_DATE'

        predicates = {
            'CampaignId': adwords_campaign_id,
            'AdGroupId': ad_group_id,
            'Id': criterion_id,
            'AdGroupStatus': 'ENABLED',
        }        
                        
        selector = {
            'fields': [
                'AdGroupName',
                'AdGroupId',
                'Conversions',
                'ConversionRate',
                'Clicks',
            ],
        }

        if predicates is not None:
            selector['predicates'] = self.format_filters(predicates, single=True)

        selector['dateRange'] = self.format_date_range(date_from, date_to)
        
        
        report = self.get_report(
            'Criteria report',
            'CRITERIA_PERFORMANCE_REPORT',
            date_range,
            selector,
            True,
            False
        )
        
        if len(report) > 0:
            row = report[0]
            
            return {
                    'ad_group_name': row[0],
                    'ad_group_id': row[1],
                    'conversions': self.cast(row[2], float),
                    'conversion_rate': self.cast(self.percentage(row[3]), float),
                    'clicks': int(row[4]),
                }
        else:
            return False

    
    def campaign_performance(self, adwords_campaign_id, date_from, date_to):

        date_range = 'CUSTOM_DATE'

        predicates = {
            'BaseCampaignId': adwords_campaign_id,
        }        
                        
        selector = {
            'fields': [
                'Conversions',
                'ConversionRate',
            ],
        }

        if predicates is not None:
            selector['predicates'] = self.format_filters(predicates, single=True)

        selector['dateRange'] = self.format_date_range(date_from, date_to)
        
        
        report = self.get_report(
            'Campaigns report',
            'CAMPAIGN_PERFORMANCE_REPORT',
            date_range,
            selector,
            True,
            False
        )
        if len(report) > 0:
            row = report[0]

            return {
                'conversions': self.cast(row[0], float),
                'conversion_rate': self.cast(self.percentage(row[1]), float),
            }            
        else:
            return False


    def process_log_create(self, adwords_campaign_id, is_dry_run, parameters):
        process_log = ModifierProcessLog.objects.create(
                adwords_campaign_id=adwords_campaign_id,
                is_dry_run=is_dry_run,
                parameters=parameters,
        )
        return process_log
       
    def process_log_complete(self, process_log):
        process_log.set_complete()

    def run_modifier(self, modifier, api_adapter, process_log, campaign_id, **parameters):
        modifier_log = process_log.start_modifier_log(modifier.name)

        modifier.run(api_adapter, campaign_id, log=modifier_log, **parameters)

        modifier_log.set_complete()


def test_mail():
    keywords = 'test keywords'
    campaign_name = 'Website traffic-Search-1'
    message = 'Campaign name: {campaign_name} <br />The following Keywords are over TCPA:<br />{keywords}'.format(
                keywords=keywords,
                campaign_name=campaign_name
                )
    send_mail(
        'Captivise - Alert: Keywords Over TCPA',
        message,
        settings.DEFAULT_FROM_EMAIL,
        ['vil@expedux.com'],
        fail_silently=False,
        html_message=message,
    )