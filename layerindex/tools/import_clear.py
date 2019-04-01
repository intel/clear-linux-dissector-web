#!/usr/bin/env python3

# Import distro data from a Clear Linux release
#
# Copyright (C) 2019 Intel Corporation
#
# Licensed under the MIT license, see COPYING.MIT for details

import sys
import os
import argparse
import subprocess
import logging
import urllib.request
import json
import shutil
import tempfile

sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), '..')))

import utils

logger = utils.logger_create('ClearImport')


def import_derivative(args):
    srcpath = args.derivative
    imagefile = 'release-image-config.json'
    with open(os.path.join(srcpath, 'src', 'build', imagefile), 'r') as f:
        dt = json.load(f)
    bundles = dt.get('Bundles', [])
    if not bundles:
        logger.error('No bundles found in %s' % imagefile)
        return None, None, None
    localbundles = {}
    stdbundles = []
    for bundle in bundles:
        bundlefn = os.path.join(srcpath, 'src', 'bundles', bundle)
        if os.path.exists(bundlefn):
            pkgs = []
            with open(bundlefn, 'r') as f:
                for line in f:
                    if line and not line.startswith('#'):
                        pkgs.append(line.rstrip())
            localbundles[bundle] = pkgs
        elif bundle not in stdbundles:
            stdbundles.append(bundle)

    release = str(dt.get('Version', ''))
    if not release:
        logger.error('No version specified in %s' % imagefile)
        return None, None, None

    return release, stdbundles, localbundles


def import_clear(args):
    if args.derivative:
        release, stdbundles, localbundles = import_derivative(args)
        if not release:
            return 1
    elif args.release:
        release = args.release
    else:
        logger.debug('Checking latest Clear Linux release...')
        rq = urllib.request.Request('https://cdn.download.clearlinux.org/releases/current/clear/latest')
        data = urllib.request.urlopen(rq).read()
        release = data.decode('utf-8').strip()

    logger.debug('Fetching Clear Linux release %s' % release)

    pkgsrcdir = os.path.join(args.outdir, release, 'source')
    if args.derivative:
        if os.path.exists(pkgsrcdir):
            tmpsrcdir = tempfile.mkdtemp(dir=os.path.join(args.outdir, release))
            shutil.move(pkgsrcdir, tmpsrcdir)
    else:
        tmpsrcdir = None
    try:
        env = os.environ.copy()
        if args.clear_tool_path:
            env['PATH'] = args.clear_tool_path + ':' + env['PATH']
        if args.derivative:
            cmd = ['dissector', '-clear_version', release] + stdbundles
        else:
            cmd = ['dissector', '-clear_version', release, '-all']
        if args.bundles_url:
            cmd += ['-bundles_url', args.bundles_url]
        if args.repo_url:
            cmd += ['-repo_url', args.repo_url]
        logger.debug('Executing %s' % cmd)
        return_code = subprocess.call(cmd, env=env, cwd=os.path.abspath(args.outdir))
        if return_code != 0:
            logger.error('Call to dissector failed')
            return 1

        cwd = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        pkgdir = os.path.join(args.outdir, release, 'source')
        if args.derivative:
            cmd = ['layerindex/tools/import_otherdistro.py', 'import-clear-derivative', args.branch, args.layer, pkgsrcdir, args.derivative]
        else:
            cmd = ['layerindex/tools/import_otherdistro.py', 'import-pkgspec', args.branch, args.layer, pkgsrcdir, '--description', 'Clear Linux %s' % release]
        if args.update:
            cmd += ['-u', args.update]
        logger.debug('Executing %s' % cmd)
        return_code = subprocess.call(cmd, cwd=cwd)
        if return_code != 0:
            logger.error('Importing data failed')
            return 1
    finally:
        if tmpsrcdir and os.path.exists(tmpsrcdir):
            shutil.move(tmpsrcdir, pkgsrcdir)

    skiplist = ['helloworld']
    cmd = ['layerindex/tools/update_classic_status.py', '-b', args.branch, '-l', args.layer, '-d', '-s', ','.join(skiplist)]
    if args.update:
        cmd += ['-u', args.update]
    logger.debug('Executing %s' % cmd)
    return_code = subprocess.call(cmd, cwd=cwd)
    if return_code != 0:
        logger.error('Updating recipe links failed')
        return 1

    return 0

def main():
    parser = argparse.ArgumentParser(description="Clear Linux data import utility")

    parser.add_argument('-d', '--debug', help='Enable debug output', action='store_true')
    parser.add_argument('-p', '--clear-tool-path', help='Path to Clear Linux Dissector command line application', required=True)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-r', '--release', help='Clear Linux release')
    group.add_argument('-g', '--derivative', help='Import from unpacked derivative source tarball')
    parser.add_argument('-o', '--outdir', default='clr-pkgs', help='Output directory (default "%(default)s")')
    parser.add_argument('-u', '--update', help='Update record to associate changes with')
    parser.add_argument('-b', '--branch', default='clearlinux', help='Branch to use (default "%(default)s")')
    parser.add_argument('-l', '--layer', default='clearlinux', help='Layer to use (default "%(default)s")')
    parser.add_argument('--bundles-url', help='Base URL for downloading release archives of clr-bundles')
    parser.add_argument('--repo-url', help='Base URL for downloading releases')

    args = parser.parse_args()

    if args.debug:
        logger.setLevel(logging.DEBUG)

    ret = import_clear(args)

    return ret


if __name__ == "__main__":
    try:
        ret = main()
    except Exception:
        ret = 1
        import traceback
        traceback.print_exc()
    sys.exit(ret)
