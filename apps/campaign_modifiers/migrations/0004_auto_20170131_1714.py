# -*- coding: utf-8 -*-
# Generated by Django 1.10.5 on 2017-01-31 17:14
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('campaign_modifiers', '0003_auto_20170131_1500'),
    ]

    operations = [
        migrations.CreateModel(
            name='KeywordEvent',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('adwords_keyword_id', models.CharField(max_length=255)),
                ('action', models.CharField(choices=[('increased_cpc', 'Increased CPC'), ('decreased_cpc', 'Decreased CPC'), ('no_action', 'No action'), ('paused', 'Paused')], db_index=True, max_length=50)),
                ('new_max_cpc', models.PositiveIntegerField()),
                ('previous_max_cpc', models.PositiveIntegerField()),
                ('modifier_process_log', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='keyword_events', to='campaign_modifiers.ModifierProcessLog')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.AlterField(
            model_name='keywordactionlog',
            name='created_at',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
    ]
