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

sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), '..')))

import utils

logger = utils.logger_create('ClearImport')


def import_clear(args):
    if args.release:
        release = args.release
    else:
        logger.debug('Checking latest Clear Linux release...')
        rq = urllib.request.Request('https://cdn.download.clearlinux.org/releases/current/clear/latest')
        data = urllib.request.urlopen(rq).read()
        release = data.decode('utf-8').strip()

    logger.debug('Fetching Clear Linux release %s' % release)

    env = os.environ.copy()
    if args.clear_tool_path:
        env['PATH'] = args.clear_tool_path + ':' + env['PATH']
    cmd = ['dissector', '-clear_version', release, '-all']
    if args.bundles_url:
        cmd += ['-bundles_url', args.bundles_url]
    if args.repo_url:
        cmd += ['-repo_url', args.repo_url]
    return_code = subprocess.call(cmd, env=env, cwd=os.path.abspath(args.outdir))
    if return_code == 1:
        logger.error('Call to dissector failed')
        return 1

    cwd = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    pkgdir = os.path.join(args.outdir, release, 'source')
    cmd = ['layerindex/tools/import_otherdistro.py', 'import-pkgspec', args.branch, args.layer, pkgdir, '--description', 'Clear Linux %s' % release]
    if args.update:
        cmd += ['-u', args.update]
    return_code = subprocess.call(cmd, cwd=cwd)
    if return_code == 1:
        logger.error('Importing data failed')
        return 1

    skiplist = ['helloworld']
    cmd = ['layerindex/tools/update_classic_status.py', '-b', args.branch, '-l', args.layer, pkgdir, '-d', '-s', ','.join(skiplist)]
    if args.update:
        cmd += ['-u', args.update]
    return_code = subprocess.call(cmd, cwd=cwd)
    if return_code == 1:
        logger.error('Updating recipe links failed')
        return 1

    return 0

def main():
    parser = argparse.ArgumentParser(description="Clear Linux data import utility")

    parser.add_argument('-d', '--debug', help='Enable debug output', action='store_true')
    parser.add_argument('-p', '--clear-tool-path', help='Path to Clear Linux Dissector command line application', required=True)
    parser.add_argument('-r', '--release', help='Clear Linux release')
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
