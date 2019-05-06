#!/usr/bin/env python3

# Export distro differences as a layer containing bbappends
#
# Copyright (C) 2019 Intel Corporation
#
# Licensed under the MIT license, see COPYING.MIT for details

import sys
import os
import argparse
import subprocess
import logging
import re

sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), '..')))

import utils
import recipeparse

logger = utils.logger_create('LayerExport')

def hash_patch(pfn):
    import hashlib
    shash = hashlib.sha256()
    with open(pfn, 'rb') as f:
        started = False
        for line in f:
            if line.startswith(b'---'):
                continue
            elif started:
                shash.update(line)
            elif line.startswith(b'+++'):
                shash.update(line)
                started = True
    return shash.hexdigest()

def filter_urls(urls):
    outurls = []
    files = []
    for url in urls:
        if '://' in url:
            outurls.append(url)
        else:
            files.append(url)
    return outurls, files

def compare_url_list(urls1, urls2):
    def normalise_list(inlist):
        outlist = []
        for url in inlist:
            url = url.replace('://mirrors.kernel.org/gnu/', '://ftp.gnu.org/gnu/')
            if 'sourceforge.net/' in url:
                pkg = re.search(r'/projects?/([^/]+)/', url)
                if not pkg:
                    pkg = re.search(r'sourceforge.net/([^/]+)/', url)
                if pkg:
                    url = 'https://downloads.sourceforge.net/%s/%s' % (pkg.groups()[0], url.split('/')[-1])
            url = url.replace('://mirrors.kernel.org/pub/', '://www.kernel.org/pub/')
            url = url.replace('://cdn.kernel.org/pub/', '://www.kernel.org/pub/')
            url = url.replace('://download.gnome.org/sources/', '://ftp.gnome.org/pub/GNOME/sources/')
            url = url.replace('://pypi.debian.net/docutils/', '://downloads.sourceforge.net/docutils/')
            url = url.replace('://www.x.org/', '://xorg.freedesktop.org/')
            url = url.replace('://archive.apache.org/', '://www.apache.org/')
            url = url.replace('ftp://ftp.gnupg.org/', 'https://www.gnupg.org/ftp/')
            url = url.replace('://xorg.freedesktop.org/releases/individual/xcb/', '://xcb.freedesktop.org/dist/')
            url = url.replace('://www.sudo.ws/dist/', '://ftp.sudo.ws/sudo/dist/')
            url = url.replace('://rsync.samba.org/ftp/', '://download.samba.org/pub/')
            url = url.replace('://samba.org/ftp/', '://download.samba.org/pub/')
            url = url.replace('ftp://ftp.alsa-project.org/pub/', 'https://www.alsa-project.org/files/pub/')
            url = re.sub(r'://cpan.metacpan.org/authors/id/[^/]/[^/]+/[^/]+/', '://cpan.metacpan.org/fakeurl/', url)
            url = re.sub(r'://www.cpan.org/modules/by-module/[^/]+/', '://cpan.metacpan.org/fakeurl/', url)
            url = re.sub(r'://search.cpan.org/CPAN/authors/id/[^/]/[^/]+/[^/]+/', '://cpan.metacpan.org/fakeurl/', url)
            url = re.sub(r'://www.cpan.org/authors/id/[^/]/[^/]+/[^/]+/', '://cpan.metacpan.org/fakeurl/', url)
            url = re.sub(r'://files.pythonhosted.org/packages/source/[^/]/[^/]+/', r'://pypi.fakeurl/', url)
            url = re.sub(r'://files.pythonhosted.org/packages/[^/]/[^/]+/[^/]+/', r'://pypi.fakeurl/', url)
            url = re.sub(r'://pypi.debian.net/[^/]+/', r'://pypi.fakeurl/', url)
            url = url.replace('http:', 'https:')
            url = url.replace('.tar.xz', '.tar.gz')
            url = url.replace('.tar.bz2', '.tar.gz')
            url = re.sub('/[aA]rchive/', '/', url)
            url = url.replace('/fossils/', '/')
            url = url.replace('://www.', '://')
            outlist.append(url)
        return sorted(outlist)

    return normalise_list(urls1) == normalise_list(urls2)


