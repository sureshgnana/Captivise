from django.contrib import admin

from .models import SiteConfig, CmsContent

@admin.register(CmsContent)
class CmsContentAdmin(admin.ModelAdmin):

    def has_add_permission(self, request):
        return True