from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import ugettext_lazy as _

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = (
        (None, {'fields': ('email', 'password', )}),
        (_('Personal info'), {'fields': ('first_name', 'last_name', )}),
        (_('Adwords'), {'fields': ('is_adwords_dry_run', )}),
        (_('Analytics'), {'fields': ('google_analytics_client_id', )}),
        (_('Payment'), {'fields': ('is_freerolled', 'payment_percent')}),
        (_('Permissions'), {'fields': (
            'is_active',
            'is_staff',
            'is_superuser',
            'groups',
            'user_permissions',
        )}),
        (_('Important dates'), {'fields': ('last_login', 'date_joined', )}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide', ),
            'fields': (
                'email',
                'password1',
                'password2',
                'is_adwords_dry_run',
                'is_freerolled',
            ),
        }),
    )
    list_display = ('email', 'first_name', 'last_name', 'is_staff', )
    readonly_fields = ('google_analytics_client_id', )
    search_fields = ('first_name', 'last_name', 'email', 'google_analytics_client_id', )
    ordering = ('email', )
