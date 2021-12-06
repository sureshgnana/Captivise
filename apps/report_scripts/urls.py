from django.conf.urls import url

from .views import (
    ReportScriptsView,
    ReportScriptsSchedulesView,
    ReportScriptsResultsView,
    ReportScriptsSchedulesRemoveView,
    ReportScriptsResultsDetailView,
    ReportScriptsResultsDetailUpdate,
    ReportScriptsResultsDetailSchedule,
    ReportScriptsSafeWordsView,
    ReportScriptsResultsSingleView,
)

urlpatterns = [
    url(r'^reports/$', ReportScriptsView.as_view(), name='report_scripts'),
    url(
        r'^reports/schedules/$',
        ReportScriptsSchedulesView.as_view(),
        name='report_scripts_schedules',
    ),
    url(
        r'^reports/results/$',
        ReportScriptsResultsView.as_view(),
        name='report_scripts_results',
    ),
    url(
        r'^reports/schedules/remove$',
        ReportScriptsSchedulesRemoveView.as_view(),
        name='report_scripts_schedules_remove',
    ),
    url(
        r'^reports/results/(?P<result_id>\d+)/$',
        ReportScriptsResultsDetailView.as_view(),
        name='report_scripts_results_detail',
    ), 
    url(
        r'^reports/results/updateresults$',
        ReportScriptsResultsDetailUpdate.as_view(),
        name='report_scripts_results_update'
    ),
    url(
        r'^reports/results/scheduleresults$',
        ReportScriptsResultsDetailSchedule.as_view(),
        name='report_scripts_results_schedule'
    ),
    url(
        r'^reports/safe-words$',
        ReportScriptsSafeWordsView.as_view(),
        name='report_scripts_safe_words',
    ),
    url(
        r'^reports/results/(?P<result_id>\d+)/detail/$',
        ReportScriptsResultsSingleView.as_view(),
        name='report_scripts_results_single',
    ),
]
