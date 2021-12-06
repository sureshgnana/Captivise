# -*- coding: utf-8 -*-
# Generated by Django 1.10.5 on 2017-01-24 12:16
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='KeywordActionLog',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('adwords_keyword_id', models.CharField(max_length=255)),
                ('action', models.CharField(choices=[('increased_cpc', 'Increased CPC'), ('decreased_cpc', 'Decreased CPC'), ('no_action', 'No action'), ('paused', 'Paused')], db_index=True, max_length=50)),
                ('new_max_cpc', models.DecimalField(decimal_places=2, max_digits=10)),
                ('previous_max_cpc', models.DecimalField(decimal_places=2, max_digits=10)),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='ModifierLog',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('modifier_name', models.CharField(max_length=100)),
                ('started_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
            ],
        ),
        migrations.CreateModel(
            name='ModifierProcessLog',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('started_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('status', models.CharField(choices=[('running', 'Running'), ('complete', 'Complete'), ('failed', 'Failed')], default='running', max_length=50)),
                ('error', models.TextField(blank=True)),
            ],
        ),
        migrations.AddField(
            model_name='modifierlog',
            name='modifier_process_log',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='modifier_logs', to='campaign_modifiers.ModifierProcessLog'),
        ),
        migrations.AddField(
            model_name='keywordactionlog',
            name='modifier_log',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='keyword_action_logs', to='campaign_modifiers.ModifierLog'),
        ),
    ]
