# -*- coding: utf-8 -*-
# Generated by Django 1.11.5 on 2017-09-22 10:51
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0012_auto_20170922_0945'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='payment_last_taken_at',
            field=models.DateField(blank=True, null=True),
        ),
    ]