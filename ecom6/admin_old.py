from django.contrib import admin

from .models import Response


@admin.register(Response)
class ResponseAdmin(admin.ModelAdmin):
    readonly_fields = [field.name for field in Response._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
