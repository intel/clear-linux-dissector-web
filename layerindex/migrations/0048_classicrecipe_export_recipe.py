# -*- coding: utf-8 -*-
# Generated by Django 1.11.20 on 2019-06-10 04:26
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('layerindex', '0047_updatefile'),
    ]

    operations = [
        migrations.AlterField(
            model_name='classicrecipe',
            name='export',
            field=models.CharField(choices=[('X', 'Export bbappend'), ('R', 'Export recipe update'), ('A', 'Already handled'), ('N', 'Not needed')], default='X', max_length=1),
        ),
    ]