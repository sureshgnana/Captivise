DEBUG = True

ALLOWED_HOSTS = (
    'app.captivise.com',
    '.jpclients.com',
)


# Database
# https://docs.djangoproject.com/en/1.10/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'captivise',
        'USER': 'jp74',
        'PASSWORD': 'BbK8of$R9%rtCHf6D*RXwKse6pPf3!1e',
        'HOST': '127.0.0.1',
        'PORT': '',
    },
}


# Email

EMAIL_HOST = 'mailtrap.io'
EMAIL_HOST_USER = '1999352a376c5581b'
EMAIL_HOST_PASSWORD = '3f2730828b18f1'
EMAIL_PORT = '2525'


# Googleads
ADWORDS_DEVELOPER_TOKEN = 'WyUU6lrzentIzanlF7BzQQ'
ADWORDS_CLIENT_ID = '451839149375-d7cujajfgfgb2g7s2abp5l7pnuvi2vn1.apps.googleusercontent.com'
ADWORDS_SECRET_KEY = 'PaZFjB-9PVaHG66tGJC1nNhM'
ANALYTICS_TID = 'UA-107932867-1'


# django-compressor
COMPRESS_ENABLED = True


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
ECOM6_CALLBACK_HOST = 'captivise.jpclients.com'


# Determines whether the environment should be able to make google ads
# changes.
SHOULD_MUTATE_GOOGLE_ADS = False
