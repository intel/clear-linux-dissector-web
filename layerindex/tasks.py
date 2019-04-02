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
    backend=settings.RABBIT_BACKEND)

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
    update_command = update_command.replace('%update%', str(updateobj.id))
    update_command = update_command.replace('%branch%', branch_name)
    try:
        os.makedirs(settings.TASK_LOG_DIR)
    except FileExistsError:
        pass
    logfile = os.path.join(settings.TASK_LOG_DIR, 'task_%s.log' % str(self.request.id))
    retcode = 0
    erroutput = None
    try:
        output = utils.runcmd(update_command, os.path.dirname(os.path.dirname(__file__)), outfile=logfile, shell=True)
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
def generate_diff(file_diff_id):
    utils.setup_django()
    from layerindex.models import VersionComparisonFileDiff
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
            utils.runcmd("diff -udNr %s %s | sed '/^Binary files/d' > %s" % (from_path, to_path, fdiff_file), destdir=srcdir, shell=True)
        except subprocess.CalledProcessError as e:
            if e.returncode != 1:
                raise
    except:
        fdiff.status = 'F'
        fdiff.save()
        raise
    fdiff.status = 'S'
    fdiff.save()