def write_bbappend(args, recipe, cover_recipe, cover_layerdir, rd):
    import oe.recipeutils
    from django.db.models import Q
    from layerindex.models import PatchDisposition

    cover_patch_hashes = []
    for patch in cover_recipe.patch_set.all():
        pfn = os.path.join(cover_layerdir, patch.path)
        sha256sum = hash_patch(pfn)
        cover_patch_hashes.append(sha256sum)

    if recipe.pv == cover_recipe.pv:
        rsources, rfiles = filter_urls(recipe.source_set.exclude(url__endswith='.sig').exclude(url__endswith='.asc').values_list('url', flat=True))
        crsources, _ = filter_urls(cover_recipe.source_set.values_list('url', flat=True))
        if not compare_url_list(rsources, crsources):
            logger.info('%s: [%s] != [%s]' % (cover_recipe.pn, ', '.join(rsources), ', '.join(crsources)))
        if rfiles:
            logger.info('%s: extra files: [%s]' % (cover_recipe.pn, ', '.join(rfiles)))
    else:
        logger.info('%s: version %s != %s' % (cover_recipe.pn, recipe.pv, cover_recipe.pv))

    srcfiles = {}
    patches = []
    for patch in recipe.patch_set.filter(Q(patchdisposition__isnull=True) | Q(patchdisposition__disposition='A')):
        pfn = os.path.join(args.srcdir, patch.path)
        sha256sum = hash_patch(pfn)
        if sha256sum in cover_patch_hashes:
            if not PatchDisposition.objects.filter(patch=patch).exists():
                logger.info('Marking patch %s as existing' % patch)
                pa = PatchDisposition(patch=patch)
                pa.disposition = 'E'
                pa.comment = 'Set automatically by export_layer'
                pa.save()
                continue
        if not patch.applied:
            if not PatchDisposition.objects.filter(patch=patch).exists():
                logger.info('Marking patch %s as invalid (since it is not being applied)' % patch)
                pa = PatchDisposition(patch=patch)
                pa.disposition = 'I'
                pa.comment = 'Set automatically by export_layer (as patch is not being applied)'
                pa.save()
                continue
        srcfiles[pfn] = None
        params = []
        if patch.striplevel != 1:
            params.append('striplevel=%s' % patch.striplevel)
        patches.append((pfn, params))

    vals = {}
    if vals or srcfiles:
        bbappend, _ = oe.recipeutils.bbappend_recipe(rd, args.outdir, srcfiles, None, wildcardver=True, extralines=vals)
        if patches:
            # FIXME this should be made possible within bbappend_recipe()
            pvalues = {}
            srcuri = []
            for pfn, params in patches:
                if params:
                    paramstr = ';' + (';'.join(params))
                else:
                    paramstr = ''
                srcuri.append('file://%s%s' % (os.path.basename(pfn), paramstr))
            pvalues['SRC_URI'] = ('+=', ' '.join(srcuri))
            oe.recipeutils.patch_recipe_file(bbappend, pvalues, patch=False)


