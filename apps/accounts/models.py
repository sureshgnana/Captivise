import datetime
import decimal
import logging
import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import send_mail
from django.db import models
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _

import requests

from adwords.adapter import Adapter
from adwords.exceptions import TooEarlyError
from billing.models import Payment
from billing.utils import get_pricing
from reports.utils import decimal_to_micro_amount, micro_amount_to_decimal
from website.utils import get_new_user_alert_email
import json
from quotes.models import StripeResponse
import stripe
from constance import config

from .exceptions import (
    CapturingContinuousAuthorityPaymentFailedError,
    NoContinuousAuthorityInitialPaymentError,
)
from .managers import UserManager
from reports.models import Campaign
from report_scripts.models import ReportScriptsStatus
from django.db.models import Count


class User(AbstractBaseUser, PermissionsMixin):
    first_name = models.CharField(_('first name'), max_length=30, blank=True)
    last_name = models.CharField(_('last name'), max_length=30, blank=True)
    email = models.EmailField(_('email address'), unique=True)
    is_staff = models.BooleanField(
        _('staff status'),
        default=False,
        help_text=_('Designates whether the user can log into this admin site.'),
    )
    is_active = models.BooleanField(
        _('active'),
        default=True,
        help_text=_(
            'Designates whether this user should be treated as active. '
            'Unselect this instead of deleting accounts.'
        ),
    )
    refresh_token = models.CharField(
        _('refresh token'),
        max_length=255,
        unique=True,
        null=True,
        blank=True,
    )
    client_customer_id = models.CharField(_('client customer id'), max_length=255, blank=True)
    date_joined = models.DateTimeField(_('date joined'), default=timezone.now)
    is_adwords_dry_run = models.BooleanField(_('Do not apply Adwords changes'), default=False)
    is_freerolled = models.BooleanField(
        _('Freeroll this user'),
        help_text=_(
            'If set, this user will have their account managed for free,'
            ' and will not encounter the payent step of the signup process.'
        ),
        default=False,
    )
    phone_number = models.CharField(_('Telephone'), max_length=14, blank=False)
    company_name = models.CharField(_('Company'), max_length=50, blank=True)
    email_confirmed_at = models.DateTimeField(_('Email confirmed at'), null=True, blank=True)
    initial_continuous_authority_payment = models.ForeignKey(
        'billing.Payment', null=True, blank=True, related_name='+', on_delete=models.SET_NULL)
    previous_initial_continuous_authority_payments = models.ManyToManyField(
        'billing.Payment', null=True, blank=True, related_name='+')
    payment_last_taken_at = models.DateTimeField(_('Payment last taken at'), auto_now_add=True, null=True, blank=True)

    show_card_expiry_warning = models.BooleanField(default=False)

    google_analytics_client_id = models.UUIDField(
        _('The ID used to refer to this user within Google Analytics'),
        default=uuid.uuid4,
        unique=True,
    )
    stripe_pay = models.ForeignKey(StripeResponse, null=True, blank=True, related_name='+', on_delete=models.SET_NULL)
    payment_percent = models.DecimalField(max_digits=12,  decimal_places=2, null=True, blank=True)
    merchant_refresh_token = models.CharField(_('merchant refresh token'), max_length=255, null=True, blank=True)
    merchant_access_token = models.CharField(_('merchant access token'), max_length=255, null=True, blank=True)
    merchant_id = models.CharField(_('merchant id'), max_length=255, null=True, blank=True)
    merchant_name = models.CharField(_('merchant name'), max_length=255, null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = _('user')
        verbose_name_plural = _('users')

    def set_adwords_fields(self, refresh_token, client_customer_id):
        self.refresh_token = refresh_token
        self.client_customer_id = client_customer_id
        self.save()        

    def reset_adwords_fields(self):
        self.refresh_token = None
        self.client_customer_id = ''
        self.save()

    def set_merchant_fields(self, merchant_refresh_token, merchant_access_token, merchant_id, merchant_name):
        self.merchant_refresh_token = merchant_refresh_token
        self.merchant_access_token = merchant_access_token
        self.merchant_id = merchant_id
        self.merchant_name = merchant_name
        self.save()        

    def reset_merchant_fields(self):
        self.merchant_refresh_token = None
        self.merchant_access_token = None
        self.merchant_id = ''
        self.merchant_name = ''
        self.save()
    
    def getAdapter(self):
        return Adapter(self)

    @property
    def has_adwords_account(self):
        return self.refresh_token is not None

    @property
    def has_payment_details(self):
        if self.is_freerolled:
            return True
        
        try:
            payment_info = StripeResponse.objects.get(user_id=self.pk)
            if payment_info.response_code == "1":
                return True
        except:
            return False

        payment = self.initial_continuous_authority_payment
        if payment is None:
            return False

        return payment.is_successful

    def get_payment_details_context(self):
        if self.is_freerolled:
            return {
                'card_number_mask': 'N/A',
                'card_expiry': 'N/A',
                'card_type': 'N/A',
            }
        
        payment_info = StripeResponse.objects.get(user_id=self.pk)

        return {
            'card_number_mask': payment_info.card_number_mask.rjust(16, '*'),
            'card_expiry': '{month}/{year}'.format(
                month=str(payment_info.card_expiry_month).zfill(2),
                year=str(payment_info.card_expiry_year)[-2:],
            ),
            'card_type': payment_info.card_type.title(),
        }

        payment = self.initial_continuous_authority_payment
        
        return {
            'card_number_mask': payment.response.card_number_mask,
            'card_expiry': '{month}/{year}'.format(
                month=payment.response.card_expiry_month,
                year=payment.response.card_expiry_year,
            ),
            'card_type': payment.response.card_type,
        }

    def get_payment_amount_required(self, force_recalculate=False):
        if hasattr(self, '_payment_amount_required') and not force_recalculate:
            return self._payment_amount_required

        now = datetime.datetime.now()
        if now.time() < datetime.time(hour=3):
            raise TooEarlyError(
                'Data is only available for the previous day from 3AM.'
                '  Please try again later.'
            )

        adapter = Adapter(self)
        #monthly_spend = adapter.get_monthly_spend()
        
        if self.payment_last_taken_at is None:
            spend_since_last_billed = adapter.get_monthly_spend()            
        else:
            spend_since_last_billed = adapter.get_spend_for_period(
                self.payment_last_taken_at, now.date())
                  
        
        payment_per = config.DEFAULT_PERCENT
        if self.payment_percent is not None and self.payment_percent > 0:
            payment_per = self.payment_percent
    
        self._payment_amount_required = int((
            spend_since_last_billed * (payment_per / 100)))

        print("Step Final")
        print(self._payment_amount_required)
        print(decimal_to_micro_amount(0.1))
        return self._payment_amount_required

    @property
    def is_payment_required(self):
        #return True
        if self.is_freerolled:
            return False    
                
        if self.payment_last_taken_at is not None:
            payment_last_date = timezone.now()-self.payment_last_taken_at
            if payment_last_date.days > 30:
                return True
            else:
                return False
        else:
            return True

        #threshold = decimal_to_micro_amount(500)
        threshold = decimal_to_micro_amount(0.1)

        if threshold <= self.get_payment_amount_required(True):
            return True

        return False

    def take_payment(self, amount):
        if self.initial_continuous_authority_payment is None:
            raise NoContinuousAuthorityInitialPaymentError()

        if not self.initial_continuous_authority_payment.is_successful:
            raise NoContinuousAuthorityInitialPaymentError()

        payment = Payment.objects.create(
            amount=amount,
            currency_code='GBP',
            action='SALE',
            user=self,
        )

        payment.set_as_continuous_authority_payment(self.initial_continuous_authority_payment)
        payment.capture_continuous_authority_payment()

        if payment.response.response_code != 0:
            raise CapturingContinuousAuthorityPaymentFailedError(
                'Taking payment {payment_pk} for user {user_pk} failed.'.format(
                    payment_pk=payment.pk, user_pk=self.pk)
            )

        self.payment_last_taken_at = datetime.datetime.now()
        self.save()

        self.register_analytics_transaction(payment)

        del self._payment_amount_required

    def take_payment_if_required(self):
        if self.is_payment_required:
            micro_amount = self.get_payment_amount_required(True)
            
            if micro_amount > 0:
                amount = micro_amount_to_decimal(micro_amount)   
                if amount > 0.50:                          
                    amount_in_pennies = int(amount * 100)
                    return self.capture_stripe_payment(amount_in_pennies)


    def register_analytics_transaction(self, payment):
        requests.post(
            'https://google-analytics.com/collect',
            data={
                'v': 1,
                'tid': settings.ANALYTICS_TID,
                'cid': self.google_analytics_client_id,
                't': 'transaction',
                'ti': payment.transaction_id,
                'tr': decimal.Decimal(payment.amount) / 100,
                'ts': 0,
                'tt': 0,  # TODO:  If we charge VAT, this needs to change.
                'cu': 'GBP',
            },
        )

    def alert_user_registered(self):
        try:
            email_to = config.NEW_USER_ALERT_EMAIL
        except ImproperlyConfigured:
            logger = logging.getLogger('celery')
            logger.exception(
                'Failed to alert of a new user (pk: {pk}) registering;'
                ' no alert recipient set.'.format(pk=self.pk)
            )
        else:  # noexcept
            context = {
                "first_name": self.first_name,
                "last_name": self.last_name,
                "email": self.email,
                "company_name": self.company_name,
            }

            try:
                send_mail(
                    'Captivise - A new user has registered',
                    render_to_string('accounts/email/alert_user_registered.txt', context),
                    settings.DEFAULT_FROM_EMAIL,
                    [email_to],
                    fail_silently=False,
                )
            except Exception:
                logger = logging.getLogger('celery')
                logger.exception(
                    'Failed to alert of a new user (pk: {pk}) registering'.format(pk=self.pk))

    def save(self, *args, **kwargs):
        should_alert_user_registered = False
        if self.pk is None:
            should_alert_user_registered = True

        super().save(*args, **kwargs)

        if should_alert_user_registered:
            
            self.alert_user_registered()

    def get_full_name(self):
        """
        Returns the first_name plus the last_name, with a space in between.
        """
        full_name = '%s %s' % (self.first_name, self.last_name)
        return full_name.strip()

    def get_short_name(self):
        """
        Returns the short name for the user.
        """
        return self.first_name
    def get_email(self):
        """
        Returns the email for the user.
        """
        return self.email

    def email_user(self, subject, message, from_email=None, **kwargs):
        """
        Sends an email to this User.
        """
        send_mail(subject, message, from_email, [self.email], **kwargs)

    def set_email_confirmed(self, commit=True):
        self.email_confirmed_at = timezone.now()
        if commit:
            self.save()
    
    def capture_stripe_payment(self, amount=0):
        
        stripe.api_version = settings.STRIPE_API_VERSION
        if config.STRIPE_PAYMENT_SANDBOX is True:
            stripe.api_key = settings.STRIPE_SANDBOX_SECRET_KEY
            stripe.public_key = settings.STRIPE_SANDBOX_PUBLISHABLE_KEY
        else:
            stripe.api_key = settings.STRIPE_SECRET_KEY
            stripe.public_key = settings.STRIPE_PUBLISHABLE_KEY


        payment_info = StripeResponse.objects.get(user_id=self.pk)
        logger = logging.getLogger('celery')

        try:
            intent = stripe.PaymentIntent.create(
                amount=amount,
                currency=config.CURRENCY_CODE,
                payment_method=payment_info.payment_method,
                customer=payment_info.customer_id,
                confirm=True,
                off_session=True
            )

            
            charges = intent.charges.data[0]
            amount_captured = charges.amount_captured
            charges_id = charges.id

            email = charges.billing_details.email
            name = charges.billing_details.name
            phone = charges.billing_details.phone
            line1 = charges.billing_details.address.line1
            line2 = charges.billing_details.address.line2
            customer_address = ', '.join(filter(None, [line1, line2]))
            city = charges.billing_details.address.city
            postal_code = charges.billing_details.address.postal_code
            state = charges.billing_details.address.state
            country = charges.billing_details.address.country
            status = charges.status
            currency = charges.currency.upper()

            transaction_id = intent.id
            card_last4 = charges.payment_method_details.card.last4
            card_exp_month = charges.payment_method_details.card.exp_month
            card_exp_year = charges.payment_method_details.card.exp_year
            card_type = charges.payment_method_details.card.brand

            payment = Payment.objects.create(
                amount=amount_captured,
                currency_code=currency,
                customer_name=name,
                customer_address=customer_address,
                customer_postcode=postal_code,
                customer_city=city,
                customer_state=state,
                customer_country=country,
                customer_email=email,
                customer_phone=phone,
                user=self,
                transaction_id=transaction_id,
                charges_id=charges_id,
                card_type=card_type,
                card_last4=card_last4,
                card_expiry_year=card_exp_year,
                card_expiry_month=card_exp_month,
                status=status,
            )
           
            if status == "succeeded":               

                self.initial_continuous_authority_payment = payment
                self.payment_last_taken_at = timezone.now()
                self.save()

                self.register_analytics_transaction(payment) 

                del self._payment_amount_required
                
                context = {
                    'address': {
                        'street_address': customer_address,
                        'city': city,
                        'postal_code': postal_code,
                        'state': state,
                        'country': country,                       
                        
                    },
                    'phone': phone,
                    'email': email,
                    'amount': decimal.Decimal(amount/100.0).quantize(decimal.Decimal('0.01')),
                    'id': payment.id,
                    'created_at': payment.created_at.strftime("%d/%m/%Y"),
                    'config': config
                }

                try:
                    send_mail(
                        'Captivise - Payment',
                        'Captivise - Payment',
                        settings.DEFAULT_FROM_EMAIL,
                        [self.email],
                        fail_silently=False,
                        html_message=render_to_string('accounts/email/alert_user_charged.html', context),
                    )
                except Exception:
                    logger = logging.getLogger('celery')
                    logger.exception(
                        'Failed to alert of a charge user (pk: {pk})'.format(pk=self.pk))

        except stripe.error.CardError as e:
            err = e.error
            if err.code == 'authentication_required':                
                logger.exception(
                    'Error: authentication_required. paymentMethod - {payment_method} user - {pk}'.format(
                        payment_method=err.payment_method.id, pk=self.pk))
            elif err.code:               
                logger.exception(
                    'Error: paymentMethod - {payment_method} user - {pk}'.format(
                        payment_method=err.code, pk=self.pk))
        except stripe.error.RateLimitError as e:            
            logger.exception(
                'Error: RateLimitError user - {pk}'.format(pk=self.pk))
            pass
        except stripe.error.InvalidRequestError as e:            
            logger.exception(
                'Error: InvalidRequestError user - {pk}'.format(pk=self.pk))
            pass
        except stripe.error.AuthenticationError as e:
            logger.exception(
                'Error: AuthenticationError user - {pk}'.format(pk=self.pk))
            pass
        except stripe.error.APIConnectionError as e:
            logger.exception(
                'Error: APIConnectionError user - {pk}'.format(pk=self.pk))            
            pass
        except stripe.error.StripeError as e:
            logger.exception(
                'Error: StripeError user - {pk}'.format(pk=self.pk))           
            pass
        except Exception as e:
            logger.exception(
                'Error: StripeError user - {pk}'.format(pk=self.pk))
            pass
        
        return True
    
    @property
    def is_campaign_warning(self):
        
        campaign_obj = ReportScriptsStatus.objects.filter(
            user_id=self.pk,
            campaign__client_customer_id=self.client_customer_id,
            campaign__is_managed=False,
            status=True
        ).aggregate(unique_campaign=Count('campaign_id', distinct=True),)
        if 'unique_campaign' in campaign_obj and campaign_obj['unique_campaign'] is not None:        
            return campaign_obj['unique_campaign']
        else:
            return 0