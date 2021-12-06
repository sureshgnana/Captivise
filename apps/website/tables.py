import locale

from django_tables2 import Column


class CurrencyColumn(Column):

    def render(self, value):
        return locale.currency(value, grouping=True)


class PercentColumn(Column):

    def render(self, value):
        return '{value}%'.format(value=value)