def export_layer(args):
    utils.setup_django()
    import settings
    from layerindex.models import Branch, LayerItem, LayerBranch, ClassicRecipe, Patch
    from django.db import transaction

    from layerindex.models import LayerItem, LayerBranch

    branch = utils.get_branch(args.branch)
    if not branch:
        logger.error('Specified branch %s is not valid' % args.branch)
        return 1

    if args.layer:
        layername = args.layer
    else:
        layername = args.branch

    layer = LayerItem.objects.filter(name=layername).first()
    if not layer:
        logger.error('Cannot find specified layer "%s"' % args.layer)
        return 1

    layerbranch = layer.get_layerbranch(args.branch)
    if not layerbranch:
        logger.error('Layer %s does not currently exist on branch %s' % (args.layer, args.branch))
        return 1

    if not os.path.exists(os.path.join(args.outdir, 'conf', 'layer.conf')):
        logger.error('Output directory %s is not a layer (use "bitbake-layers create-layer" to create it first)' % (args.outdir))
        return 1

    master_branch = utils.get_branch('master')
    fetchdir = settings.LAYER_FETCH_DIR
    bitbakepath = os.path.join(fetchdir, 'bitbake')

    if not os.path.exists(bitbakepath):
        sys.stderr.write("Unable to find bitbake checkout at %s" % bitbakepath)
        sys.exit(1)

    lockfn = os.path.join(fetchdir, "layerindex.lock")
    lockfile = utils.lock_file(lockfn)
    if not lockfile:
        sys.stderr.write("Layer index lock timeout expired\n")
        sys.exit(1)
    try:
        (tinfoil, tempdir) = recipeparse.init_parser(settings, master_branch, bitbakepath, True)
        try:
            utils.setup_core_layer_sys_path(settings, master_branch.name)

            # Start writing out log
            logfile = os.path.join(args.outdir, 'export_layer.log')
            try:
                os.remove(logfile)
            except FileNotFoundError:
                pass
            fh = logging.FileHandler(logfile)
            formatter = logging.Formatter('%(levelname)s: %(message)s')
            fh.setFormatter(formatter)
            logger.addHandler(fh)

            logger.info('Exporting ' + str(branch))

            cover_layerbranch = None
            recipequery = ClassicRecipe.objects.filter(layerbranch=layerbranch, deleted=False, cover_status='D', export='X')
            if args.cover_layers:
                recipequery = recipequery.filter(cover_layerbranch__layer__name__in=args.cover_layers.split(','))
            for recipe in recipequery.order_by('cover_layerbranch', 'pn'):
                cover_recipe = recipe.get_cover_recipe()
                if not cover_recipe:
                    logger.warn('Missing cover recipe for recipe %s that has "Direct match" cover type' % recipe.pn)
                    continue
                if recipe.cover_layerbranch != cover_layerbranch:
                    cover_layerbranch = recipe.cover_layerbranch
                    layerfetchdir = os.path.join(fetchdir, cover_layerbranch.layer.get_fetch_dir())
                    utils.checkout_layer_branch(cover_layerbranch, layerfetchdir)
                    cover_layerdir = os.path.join(layerfetchdir, cover_layerbranch.vcs_subdir)
                    config_data_copy = recipeparse.setup_layer(tinfoil.config_data, fetchdir, cover_layerdir, cover_layerbranch.layer, cover_layerbranch, logger)
                    config_data_copy.setVar('BBLAYERS', ' '.join([cover_layerdir, args.outdir]))
                recipefile = str(os.path.join(layerfetchdir, cover_layerbranch.vcs_subdir, cover_recipe.filepath, cover_recipe.filename))
                rd = tinfoil.parse_recipe_file(recipefile, appends=False, config_data=config_data_copy)
                write_bbappend(args, recipe, cover_recipe, cover_layerdir, rd)
        finally:
            tinfoil.shutdown()
    finally:
        utils.unlock_file(lockfile)

    return 0

def main():
    parser = argparse.ArgumentParser(description="Layer export utility")

    parser.add_argument('-d', '--debug', help='Enable debug output', action='store_true')
    parser.add_argument('srcdir', help='Source directory (for patches)')
    parser.add_argument('outdir', help='Output directory')
    parser.add_argument('-b', '--branch', default='clearlinux', help='Branch to use (default "%(default)s")')
    parser.add_argument('-l', '--layer', help='Layer to use (defaults to same name as branch)')
    parser.add_argument('-L', '--cover-layers', help='Limit to specific covering layers (comma-separated list)')

    args = parser.parse_args()

    if args.debug:
        logger.setLevel(logging.DEBUG)

    ret = export_layer(args)

    return ret


if __name__ == "__main__":
    try:
        ret = main()
    except Exception:
        ret = 1
        import traceback
        traceback.print_exc()
    sys.exit(ret)
