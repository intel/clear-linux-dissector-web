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
import tarfile

sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), '..')))

import utils

logger = utils.logger_create('ClearImport')


def import_derivative(args, tempdir):
    def extract_tar(tarballfn):
        with tarfile.open(tarballfn, 'r') as tar:
            if not utils.check_tar_contents(tar):
                logger.error('Invalid source tarball')
                return None
            tar.extractall(tempdir)
        for entry in os.listdir(tempdir):
            pth = os.path.join(tempdir, entry)
            if os.path.isdir(pth):
                return pth
        logger.error('No directory found after extracting source tarball')
        return None

    if '://' in args.derivative:
        def reporthook(blocknum, blocksize, total):
            downloaded = blocknum * blocksize
            if total > 0:
                percent = downloaded * 100 / total
                s = "\r %d%% %s / %s    " % (
                    percent, utils.human_filesize(downloaded), utils.human_filesize(total))
                sys.stderr.write(s)
                if downloaded >= total:
                    sys.stderr.write("\n")
            else:
                sys.stderr.write("Downloaded %s\n" % utils.human_filesize(downloaded))

        tarball = os.path.join(tempdir, 'tmpsrc.tar.gz')
        logger.info('Retrieving source tarball')
        urllib.request.urlretrieve(args.derivative, tarball, reporthook)
        srcpath = extract_tar(tarball)
        if not srcpath:
            return None, None, None, None
    elif args.derivative.endswith(('.tar.gz', '.tgz', '.tar.bz2', '.tar.xz')):
        srcpath = extract_tar(args.derivative)
        if not srcpath:
            return None, None, None, None
    else:
        srcpath = args.derivative

    imagefile = 'release-image-config.json'
    try:
        with open(os.path.join(srcpath, 'src', 'build', imagefile), 'r') as f:
            dt = json.load(f)
    except FileNotFoundError:
        logger.error('Tarball unpacked but did not contain src/build/release-image-config.json - is this actually a Clear Linux derivative source tarball?')
        return None, None, None, None
    bundles = dt.get('Bundles', [])
    if not bundles:
        logger.error('No bundles found in %s' % imagefile)
        return None, None, None, None
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
        return None, None, None, None

    return release, stdbundles, localbundles, srcpath


def import_clear(args):
    tmpsrcdir = None
    tempdir = tempfile.mkdtemp()
    try:
        if args.derivative:
            release, stdbundles, localbundles, srcpath = import_derivative(args, tempdir)
            if not release:
                return 1
        elif args.release:
            release = args.release
        else:
            logger.debug('Checking latest Clear Linux release...')
            rq = urllib.request.Request('https://cdn.download.clearlinux.org/releases/current/clear/latest')
            data = urllib.request.urlopen(rq).read()
            release = data.decode('utf-8').strip()

        if args.layer:
            layername = args.layer
        else:
            # Use same name as branch
            layername = args.branch

        logger.debug('Fetching Clear Linux release %s' % release)

        pkgsrcdir = os.path.join(args.outdir, release, 'source')
        if args.derivative:
            if os.path.exists(pkgsrcdir):
                tmpsrcdir = tempfile.mkdtemp(dir=os.path.join(args.outdir, release))
                shutil.move(pkgsrcdir, tmpsrcdir)

        env = os.environ.copy()
        if args.clear_tool_path:
            if not os.path.exists(os.path.join(args.clear_tool_path, 'dissector')):
                logger.error('No dissector executable found in specified path')
                return 1
            env['PATH'] = args.clear_tool_path + ':' + env['PATH']
        cmd = ['dissector', '-clear_version', release]
        if args.bundles_url:
            cmd += ['-bundles_url', args.bundles_url]
        if args.repo_url:
            cmd += ['-repo_url', args.repo_url]
        if args.derivative:
            cmd += stdbundles
        else:
            cmd.append('-all')
        logger.debug('Executing %s' % cmd)
        return_code = subprocess.call(cmd, env=env, cwd=os.path.abspath(args.outdir))
        if return_code != 0:
            logger.error('Call to dissector failed')
            return 1

        if args.derivative:
            # Now move the source tree somewhere more permanent (so we can do file diffs)
            pkgnewsrcdir = os.path.join(args.outdir, 'derivative_%s' % args.branch)
            if os.path.exists(pkgnewsrcdir):
                shutil.rmtree(pkgnewsrcdir)
            shutil.move(pkgsrcdir, pkgnewsrcdir)
            pkgsrcdir = pkgnewsrcdir

        cwd = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        pkgdir = os.path.join(args.outdir, release, 'source')
        if args.derivative:
            cmd = ['layerindex/tools/import_otherdistro.py', 'import-clear-derivative', args.branch, layername, pkgsrcdir, srcpath, '--description', '%s %s' % (args.name, release), '--relative-path', args.outdir]
        else:
            cmd = ['layerindex/tools/import_otherdistro.py', 'import-pkgspec', args.branch, layername, pkgsrcdir, '--description', '%s %s' % (args.name, release), '--relative-path', args.outdir]
        if args.update:
            cmd += ['-u', args.update]
        if args.debug:
            cmd.insert(1, '-d')
        logger.debug('Executing %s' % cmd)
        return_code = subprocess.call(cmd, cwd=cwd)
        if return_code != 0:
            logger.error('Importing data failed')
            return 1
    finally:
        shutil.rmtree(tempdir)
        if tmpsrcdir and os.path.exists(tmpsrcdir):
            shutil.move(tmpsrcdir, pkgsrcdir)

    if not args.no_status:
        skiplist = ['helloworld']
        cmd = ['layerindex/tools/update_classic_status.py', '-b', args.branch, '-l', layername, '-d', '-s', ','.join(skiplist)]
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
    group.add_argument('-r', '--release', help='Clear Linux release (default is latest for Clear Linux upstream, or release specified in tarball for derivative)')
    group.add_argument('-g', '--derivative', help='Import from a derivative source tarball URL, fetched local tarball, or unpacked directory')
    parser.add_argument('-n', '--name', default='Clear Linux', help='Name of distribution (default "%(default)s")')
    parser.add_argument('-o', '--outdir', default='clr-pkgs', help='Output directory (default "%(default)s")')
    parser.add_argument('-u', '--update', help='Update record to associate changes with')
    parser.add_argument('-b', '--branch', help='Branch to use (default "%(default)s")', required=True)
    parser.add_argument('-l', '--layer', help='Layer to use (defaults to same name as specified branch)')
    parser.add_argument('--bundles-url', help='Base URL for downloading release archives of clr-bundles')
    parser.add_argument('--repo-url', help='Base URL for downloading releases')
    parser.add_argument('--no-status', help='Skip updating status', action='store_true')

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
