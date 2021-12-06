# Generated by Django 2.2.9 on 2020-05-31 14:22

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='StripeResponse',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('response_code', models.CharField(max_length=255, verbose_name='Response Code')),
                ('timestamp', models.CharField(max_length=255, verbose_name='Timestamp')),
                ('card_number_mask', models.CharField(max_length=255, null=True, verbose_name='Card Number Mask')),
                ('user_email', models.CharField(max_length=255, null=True, verbose_name='Email')),
                ('card_expiry_year', models.CharField(max_length=255, null=True, verbose_name='Card Expiry Year')),
                ('card_expiry_month', models.CharField(max_length=255, null=True, verbose_name='Card Expiry Month')),
                ('customer_id', models.CharField(max_length=255, null=True, verbose_name='Stripe Customer ID')),
                ('setup_intents_id', models.CharField(max_length=255, null=True, verbose_name='Stripe Intents ID')),
                ('payment_method', models.CharField(max_length=255, null=True, verbose_name='Payment Method')),
                ('client_secret', models.CharField(max_length=255, null=True, verbose_name='Client Secret')),
                ('response_data', models.TextField()),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, verbose_name='User')),
            ],
        ),
        migrations.CreateModel(
            name='Quote',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created at')),
                ('user_first_name', models.CharField(max_length=30, verbose_name='First name')),
                ('user_last_name', models.CharField(max_length=30, verbose_name='Last name')),
                ('user_email', models.EmailField(max_length=254, verbose_name='Email address')),
                ('monthly_adwords_spend', models.BigIntegerField(verbose_name='Monthly Google Adwords Spend')),
                ('quote', models.BigIntegerField(verbose_name='Quote')),
                ('type', models.CharField(choices=[('automatic', 'Automatic'), ('estimate', 'Estimate')], max_length=20, verbose_name='Type')),
                ('is_accepted', models.BooleanField(default=False, verbose_name='Accepted')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, verbose_name='User')),
            ],
        ),
    ]
