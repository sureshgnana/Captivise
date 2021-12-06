from abc import ABCMeta, abstractmethod
from datetime import date, datetime, time, timedelta, timezone
import traceback

from .models import ModifierProcessLog


def get_utc_now():
    return datetime.now(timezone.utc)


class ModifierBase(metaclass=ABCMeta):

    @property
    @abstractmethod
    def name(self):
        pass

    @abstractmethod
    def run(self, api_adapter, campaign_id, **parameters):
        pass

    @staticmethod
    def get_x_days_ago(days):
        return get_utc_now() - timedelta(days=days)

    @staticmethod
    def format_date(date):
        return date.strftime('%Y%m%d')

    def get_date_range_from_now(self, days):
        return {
            'min': self.format_date(self.get_x_days_ago(days)),
            'max': self.format_date(get_utc_now()),
        }

    @staticmethod
    def should_skip_keyword(adwords_keyword_id, modifier_process_log):
        if modifier_process_log is None:
            return False

        return modifier_process_log.was_keyword_modified(adwords_keyword_id)


class ModifierProcess:
    class DuplicateModifierProcessRunForCampaign(Exception):
        pass

    def run(self, modifiers, api_adapter, campaign_id, is_dry_run, **parameters):
        today = date.today()
        today_min = datetime.combine(today, time.min)
        today_max = datetime.combine(today, time.max)
        if ModifierProcessLog.objects.filter(
                started_at__range=(today_min, today_max), adwords_campaign_id=campaign_id):

            # Defend ourselves from rogue extra celery processes.
            raise self.DuplicateModifierProcessRunForCampaign(
                'Campaign ID:  {campaign_id}'.format(campaign_id=campaign_id))

        process_log = ModifierProcessLog.objects.create(
            adwords_campaign_id=campaign_id,
            is_dry_run=is_dry_run,
            parameters=parameters,
        )

        try:
            for modifier in modifiers:
                self.run_modifier(modifier, api_adapter, process_log, campaign_id, **parameters)
        except:
            error = traceback.format_exc()
            process_log.set_failed(error)
            raise
        else:
            process_log.set_complete()

    def run_modifier(self, modifier, api_adapter, process_log, campaign_id, **parameters):
        modifier_log = process_log.start_modifier_log(modifier.name)

        modifier.run(api_adapter, campaign_id, log=modifier_log, **parameters)

        modifier_log.set_complete()
