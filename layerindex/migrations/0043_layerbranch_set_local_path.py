# -*- coding: utf-8 -*-
# Generated by Django 1.11.16 on 2019-05-08 10:00
from __future__ import unicode_literals

from django.db import migrations


def set_layerbranch_local_path(apps, schema_editor):
    LayerBranch = apps.get_model('layerindex', 'LayerBranch')
    ImageComparison = apps.get_model('layerindex', 'ImageComparison')
    for item in ImageComparison.objects.all():
        for layerbranch in LayerBranch.objects.filter(branch=item.from_branch):
            layerbranch.local_path = str(item.id)
            layerbranch.save()

class Migration(migrations.Migration):

    dependencies = [
        ('layerindex', '0042_imagecomparisonrecipe_sha256sum'),
    ]

    operations = [
        migrations.RunPython(set_layerbranch_local_path, reverse_code=migrations.RunPython.noop),
    ]
