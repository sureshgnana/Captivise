from django.db import models
from django.utils.timezone import now

from jsonfield import JSONField

from model_utils import Choices

from .managers import KeywordActionLogManager
from report_scripts.models import ReportScripts, ReportScriptsSchedule, ReportScriptsResult


class ModifierProcessLog(models.Model):
    STATUS_CHOICES = Choices(
        ('running', 'Running'),
        ('complete', 'Complete'),
        ('failed', 'Failed'),
    )

    adwords_campaign_id = models.CharField(max_length=255)
    is_dry_run = models.BooleanField()
    parameters = JSONField()
    started_at = models.DateTimeField(default=now)
    completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=50,
        choices=STATUS_CHOICES,
        default=STATUS_CHOICES.running,
    )
    error = models.TextField(blank=True)

    def __str__(self):
        return 'Log for campaign {}'.format(self.adwords_campaign_id)

    def set_running(self):
        self.status = self.STATUS_CHOICES.running
        self.started_at = now()
        self.save()

    def set_complete(self):
        self.de_normalise_logs()

        self.status = self.STATUS_CHOICES.complete
        self.completed_at = now()
        self.save()

    def set_failed(self, error):
        self.status = self.STATUS_CHOICES.failed
        self.completed_at = now()
        self.error = error
        self.save()

    def start_modifier_log(self, modifier_name):
        return self.modifier_logs.create(modifier_name=modifier_name)

    def de_normalise_logs(self):
        keyword_actions = KeywordActionLog.objects \
            .filter(modifier_log__modifier_process_log=self) \
            .order_by('adwords_keyword_id', 'created_at')

        keyword_event_data = {}
        for keyword_action in keyword_actions:
            if keyword_event_data.get('adwords_keyword_id') != keyword_action.adwords_keyword_id:
                if keyword_event_data:
                    # Save new event.
                    self.keyword_events.create(**keyword_event_data)

                # Initialise event.
                keyword_event_data = {
                    'adwords_keyword_id': keyword_action.adwords_keyword_id,
                    'action': keyword_action.action,
                    'previous_max_cpc': keyword_action.previous_max_cpc,
                    'new_max_cpc': keyword_action.new_max_cpc,
                }

            if keyword_action.action != keyword_action.ACTION_CHOICES.no_action:
                # If an action happened it takes precedence over the
                # previous one.
                keyword_event_data['action'] = keyword_action.action
                keyword_event_data['new_max_cpc'] = keyword_action.new_max_cpc
            keyword_event_data['created_at'] = keyword_action.created_at

        if keyword_event_data:
            self.keyword_events.create(**keyword_event_data)

    def was_keyword_modified(self, adwords_keyword_id):
        count = KeywordActionLog.objects \
            .get_modified() \
            .filter(modifier_log__modifier_process_log=self) \
            .filter(adwords_keyword_id=adwords_keyword_id) \
            .count()
        return count > 0


class ModifierLog(models.Model):
    modifier_process_log = models.ForeignKey(
        'ModifierProcessLog',
        related_name='modifier_logs',
        on_delete=models.CASCADE,
    )
    modifier_name = models.CharField(max_length=100)
    started_at = models.DateTimeField(default=now)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return 'Log for {}'.format(self.modifier_name)

    def set_running(self):
        self.started_at = now()
        self.save()

    def set_complete(self, script_result_id=None):
        self.completed_at = now()
        self.script_result_id = script_result_id
        self.save()

    def log_increased_keyword_cpc(
            self, keyword_id, previous_max_cpc, new_max_cpc, keyword, ad_group_name, conversion_rate, modifier_data=None):
        return self.keyword_action_logs.field.remote_field.related_model.log_increased_keyword_cpc(
            self,
            keyword_id,
            previous_max_cpc,
            new_max_cpc,
            keyword,
            ad_group_name,
            conversion_rate,
            modifier_data,
        )

    def log_decreased_keyword_cpc(
            self, keyword_id, previous_max_cpc, new_max_cpc, keyword, ad_group_name, conversion_rate, modifier_data=None):
        return self.keyword_action_logs.field.remote_field.related_model.log_decreased_keyword_cpc(
            self,
            keyword_id,
            previous_max_cpc,
            new_max_cpc,
            keyword,
            ad_group_name,
            conversion_rate,
            modifier_data,
        )

    def log_ignored_keyword(self, keyword_id, max_cpc, keyword, ad_group_name, conversion_rate, modifier_data=None):
        return self.keyword_action_logs.field.remote_field.related_model.log_ignored_keyword(
            self,
            keyword_id,
            max_cpc,
            keyword,
            ad_group_name,
            conversion_rate,
            modifier_data,
        )

    def log_paused_keyword(self, keyword_id, max_cpc, keyword, ad_group_name, conversion_rate, modifier_data=None):
        return self.keyword_action_logs.field.remote_field.related_model.log_paused_keyword(
            self,
            keyword_id,
            max_cpc,
            keyword,
            ad_group_name,
            conversion_rate,
            modifier_data=modifier_data,            
        )


