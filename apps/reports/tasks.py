from celery import shared_task
from celery.task import task

import datetime
import celery
import logging
import os
from celery.task.schedules import crontab
from celery.decorators import periodic_task





#@shared_task
def print_demo():
    # Demo to show periodic tasks are setup correctly
    print('PRINT DEMO')
    
@periodic_task(run_every=(crontab(minute='3', hour='0')), name='reports.tasks.update_file')
def update_file():
      logging.basicConfig( level=logging.DEBUG, filename='/var/www/appcaptivise/debug.log')
      # Demo to show periodic tasks are setup correctly
      f = open("/var/www/appcaptivise/apps/reports/sample.txt", "a")
      now = datetime.datetime.now()
      date_time = now.strftime("%m/%d/%Y, %H:%M:%S")
      f.write(date_time + "Now the file has more content!")

      f.write("\n")
      f.close()

    
if __name__ == "__main__":
    update_file()
