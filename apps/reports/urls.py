from django.conf.urls import url

from .views import (
    DashboardView,
    CampaignListView,
    CampaignKeywordView,
    CampaignRunsView,
    CampaignSettingsView,
    CampaignReportScriptsScheduleView,
    CampaignReportScriptsEnableView,
    CampaignReportScriptsDisableView,
    CampaignReportScriptsStatusView,
    CampaignReportScriptsCategoryView,
    CmsContentView,
)

urlpatterns = [
    url(r'^$', DashboardView.as_view(), name='reports_dashboard'),
    url(r'^campaigns/$', CampaignListView.as_view(), name='reports_campaign_list'),
    url(
        r'^campaigns/(?P<campaign_id>\d+)/$',
        CampaignKeywordView.as_view(),
        name='reports_campaign_detail',
    ),
    url(
        r'^campaigns/(?P<campaign_id>\d+)/runs/$',
        CampaignRunsView.as_view(),
        name='reports_campaign_detail_runs',
    ),
    url(
        r'^campaigns/(?P<campaign_id>\d+)/settings/$',
        CampaignSettingsView.as_view(),
        name='reports_campaign_detail_settings',
    ),
    url(r'^campaigns/report_scripts/schedule$', CampaignReportScriptsScheduleView.as_view(), name='campaign_report_scripts_schedule'),
    url(r'^campaigns/report_scripts/enable$', CampaignReportScriptsEnableView.as_view(), name='campaign_report_scripts_enable'),
    url(r'^campaigns/report_scripts/disable$', CampaignReportScriptsDisableView.as_view(), name='campaign_report_scripts_disable'),
    url(r'^campaigns/report_scripts/status$', CampaignReportScriptsStatusView.as_view(), name='campaign_report_scripts_status'),
    #01/12/20
    url(r'^cms/(?P<cms_id>\d+)/$', CmsContentView.as_view(), name='get_cms_content'),
    url(r'^campaigns/report_scripts/category$', CampaignReportScriptsCategoryView.as_view(), name='campaign_report_scripts_category'),
]
