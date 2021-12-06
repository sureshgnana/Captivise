import logging

from celery.task import task

from adwords.exceptions import TooEarlyError

from .models import ReportScripts, ReportScriptsSchedule, ReportScriptsResult
from .scripts import ScriptAdapter
from accounts.models import User
from reports.models import Campaign
from django.utils import timezone
from celery.task.schedules import crontab
from celery.decorators import periodic_task

@periodic_task(run_every=(crontab(minute='0', hour='1')), name='report_scripts.run_scripts')
def run_scripts():
    logger = logging.getLogger('celery')

    script_schedules = ReportScriptsSchedule.objects.filter(status=False)    

    for script_schedule in script_schedules:

        schedule_id = script_schedule.id
        script_id = script_schedule.script_id
        campaign_id = script_schedule.campaign_id
        user_obj = User.objects.get(pk=script_schedule.user_id)
        campaign_obj = Campaign.objects.get(pk=campaign_id)
       
        SA = ScriptAdapter(user_obj)

        if campaign_obj.is_managed == False:
            continue
                
        if script_id == 1:
            result = SA.pause_empty_adgroups(script_schedule, campaign_obj)
        elif script_id == 2:
            result = SA.pause_zero_conversion_keywords(script_schedule, campaign_obj)
        elif script_id == 3:
            result = SA.over_cpa_alert(script_schedule, campaign_obj)
        elif script_id == 4:
            result = SA.tcpa_bids(script_schedule, campaign_obj, 30)
        elif script_id == 5:
            result = SA.tcpa_bids(script_schedule, campaign_obj, 60)
        elif script_id == 6:            
            result = SA.tcpa_bids(script_schedule, campaign_obj, 90)
        elif script_id == 7:            
            result = SA.tcpa_bids(script_schedule, campaign_obj, 180)  
        elif script_id == 8:            
            result = SA.tcpa_bids(script_schedule, campaign_obj, 365)
        elif script_id == 9:            
            result = SA.tcpa_bids(script_schedule, campaign_obj, 730)
        elif script_id == 10:            
            result = SA.tcpa_bids(script_schedule, campaign_obj, 1095)
        elif script_id == 11:            
            result = SA.sqag_generator(script_schedule, campaign_obj)
        elif script_id == 12:            
            result = SA.sqag_qs_apply(script_schedule, campaign_obj)
        elif script_id == 13:            
            result = SA.quality_score_search(script_schedule, campaign_obj)
        elif script_id == 14:            
            result = SA.sqag_qs_apply(script_schedule, campaign_obj)
        elif script_id == 15:            
            result = SA.top_of_page_and_first_page_bid(script_schedule, campaign_obj)
        elif script_id == 16:            
            result = SA.zero_spend_alert(script_schedule, campaign_obj)
        elif script_id == 17:            
            result = SA.automated_negatives(script_schedule, campaign_obj) 
        elif script_id == 18:            
            result = SA.ad_schedule_creation(script_schedule, campaign_obj)
        elif script_id == 19:            
            result = SA.shopping_automated_product_listing_bids(script_schedule, campaign_obj, user_obj)
        elif script_id == 20:            
            result = SA.shopping_sq_title_description_match(script_schedule, campaign_obj, user_obj)
            

        if result is not False  and 'total_records' in result and  result['total_records'] > 0 :
            script_schedule.status = ReportScriptsSchedule.STATUS_COMPLETE
        else:
            script_schedule.status = ReportScriptsSchedule.STATUS_NO_RESULTS
        
        
        script_schedule.completed_at = timezone.now()
        script_schedule.save()