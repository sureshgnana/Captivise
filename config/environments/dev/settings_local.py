DEBUG = True

ALLOWED_HOSTS = ('*', )


# Database
# https://docs.djangoproject.com/en/1.10/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'captivise',
        'USER': 'root',
        'PASSWORD': '',
        'HOST': '127.0.0.1',
        'PORT': '',
    },
}


# Googleads

ADWORDS_DEVELOPER_TOKEN = '50FG59WGOJOWg6cCFfT-kA'
ADWORDS_CLIENT_ID = '45353254968-5p9bbihsc6vt9sbtlivd7g3l2j78829j.apps.googleusercontent.com'
ADWORDS_SECRET_KEY = 'qR-129WwU6BUZafw9TfQb01L'
ANALYTICS_TID = 'UA-107932867-1'


# django-compressor
COMPRESS_ENABLED = False


# Payment settings
ECOM6_PAYMENT_OPTIONS = {
    'default': {
        'merchant_ID': 103237,
        'secret_key': 'Agency12Also14Entity',
        'country_code': 'gb',
    },
    'continuous_authority': {
        'merchant_ID': 103237,
        'secret_key': 'Agency12Also14Entity',
        'country_code': 'gb',
    },
}

ECOM6_CALLBACK_SCHEME = 'http'
ECOM6_CALLBACK_HOST = 'localhost'  # Switch this out for your ngrok hostname.


# Determines whether the environment should be able to make google ads
# changes.
SHOULD_MUTATE_GOOGLE_ADS = False
