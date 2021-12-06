from django.db.models.manager import BaseManager, QuerySet


class KeywordActionLogQuerySet(QuerySet):

    def get_modified(self):
        return self.exclude(action=self.model.ACTION_CHOICES.no_action)


class KeywordActionLogManager(BaseManager.from_queryset(KeywordActionLogQuerySet)):
    pass