class KeywordActionLogBase(models.Model):
    ACTION_CHOICES = Choices(
        ('increased_cpc', 'Increased CPC'),
        ('decreased_cpc', 'Decreased CPC'),
        ('no_action', 'No action'),
        ('paused', 'Paused'),
    )
    CPC_ACTIONS = (
        ACTION_CHOICES.increased_cpc,
        ACTION_CHOICES.decreased_cpc,
    )

    created_at = models.DateTimeField(default=now)
    adwords_keyword_id = models.CharField(max_length=255)  # TODO: How long will this actually be?
    keyword = models.CharField('Keyword', max_length=255, null=True, blank=True)
    ad_group_name = models.CharField('Ad Group Name', max_length=255, null=True, blank=True)
    conversion_rate = models.DecimalField(max_digits=12,  decimal_places=2)
    action = models.CharField(max_length=50, choices=ACTION_CHOICES, db_index=True)
    previous_max_cpc = models.PositiveIntegerField()
    new_max_cpc = models.PositiveIntegerField()
    modifier_data = JSONField(
        null=True, help_text='Collection of variables used in modifiers. Helpful for debugging.')

    class Meta:
        abstract = True

    def __str__(self):
        return 'Action for {}: {}'.format(self.adwords_keyword_id, self.action)


class KeywordActionLog(KeywordActionLogBase):
    modifier_log = models.ForeignKey(
        'ModifierLog',
        related_name='keyword_action_logs',
        on_delete=models.CASCADE,
    )
    result = models.ForeignKey(
        'report_scripts.ReportScriptsResult',
        verbose_name='Result Id',
        null=True,
        blank=True,
        on_delete=models.SET_NULL, related_name="result_keyword",
    )

    objects = KeywordActionLogManager()

    @classmethod
    def log_increased_keyword_cpc(
            cls, log, keyword_id, previous_max_cpc, new_max_cpc, keyword, ad_group_name, conversion_rate, modifier_data=None):
        return cls.objects.create(
            modifier_log=log,
            adwords_keyword_id=keyword_id,
            action=KeywordActionLog.ACTION_CHOICES.increased_cpc,
            previous_max_cpc=previous_max_cpc,
            new_max_cpc=new_max_cpc,
            keyword=keyword,
            ad_group_name=ad_group_name,
            conversion_rate=conversion_rate,
            modifier_data=modifier_data,
            
        )

    @classmethod
    def log_decreased_keyword_cpc(
            cls, log, keyword_id, previous_max_cpc, new_max_cpc, keyword, ad_group_name, conversion_rate, modifier_data=None):
        return cls.objects.create(
            modifier_log=log,
            adwords_keyword_id=keyword_id,
            action=KeywordActionLog.ACTION_CHOICES.decreased_cpc,
            previous_max_cpc=previous_max_cpc,
            new_max_cpc=new_max_cpc,
            keyword=keyword,
            ad_group_name=ad_group_name,
            conversion_rate=conversion_rate,
            modifier_data=modifier_data,
            
        )

    @classmethod
    def log_ignored_keyword(cls, log, keyword_id, max_cpc, keyword, ad_group_name, conversion_rate, modifier_data=None):
        return cls.objects.create(
            modifier_log=log,
            adwords_keyword_id=keyword_id,
            action=KeywordActionLog.ACTION_CHOICES.no_action,
            previous_max_cpc=max_cpc,
            new_max_cpc=max_cpc,
            keyword=keyword,
            ad_group_name=ad_group_name,
            conversion_rate=conversion_rate,
            modifier_data=modifier_data,
            
        )

    @classmethod
    def log_paused_keyword(cls, log, keyword_id, max_cpc, keyword, ad_group_name, conversion_rate, modifier_data=None):
        return cls.objects.create(
            modifier_log=log,
            adwords_keyword_id=keyword_id,
            action=KeywordActionLog.ACTION_CHOICES.paused,
            previous_max_cpc=max_cpc,
            new_max_cpc=max_cpc,
            keyword=keyword,
            ad_group_name=ad_group_name,
            conversion_rate=conversion_rate,
            modifier_data=modifier_data,            
        )


class KeywordEvent(KeywordActionLogBase):
    """
    De-normalised data from KeywordActionLog: one event per keyword
    per modifier process log. This is useful for further analysis,
    such as on the dashboard.
    """
    modifier_process_log = models.ForeignKey(
        'ModifierProcessLog',
        related_name='keyword_events',
        on_delete=models.CASCADE,
    )
