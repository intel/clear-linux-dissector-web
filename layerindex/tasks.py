# Celery task definitions for the layer index app
#
# Copyright (C) 2018 Intel Corporation
# Author: Paul Eggleton <paul.eggleton@linux.intel.com>
#
# Licensed under the MIT license, see COPYING.MIT for details

from celery import Celery
from django.core.mail import EmailMessage
from . import utils
import os
import time
import subprocess
import shlex
from datetime import datetime

try:
    import settings
except ImportError:
    # not in a full django env, so settings is inaccessible.
    # setup django to access settings.
    utils.setup_django()
    import settings

tasks = Celery('layerindex',
    broker=settings.RABBIT_BROKER,
    backend=settings.RABBIT_BACKEND,
    broker_heartbeat=0)

@tasks.task
def send_email(subject, text_content, from_email=settings.DEFAULT_FROM_EMAIL, to_emails=[]):
    # We seem to need to run this within the task
    utils.setup_django()
    msg = EmailMessage(subject, text_content, from_email, to_emails)
    msg.send()

@tasks.task(bind=True)
def run_update_command(self, branch_name, update_command):
    utils.setup_django()
    from layerindex.models import Update
    updateobj = Update.objects.get(task_id=self.request.id)
    updateobj.started = datetime.now()
    updateobj.save()
    output = ''
    shell = False
    if isinstance(update_command, str):
        update_command = update_command.replace('%update%', str(updateobj.id))
        update_command = update_command.replace('%branch%', shlex.quote(branch_name))
        shell = True
    try:
        os.makedirs(settings.TASK_LOG_DIR)
    except FileExistsError:
        pass
    logfile = os.path.join(settings.TASK_LOG_DIR, 'task_%s.log' % str(self.request.id))
    retcode = 0
    erroutput = None
    try:
        output = utils.runcmd(update_command, os.path.dirname(os.path.dirname(__file__)), outfile=logfile, shell=shell)
    except subprocess.CalledProcessError as e:
        output = e.output
        erroutput = output
        retcode = e.returncode
    except Exception as e:
        print('ERROR: %s' % str(e))
        output = str(e)
        erroutput = output
        retcode = -1
    finally:
        updateobj.log = output
        updateobj.finished = datetime.now()
        updateobj.retcode = retcode
        updateobj.save()
    return {'retcode': retcode, 'output': erroutput}


