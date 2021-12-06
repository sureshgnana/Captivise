# -*- coding: utf-8 -*-
# Generated by Django 1.10.5 on 2017-08-15 14:40
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0009_user_email_confirmed_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='phone_number',
            field=models.CharField(default='', max_length=14, verbose_name='Telephone'),
            preserve_default=False,
        ),
    ]
