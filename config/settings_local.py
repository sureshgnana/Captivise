DEBUG = True

ALLOWED_HOSTS = (
    '127.0.0.1',
    '178.238.139.175',
    'localhost',
    'app.captivise.com','*'
)

#CSRF_COOKIE_DOMAIN = True

# Database
# https://docs.djangoproject.com/en/1.10/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'appcaptivise',
        'USER': 'root',
        'PASSWORD': 'Captivise@201*',
        'HOST': 'localhost',
        'PORT': '3306',
    },
}


# Email

#EMAIL_HOST = 'smtp.eu.mailgun.org'
#EMAIL_HOST_USER = 'info@mg.captivise.com'
#EMAIL_HOST_PASSWORD = '75b9c7c1eb794139bdde7eadc0620e83-c4d287b4-d3978bad'
#EMAIL_PORT = 465
#EMAIL_USE_TLS = True
#EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'

ANYMAIL = {
    # (exact settings here depend on your ESP...)
    #"MAILGUN_API_KEY": "0c17f999d6d6dc7210fe9750134de5c3-e31dc3cc-8ac8aec5",
    "MAILGUN_API_KEY": "786edb03637def166a0d9771febd9584-4167c382-795548a1",
    "MAILGUN_SENDER_DOMAIN": 'mg.captivise.com',  # your Mailgun domain, if needed
    "MAILGUN_API_URL": "https://api.eu.mailgun.net/v3",
}
EMAIL_BACKEND = "anymail.backends.mailgun.EmailBackend"  # or sendgrid.EmailBackend, or...
DEFAULT_FROM_EMAIL = "info@captivise.com"  # if you don't already have this in settings
SERVER_EMAIL = "info@captivise.com"  # ditto (default from-email for Django errors)


# Googleads
ADWORDS_DEVELOPER_TOKEN = 'RAPXaNRd9Qsg08dOizs9NA'
ADWORDS_CLIENT_ID = '963725954414-1om1d8ltk7c5u4oipce542dr547fimcd.apps.googleusercontent.com'
ADWORDS_SECRET_KEY = 'kjrIzGJWrGhLT4yc3qhsJp-0'
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
ECOM6_CALLBACK_HOST = 'app.captivise.com'


# Determines whether the environment should be able to make google ads
# changes.
SHOULD_MUTATE_GOOGLE_ADS = True

STRIPE_SECRET_KEY = 'sk_live_OfjqOHNE43Q0ohC7U4jmkup600thtu80k2'
STRIPE_PUBLISHABLE_KEY = 'pk_live_jRf817ZS4OXnUIAr0Z2Kzrpe'
STRIPE_SANDBOX_SECRET_KEY = 'sk_test_51I1VrTDxXsJTvkcOcTl73EYSZxQWgzeUmtPyhIZovpWVA3M3UkoyPZ26frtVXkb4LQfHhg1Aek3XlBUE1DBsJ3cw00o1b4TG7K'
STRIPE_SANDBOX_PUBLISHABLE_KEY = 'pk_test_51I1VrTDxXsJTvkcOTZk4Q4pK8M6n0yX9JSt212F4DCFqh8unDzb7lkTB5PO9ylndXXhoQBv634vo2lH4auOyZITs00qwFAanh7'

STRIPE_API_VERSION = '2020-03-02'
LOGOUT_REDIRECT_URL = '/login/'