@tasks.task
def generate_version_comparison(vercmp_id):
    from distutils.version import LooseVersion
    utils.setup_django()
    from django.db import transaction
    from layerindex.models import ClassicRecipe
    from dissector.models import VersionComparison, VersionComparisonDifference, ImageComparisonRecipe
    vercmp = VersionComparison.objects.get(id=vercmp_id)
    try:
        from_branch = vercmp.from_branch
        to_branch = vercmp.to_branch
        from_image = from_branch.is_image_comparison()
        to_image = to_branch.is_image_comparison()
        with transaction.atomic():
            from_layerbranch = from_branch.layerbranch_set.first()
            to_layerbranch = to_branch.layerbranch_set.first()
            if from_image:
                from_recipes = ImageComparisonRecipe.objects.filter(layerbranch=from_layerbranch).only('pn')
            else:
                from_recipes = ClassicRecipe.objects.filter(layerbranch=from_layerbranch, deleted=False).only('pn')

            if from_image and not to_image:
                from_pns = set(from_recipes.values_list('cover_pn', flat=True))
            else:
                from_pns = set(from_recipes.values_list('pn', flat=True))

            if to_image:
                to_recipes = ImageComparisonRecipe.objects.filter(layerbranch=to_layerbranch).only('pn')
            else:
                to_recipes = ClassicRecipe.objects.filter(layerbranch=to_layerbranch, deleted=False).only('pn')

            if to_image and not from_image:
                to_pns = set(to_recipes.values_list('cover_pn', flat=True))
            else:
                to_pns = set(to_recipes.values_list('pn', flat=True))

            removed = from_pns - to_pns
            added = to_pns - from_pns

            modifications = []
            for item in sorted(added, key=lambda s: s.lower()):
                if not item:
                    continue
                diff = VersionComparisonDifference()
                diff.comparison = vercmp
                diff.pn = item
                diff.from_layerbranch = from_layerbranch
                diff.to_layerbranch = to_layerbranch
                diff.change_type = 'A'
                diff.save()

            for item in sorted(from_pns & to_pns, key=lambda s: s.lower()):
                if from_image and not to_image:
                    item_from_recipes = from_recipes.filter(cover_pn=item)
                else:
                    item_from_recipes = from_recipes.filter(pn=item)
                if to_image and not from_image:
                    item_to_recipes = to_recipes.filter(cover_pn=item)
                else:
                    item_to_recipes = to_recipes.filter(pn=item)
                from_pvs = item_from_recipes.values_list('pv', flat=True)
                to_pvs = item_to_recipes.values_list('pv', flat=True)
                # Create a diff (we don't necessarily have to save it)
                diff = VersionComparisonDifference()
                diff.comparison = vercmp
                diff.pn = item
                diff.from_layerbranch = from_layerbranch
                diff.to_layerbranch = to_layerbranch
                if len(from_pvs) == 1 and len(to_pvs) == 1:
                    if from_pvs[0] and to_pvs[0] and from_pvs[0] != to_pvs[0]:
                        from_ver = LooseVersion(from_pvs[0])
                        to_ver = LooseVersion(to_pvs[0])
                        if to_ver > from_ver:
                            diff.change_type = 'U'
                            diff.oldvalue = from_pvs[0]
                            diff.newvalue = to_pvs[0]
                            diff.save()
                        elif from_ver > to_ver:
                            diff.change_type = 'D'
                            diff.oldvalue = from_pvs[0]
                            diff.newvalue = to_pvs[0]
                            diff.save()
                    else:
                        item_from_recipe = item_from_recipes.first()
                        item_to_recipe = item_to_recipes.first()
                        changed = False
                        if item_from_recipe.sha256sum != item_to_recipe.sha256sum:
                            changed = True
                        else:
                            # Check patches
                            from_patches = set(item_from_recipe.patch_set.filter(applied=True).values_list('src_path', flat=True))
                            to_patches = set(item_to_recipe.patch_set.filter(applied=True).values_list('src_path', flat=True))
                            if from_patches.symmetric_difference(to_patches):
                                changed = True
                            else:
                                for src_path in from_patches.union(to_patches):
                                    from_patch = item_from_recipe.patch_set.filter(src_path=src_path).first()
                                    to_patch = item_to_recipe.patch_set.filter(src_path=src_path).first()
                                    if from_patch.sha256sum != to_patch.sha256sum:
                                        changed = True
                                        break
                        if not changed:
                            # Check sources
                            from_sources = set(item_from_recipe.source_set.all().values_list('url', flat=True))
                            to_sources = set(item_to_recipe.source_set.all().values_list('url', flat=True))
                            if from_sources.symmetric_difference(to_sources):
                                changed = True
                            else:
                                for url in from_sources.union(to_sources):
                                    from_source = item_from_recipe.source_set.filter(url=url).first()
                                    to_source = item_to_recipe.source_set.filter(url=url).first()
                                    if from_source.sha256sum != to_source.sha256sum:
                                        changed = True
                                        break
                        if changed:
                            # Defer saving modifications until after upgrades
                            diff.change_type = 'M'
                            modifications.append(diff)
                else:
                    diff.change_type = 'V'
                    diff.oldvalue = ', '.join(from_pvs)
                    diff.newvalue = ', '.join(to_pvs)
                    diff.save()

            for diff in modifications:
                diff.save()

            for item in sorted(removed, key=lambda s: s.lower()):
                if not item:
                    continue
                diff = VersionComparisonDifference()
                diff.comparison = vercmp
                diff.pn = item
                diff.from_layerbranch = from_layerbranch
                diff.to_layerbranch = to_layerbranch
                diff.change_type = 'R'
                diff.save()
    except:
        vercmp.status = 'F'
        vercmp.save()
        raise
    vercmp.status = 'S'
    vercmp.save()


@tasks.task
def generate_diff(file_diff_id):
    utils.setup_django()
    from dissector.models import VersionComparisonFileDiff
    fdiff = VersionComparisonFileDiff.objects.get(id=file_diff_id)
    try:
        fdiff_file = fdiff.get_diff_path()
        try:
            os.makedirs(os.path.dirname(fdiff_file))
        except FileExistsError:
            pass
        from_path, to_path = fdiff.difference.get_comparison_paths()
        if not from_path:
            raise Exception('Unable to generate diff: invalid from path')
        if not to_path:
            raise Exception('Unable to generate diff: invalid to path')
        srcdir = getattr(settings, 'VERSION_COMPARE_SOURCE_DIR')
        from_path = os.path.relpath(from_path, srcdir)
        to_path = os.path.relpath(to_path, srcdir)
        try:
            utils.runcmd("diff -udNr %s %s | sed '/^Binary files/d' > %s" % (shlex.quote(from_path), shlex.quote(to_path), shlex.quote(fdiff_file)), destdir=srcdir, shell=True)
        except subprocess.CalledProcessError as e:
            if e.returncode != 1:
                raise
    except:
        fdiff.status = 'F'
        fdiff.save()
        raise
    fdiff.status = 'S'
    fdiff.save()
