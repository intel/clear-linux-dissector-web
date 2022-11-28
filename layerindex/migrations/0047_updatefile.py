# -*- coding: utf-8 -*-
# Generated by Django 1.11.20 on 2019-05-28 23:51
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('layerindex', '0046_classicrecipe_export_class'),
    ]

    operations = [
        migrations.CreateModel(
            name='UpdateFile',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('filename', models.CharField(max_length=200)),
                ('update', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='layerindex.Update')),
            ],
        ),
    ]
