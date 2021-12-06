import datetime

from django.conf import settings
from django.contrib.auth.base_user import BaseUserManager
from django.core.mail import send_mail
from django.db.models import Q
from django.template.loader import render_to_string

from dateutil.relativedelta import relativedelta
from quotes.models import StripeResponse


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        """
        Creates and saves a User with the given email and password.
        """
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self._create_user(email, password, **extra_fields)

    def get_users_with_card_expiry_within_x_months(self, x):
        earliest_safe_date = relativedelta(months=x) + datetime.datetime.now()
        earliest_safe_year = int(earliest_safe_date.strftime('%Y'))
        earliest_safe_month = earliest_safe_date.month

        """return self.get_queryset().filter(           
            is_active=True
        )"""

        qs = self.get_queryset().filter(            
            Q(
                stripe_pay__card_expiry_year__lt=earliest_safe_year) |  # noqa
            (
                Q(stripe_pay__card_expiry_year=earliest_safe_year) &  # noqa
                Q(stripe_pay__card_expiry_month__lt=earliest_safe_month)  # noqa
            ),
            is_active=True,
        )
        #print(qs.query.get_compiler('default').as_sql())
        return qs        

        return self.get_queryset().filter(
            Q(
                initial_continuous_authority_payment__response__card_expiry_year__lt=earliest_safe_year) |  # noqa
            (
                Q(initial_continuous_authority_payment__response__card_expiry_year=earliest_safe_year) &  # noqa
                Q(initial_continuous_authority_payment__response__card_expiry_month__lt=earliest_safe_month)  # noqa
            ),
            is_active=True,
        )

    def alert_users_of_imminent_card_expiry(self, raise_for_errors=False, loghook=None):
        qs = self.get_users_with_card_expiry_within_x_months(3) \
            .filter(show_card_expiry_warning=False)        
        
        for user in qs:
            # Set a flag for the user to show them a warning banner.
            user.show_card_expiry_warning = True
            user.save()

            payment_info = StripeResponse.objects.get(user_id=user.id)
            # Email the user.
            context = {
                'card_number_mask': (
                    payment_info.card_number_mask.rjust(16, '*')
                ),
            }

            try:
                send_mail(
                    'Captivise - Your card is expiring soon',
                    render_to_string('accounts/email/card_expiry_warning.txt', context),
                    settings.DEFAULT_FROM_EMAIL,
                    [user.email],
                    fail_silently=False,
                )
            except Exception:
                if callable(loghook):
                    loghook(user)

                if raise_for_errors:
                    raise

    def lock_out_users_with_expired_cards(self):
        qs = self.get_users_with_card_expiry_within_x_months(0)

        for user in qs:           

            user.stripe_pay = None
            user.save()