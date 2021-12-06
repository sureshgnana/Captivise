DEBUG = True

ALLOWED_HOSTS = (
    '127.0.0.1',
    '54.37.1.151',
    'appcaptivise.expedux.in'
)


# Database
# https://docs.djangoproject.com/en/1.10/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'captivise',
        'USER': 'rbsuser',
        'PASSWORD': 'Rbs@123',
        'HOST': '94.237.81.230',
        'PORT': '',
    },
}


# Email

EMAIL_HOST = 'smtp.sendgrid.net'
EMAIL_HOST_USER = 'apikey'
EMAIL_HOST_PASSWORD = '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'
EMAIL_PORT = '25'


# Googleads
ADWORDS_DEVELOPER_TOKEN = 'RAPXaNRd9Qsg08dOizs9NA'
ADWORDS_CLIENT_ID = '191163205443-uq0blpjjfefo3196lb5h25t8orn34jsc.apps.googleusercontent.com'
ADWORDS_SECRET_KEY = '8brJ9WLyj8oz-HOk7RVenSwf'
ANALYTICS_TID = 'UA-107932867-1'


# django-compressor
COMPRESS_ENABLED = True


# Payment settings
ECOM6_PAYMENT_OPTIONS = {
    'default': {
        'merchant_ID': 109521,
        'secret_key': 'Talk12Top36Form',
        'country_code': 'gb',
    },
    'continuous_authority': {
        'merchant_ID': 109702,
        'secret_key': 'Talk12Top36Form',
        'country_code': 'gb',
    },
}
DATE_FORMAT = '%d-%m-%Y'
ECOM6_CALLBACK_SCHEME = 'https'
ECOM6_CALLBACK_HOST = 'appcaptivise.expedux.in'


# Determines whether the environment should be able to make google ads
# changes.
SHOULD_MUTATE_GOOGLE_ADS = True

#STRIPE_SECRET_KEY = 'sk_test_PSFnk5W3bFwy6Fz3K16X5gXN00s1FZfq80'
#STRIPE_PUBLISHABLE_KEY = 'pk_test_ITDtZjGTby7AEynHbPnZkIPw00IZuTbLKZ'
STRIPE_SECRET_KEY = 'sk_test_51I1VrTDxXsJTvkcOcTl73EYSZxQWgzeUmtPyhIZovpWVA3M3UkoyPZ26frtVXkb4LQfHhg1Aek3XlBUE1DBsJ3cw00o1b4TG7K'
STRIPE_PUBLISHABLE_KEY = 'pk_test_51I1VrTDxXsJTvkcOTZk4Q4pK8M6n0yX9JSt212F4DCFqh8unDzb7lkTB5PO9ylndXXhoQBv634vo2lH4auOyZITs00qwFAanh7'

STRIPE_API_VERSION = '2020-03-02'
LOGOUT_REDIRECT_URL = '/login/'

DEFAULT_FROM_EMAIL = 'info@captivise.com'

