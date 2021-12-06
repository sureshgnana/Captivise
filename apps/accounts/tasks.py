import logging

from celery.task import task

from adwords.exceptions import TooEarlyError

from .models import User
from celery.task.schedules import crontab
from celery.decorators import periodic_task

@periodic_task(run_every=(crontab(minute='0', hour='6')), name='accounts.charge_users')
def charge_users():
    #pk=37
    logger = logging.getLogger('celery')

    for user in User.objects.filter(is_active=True):
        try:
            user.take_payment_if_required()
        except TooEarlyError as e:
            # Retry in an hour.
            #self.retry(countdown=60*60, exc=e)
            logger.exception('Failed to take payment for user {pk}'.format(pk=user.pk))
            break
        except Exception:
            logger.exception('Failed to take payment for user {pk}'.format(pk=user.pk))

@periodic_task(run_every=(crontab(minute='10', hour='7')), name='accounts.check_card_expiries')
def check_card_expiries():
  try:
    def alert_failed(user):
        logging.debug('Failed to alert user {pk} of imminent card expiry'.format(pk=user.pk))

    User.objects.lock_out_users_with_expired_cards()
    User.objects.alert_users_of_imminent_card_expiry(loghook=alert_failed)
  except Exception as e:
     logging.error(e, exc_info=True)


#@task(name='accounts.alert_user_registered')
def alert_user_registered(user_pk):
    User.objects.get(pk=user_pk).alert_user_registered()
