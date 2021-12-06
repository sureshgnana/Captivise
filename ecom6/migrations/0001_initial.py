# Generated by Django 2.2.9 on 2020-05-14 14:52

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Response',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('response_code', models.PositiveIntegerField(blank=True)),
                ('response_message', models.TextField(blank=True)),
                ('transaction_id', models.CharField(blank=True, max_length=255)),
                ('xref', models.CharField(blank=True, max_length=255)),
                ('state', models.TextField(blank=True, choices=[('received', 'Received'), ('approved', 'Approved'), ('declined', 'Declined'), ('referred', 'Referred'), ('reversed', 'Reversed'), ('captured', 'Captured'), ('tendered', 'Tendered'), ('deferred', 'Deferred'), ('accepted', 'Accepted'), ('rejected', 'Rejected'), ('cancelled', 'Cancelled'), ('finished', 'Finished'), ('verified', 'Verified')], max_length=9)),
                ('timestamp', models.DateTimeField(blank=True)),
                ('authorisation_code', models.CharField(blank=True, max_length=255)),
                ('referral_phone', models.CharField(blank=True, max_length=15)),
                ('amount_received', models.PositiveIntegerField(blank=True, null=True)),
                ('card_number_mask', models.CharField(blank=True, max_length=63)),
                ('card_type_code', models.CharField(blank=True, choices=[('MC', 'MasterCard Credit'), ('MD', 'MasterCard Debit'), ('MA', 'MasterCard International Maestro'), ('MI', 'MasterCard/Diners Club'), ('MP', 'MasterCard Purchasing'), ('MU', 'MasterCard Domestic Maestro (UK)'), ('VC', 'Visa Credit'), ('VD', 'Visa Debit'), ('EL', 'Visa Electron'), ('VA', 'Visa ATM'), ('VP', 'Visa Purchasing'), ('AM', 'American Express'), ('JC', 'JCB')], max_length=2)),
                ('card_type', models.CharField(blank=True, max_length=63)),
                ('card_scheme_code', models.CharField(blank=True, choices=[('MC', 'MasterCard Credit'), ('MD', 'MasterCard Debit'), ('MA', 'MasterCard International Maestro'), ('MI', 'MasterCard/Diners Club'), ('MP', 'MasterCard Purchasing'), ('MU', 'MasterCard Domestic Maestro (UK)'), ('VC', 'Visa Credit'), ('VD', 'Visa Debit'), ('EL', 'Visa Electron'), ('VA', 'Visa ATM'), ('VP', 'Visa Purchasing'), ('AM', 'American Express'), ('JC', 'JCB'), ('CF', 'Clydesdale Financial Services'), ('CU', 'China UnionPay'), ('BC', 'BankCard'), ('DK', 'Dankort'), ('DS', 'Discover'), ('DI', 'Diners Club'), ('DE', 'Diners Club Enroute'), ('DC', 'Diners Club Carte Blanche'), ('FC', 'FlexCache'), ('LS', 'Laser'), ('SO', 'Solo'), ('ST', 'Style'), ('SW', 'Switch'), ('TP', 'Tempo Payments'), ('IP', 'InstaPayment'), ('XX', 'Unknown/unrecognised card type')], max_length=2)),
                ('card_scheme', models.CharField(blank=True, max_length=63)),
                ('card_issuer', models.CharField(blank=True, max_length=63)),
                ('card_issuer_country', models.CharField(blank=True, max_length=63)),
                ('card_issuer_country_code', models.CharField(blank=True, max_length=3)),
                ('card_expiry_year', models.PositiveIntegerField(blank=True, null=True)),
                ('card_expiry_month', models.PositiveIntegerField(blank=True, null=True)),
                ('response_data', models.TextField()),
            ],
        ),
    ]