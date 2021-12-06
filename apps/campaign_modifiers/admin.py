from django.contrib import admin

from .models import ModifierLog, ModifierProcessLog, KeywordActionLog, KeywordEvent


class ModifierLogInline(admin.TabularInline):
    model = ModifierLog
    extra = 0
    ordering = ('-started_at', )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class KeywordActionLogInline(admin.TabularInline):
    model = KeywordActionLog
    extra = 0
    ordering = ('adwords_keyword_id', )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class KeywordEventInline(admin.TabularInline):
    model = KeywordEvent
    extra = 0
    ordering = ('adwords_keyword_id', )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ModifierProcessLog)
class ModifierProcessLogAdmin(admin.ModelAdmin):
    list_display = ('adwords_campaign_id', 'started_at', 'completed_at', 'status', )
    readonly_fields = ('started_at', 'completed_at', 'status', 'is_dry_run', 'error', )
    date_hierarchy = 'started_at'
    ordering = ('-started_at', )
    inlines = (
        ModifierLogInline,
        KeywordEventInline,
    )


@admin.register(ModifierLog)
class ModifierLogAdmin(admin.ModelAdmin):
    list_display = ('modifier_name', 'campaign_id', 'started_at', 'completed_at', )
    readonly_fields = ('modifier_process_log', 'modifier_name', 'started_at', 'completed_at', )
    date_hierarchy = 'started_at'
    ordering = ('-started_at', )
    inlines = (
        KeywordActionLogInline,
    )

    def campaign_id(self, obj):
        return obj.modifier_process_log.adwords_campaign_id
