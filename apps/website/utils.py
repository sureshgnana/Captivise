import decimal
import json

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from googleads import oauth2, adwords
from django.db.models import Q

from .models import SiteConfig, CmsContent


def get_adwords_client(refresh_token, client_customer_id=None):
    client_id = settings.ADWORDS_CLIENT_ID
    client_secret = settings.ADWORDS_SECRET_KEY
    developer_token = settings.ADWORDS_DEVELOPER_TOKEN
    user_agent = 'Captivise'

    oauth2_client = oauth2.GoogleRefreshTokenClient(client_id, client_secret, refresh_token)

    return adwords.AdWordsClient(
        developer_token,
        oauth2_client,
        user_agent,
        client_customer_id=client_customer_id,
    )


# See https://stackoverflow.com/a/1960649/930517
class JSONDecimalEncoder(json.JSONEncoder):

    def default(self, o):
        if isinstance(o, decimal.Decimal):
            return float(o)
        return super().default(o)


def get_new_user_alert_email():
    try:
        site_config = SiteConfig.objects.get()
    except SiteConfig.DoesNotExist:
        raise ImproperlyConfigured('No site config exists.')
    except SiteConfig.MultipleObjectsReturned:
        # Should not be able to get here without database manipulation.
        raise ImproperlyConfigured('Too many site configs exist.')

    email_to = site_config.new_user_alert_email
    if email_to is not None:
        return email_to

    raise ImproperlyConfigured('No new user alert email set.')


def months_difference(date_from, date_to):
    return ((date_to.year * 12) + date_to.month) - ((date_from.year * 12) + date_from.month)

def cms_page_content(slug, id=0):
    cms_content = CmsContent.objects.get(
        Q(slug=slug) | Q(pk=id)
    )
    return cms_content   


