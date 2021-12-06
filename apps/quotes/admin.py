import decimal

from django.contrib import admin

from .models import Quote


@admin.register(Quote)
class QuoteAdmin(admin.ModelAdmin):
    list_display = (
        'created_at',
        'user_first_name',
        'user_last_name',
        'monthly_adwords_spend',
        'quote_str',
        'is_accepted',
    )
    exclude = ('quote', )
    list_filter = ('is_accepted', )
    date_hierarchy = 'created_at'
    ordering = ('-created_at', )
    actions = None

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields if f.name not in ('id', 'quote', )] + [
            'quote_str',
        ]

    def quote_str(self, obj):
        return decimal.Decimal(obj.quote / 10**6).quantize(decimal.Decimal('0.01'))
    quote_str.short_description = 'quote'
