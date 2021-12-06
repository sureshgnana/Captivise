import decimal

from django.contrib import admin

from .models import ReportScripts,ReportScriptsCategory
from django import forms



@admin.register(ReportScripts)
class ReportScriptsAdmin(admin.ModelAdmin):
    list_display = (
        'name','status'
    )    
    list_filter = ('name', 'status', )
    ordering = ('name', 'status', )
    actions = None    

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
        

@admin.register(ReportScriptsCategory)
class ReportScriptsCategoryAdmin(admin.ModelAdmin):
    list_display = (
        'category_name',
    )    
    list_filter = ('category_name', )
    actions = None    


    def has_delete_permission(self, request, obj=None):
        return False
