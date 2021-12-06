# TODO:  Loading services in serial has poor performance, especially
# when doing it more than once.  Can we cache them globally somehow?
# They won't change per user without the server resetting, so
# repeatedly loading the endpoint info is wasteful.

from collections import defaultdict, namedtuple
import csv
import datetime
import logging
import decimal
from functools import wraps
from urllib.error import HTTPError
from xml.etree import ElementTree

from django.conf import settings
from django.db import connection
from django.db.utils import OperationalError

from campaign_modifiers.models import KeywordEvent
from reports.models import Campaign
from reports.utils import decimal_to_micro_amount
from website.utils import get_adwords_client

from .exceptions import NonManagerAccountSelected, UserNotLinkedError
import re


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


class Adapter:
    adwords_api_version = 'v201809'

    def __init__(self, user):
        self._user = user
        self._cached_values = {}
        self.is_dry_run = user.is_adwords_dry_run

    @property
    def should_mutate(self):
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
                if isinstance(value, list):
                    formatted_filter = {
                        'field': field,
                        'operator': operator,
                        'values': [*value],
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
            include_zero_impressions=include_zero_impressions
        )


        report = csv.reader((line.decode() for line in response))
        
        if skip_headers:
            next(report)

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
        advertising_channel_type = campaign.pop('advertising_channel_type')
        instance, _ = Campaign.objects.update_or_create(
            adwords_campaign_id=adwords_campaign_id,
            client_customer_id=self._user.client_customer_id,
            advertising_channel_type=advertising_channel_type,
            defaults={'owner': self._user, 'title': title, 'client_customer_id':self._user.client_customer_id, 'advertising_channel_type':advertising_channel_type, },
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
        #adwords_campaign_ids_2 = ', '.join("'{0}'".format(w) for w in adwords_campaign_ids)

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
                'AdvertisingChannelType'
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
                'click_assisted_conversions': int(click_assisted_conversions),
                'advertising_channel_type': advertising_channel_type,
            }
            for (
                id_,
                title,
                status,
                budget_id,
                click_assisted_conversions,
                advertising_channel_type,
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

                initial[key] += decimal.Decimal(value)

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
            average_columns=('cpc', 'avg_conversion_value', 'roi', 'cost_sales', ),
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
                'ConversionRate',
                'ConversionValue',
                'AllConversionValue',
                'Clicks',
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

        def percentage(value):
            return decimal.Decimal(value[:-1])

        by_date = defaultdict(
            lambda: {'conversions': decimal.Decimal(), 'cpc': decimal.Decimal(), 'cost': decimal.Decimal(), 'conversion_rate': decimal.Decimal(), 'conversion_value': decimal.Decimal(), 'avg_conversion_value': decimal.Decimal(), 'all_conversion_value': decimal.Decimal(), 'roi': decimal.Decimal(),'cost_sales': decimal.Decimal(), 'clicks': decimal.Decimal(),})
        for click_assisted_conversions, date, cost, conversion_rate, conversion_value, all_conversion_value, clicks in report:
            if cast_dates:
                date = datetime.datetime.strptime(date, '%Y-%m-%d').date()
            by_date[date]['conversions'] += decimal.Decimal(click_assisted_conversions)
            by_date[date]['cost'] += int(cost)            
            by_date[date]['conversion_value'] += decimal.Decimal(conversion_value)
            by_date[date]['all_conversion_value'] += decimal.Decimal(all_conversion_value)
            by_date[date]['clicks'] += int(clicks)
            if by_date[date]['conversions']:
                cost = by_date[date]['cost']/10**6
                by_date[date]['cpc'] = (cost / by_date[date]['conversions']) if cost != 0 else 0                
                by_date[date]['avg_conversion_value'] = (by_date[date]['conversion_value'] / by_date[date]['conversions']) if by_date[date]['conversions'] != 0 else 0
                all_conversion_value = by_date[date]['all_conversion_value']
                by_date[date]['roi'] = ((all_conversion_value - cost) / cost) * 100 if cost != 0 else 0
                by_date[date]['cost_sales'] = (cost / all_conversion_value) * 100 if all_conversion_value != 0 else 0
                by_date[date]['conversion_rate'] = (by_date[date]['conversions'] / by_date[date]['clicks']) * 100 if by_date[date]['clicks'] != 0 else 0  

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
            return decimal.Decimal(value[:-1])  # Cut off the '%'.

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
                'max_cpc': self.find_number(max_cpc, int),
                'click_assisted_conversions': int(click_assisted_conversions),
                'conversion_rate': percentage(conversion_rate),
                'cost': int(cost),
                'impressions': int(impressions),
                'click_through_rate': percentage(click_through_rate),
                'cpa': int(cpa),
                'status': status,
                'value_per_conversion': decimal_to_micro_amount(
                    cast(value_per_conversion, decimal.Decimal)),
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

    
    def get_adgroups(self):
        filters = {'AdGroupStatus': 'ENABLED'}
        resultall = {}
        adgroups_selector = {
            'fields': [
                'AdGroupId',
                'AdGroupName',
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
                'ad_group_id': int(ad_group_id),
                'ad_group_name': str(ad_group_name),
            }
            for (
                ad_group_id,
                ad_group_name,
            ) in report
        )

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