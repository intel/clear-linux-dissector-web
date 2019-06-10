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
import shutil
import errno
import tempfile

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


def get_patches(recipe, srcdir, cover_patch_hashes):
    from django.db.models import Q
    from layerindex.models import PatchDisposition

    srcfiles = {}
    patches = []
    for patch in recipe.patch_set.filter(Q(patchdisposition__isnull=True) | Q(patchdisposition__disposition='A')):
        pfn = os.path.join(srcdir, patch.path)
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
    return patches, srcfiles


def patches_to_srcuri(patches, srcuri):
    for pfn, params in patches:
        if params:
            paramstr = ';' + (';'.join(params))
        else:
            paramstr = ''
        srcuri.append('file://%s%s' % (os.path.basename(pfn), paramstr))


def write_bbappend(args, layerdir, recipe, cover_recipe, cover_layerdir, rd):
    import oe.recipeutils

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

    patches, srcfiles = get_patches(recipe, args.srcdir, cover_patch_hashes)

    # FIXME this hack shouldn't be necessary!
    oe.recipeutils.list_vars.append('SRC_URI_append')
    oe.recipeutils.list_vars.append('SRC_URI_append_class-target')

    vals = {}
    if vals or srcfiles:
        bbappend, _ = oe.recipeutils.bbappend_recipe(rd, layerdir, srcfiles, None, wildcardver=True, extralines=vals)
        if patches:
            # FIXME this should be made possible within bbappend_recipe()
            pvalues = {}
            srcuri = []
            patches_to_srcuri(patches, srcuri)
            if recipe.export_class == 'T':
                srcurivar = 'SRC_URI_append_class-target'
            else:
                srcurivar = 'SRC_URI_append'
            # FIXME we need to use += here because any leading space gets stripped off (!)
            pvalues[srcurivar] = ('+=', ' '.join(srcuri))
            # FIXME this hack probably shouldn't be needed either
            pvalues['SRC_URI'] = None
            oe.recipeutils.patch_recipe_file(bbappend, pvalues, patch=False)


def get_checksums(args, uri):
    if args.dldir:
        dltempdir = None
        dldir = args.dldir
        try:
            os.makedirs(dldir)
        except FileExistsError:
            pass
    else:
        dltempdir = tempfile.mkdtemp()
        dldir = dltempdir
    checksums = {}
    try:
        return_code = subprocess.call(['wget', '-nc', uri], cwd=dldir)
        if return_code != 0:
            logger.error('Failed to fetch source %s' % uri)
            return None
        checksums['sha256sum'] = utils.sha256_file(os.path.join(dldir, os.path.basename(uri)))
        checksums['md5sum'] = utils.md5_file(os.path.join(dldir, os.path.basename(uri)))
    finally:
        if dltempdir:
            shutil.rmtree(dltempdir)
    return checksums


def update_recipe(args, recipe, rd, tinfoil):
    import oe.recipeutils
    import bb.fetch
    import bb.utils
    import settings

    # Get a list of entries in SRC_URI in the recipe to be updated
    # that are not the upstream source or patches (which we will
    # be replacing)
    existing_patches = [os.path.basename(pth) for pth in oe.recipeutils.get_recipe_patches(rd)]
    existing_srcuri = []
    has_defconfig = False
    for entry in rd.getVar('SRC_URI').split():
        scheme, _, pth, _, _, _ = bb.fetch.decodeurl(entry)
        filename = os.path.basename(pth)
        if filename in existing_patches:
            continue
        if scheme != 'file':
            continue
        if filename == 'defconfig':
            has_defconfig = True
        existing_srcuri.append(entry)
    # Get patches we want to add to SRC_URI and copy in
    patches, srcfiles = get_patches(recipe, args.srcdir, [])
    patch_srcuri = []
    patches_to_srcuri(patches, patch_srcuri)
    # Get sources
    src_srcuri = []
    configfile = None
    for entry in recipe.source_set.all().values_list('url', flat=True):
        if '://' in entry:
            src_srcuri.append(entry)
        if not configfile and entry.startswith('config') and not entry.endswith('-sos'):
            configfile = entry
    # Now compose new SRC_URI
    new_srcuri = src_srcuri + patch_srcuri + existing_srcuri
    # Now grab the SRC_URI checksums
    checksums = get_checksums(args, src_srcuri[0])
    if not checksums:
        # Download failed, error already shown
        sys.exit(1)
    # Update the recipe file
    recipefile = rd.getVar('FILE')
    fields = {'SRC_URI': ' '.join(new_srcuri)}
    for csname, value in checksums.items():
        fields['SRC_URI[%s]' % csname] = value
    oe.recipeutils.patch_recipe(rd, recipefile, fields, patch=False)
    if rd.getVar('LINUX_VERSION'):
        # FIXME patch_recipe cannot cope with ?= at the moment so we have to take this approach
        def update_linuxversion_varfunc(varname, origvalue, op, newlines):
            if varname == 'LINUX_VERSION':
               return recipe.pv, None, 0, True
            return origvalue, None, 0, True
        bb.utils.edit_metadata_file(recipefile, ['LINUX_VERSION'], update_linuxversion_varfunc)
    # Copy over patch files
    filesdir = os.path.join(os.path.dirname(recipefile), rd.getVar('PN'))
    try:
        os.makedirs(filesdir)
    except FileExistsError:
        pass
    for pfn in srcfiles.keys():
        shutil.copy2(pfn, filesdir)
    if has_defconfig:
        if configfile:
            # Copy defconfig
            # FIXME code outside of dissector app shouldn't know about this setting - probably need to rename it
            srcdir = getattr(settings, 'VERSION_COMPARE_SOURCE_DIR')
            configpath = os.path.join(srcdir, recipe.layerbranch.local_path, recipe.filepath, configfile)
            if os.path.exists(configpath):
                shutil.copy2(configpath, os.path.join(filesdir, 'defconfig'))
            else:
                logger.warn('%s: unable to find file %s to copy as defconfig' % (recipe.pn, configpath))
        else:
            logger.warn('%s: unable to find replacement defconfig' % recipe.pn)


def export_layer(args):
    utils.setup_django()
    import settings
    from layerindex.models import Branch, LayerItem, LayerBranch, ClassicRecipe, Patch
    from django.db.models import Q
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

    if args.subdir:
        subdir = args.subdir.lstrip(os.sep)
        outlayerdir = os.path.join(args.outdir, subdir)
    else:
        outlayerdir = args.outdir

    if args.fetch_layer:
        try:
            # Note: we do mean args.outdir here and not outlayerdir
            os.makedirs(args.outdir)
        except FileExistsError:
            pass
        if os.path.exists(outlayerdir) and os.listdir(outlayerdir):
            logger.error('Output subdirectory %s is not empty - cannot fetch into it' % outlayerdir)
            return 1
        cmd = ['git', 'clone', args.fetch_layer, '.']
        logger.debug('Executing %s' % cmd)
        # Note: we do mean args.outdir here and not outlayerdir
        return_code = subprocess.call(cmd, cwd=os.path.abspath(args.outdir))
        if return_code != 0:
            logger.error('Fetch of %s failed' % args.fetch_layer)
            return 1
        if args.fetch_revision:
            cmd = ['git', 'checkout', args.fetch_revision]
            logger.debug('Executing %s' % cmd)
            # Note: we do mean args.outdir here and not outlayerdir
            return_code = subprocess.call(cmd, cwd=os.path.abspath(args.outdir))
            if return_code != 0:
                logger.error('Checkout of %s failed' % args.fetch_revision)
                return 1

    if not os.path.exists(os.path.join(outlayerdir, 'conf', 'layer.conf')):
        logger.error('Output directory %s is not a layer (it must already be created)' % (outlayerdir,))
        return 1

    if args.patch and not os.path.exists(os.path.join(args.outdir, '.git')):
        logger.error('Output directory must be a git repository if specifying -p/--patch')
        return 1

    if args.patch and os.path.exists(args.patch):
        logger.error('Output patch file %s already exists' % args.patch)
        return 1

    recipefiles = []
    patchdirs = []
    # Gather all recipes, delete bbappends and gather directories where they exist(ed)
    for root, dirs, files in os.walk(outlayerdir):
        for fn in files:
            fp = os.path.join(root, fn)
            if fp.endswith('.bbappend'):
                os.remove(fp)
                patchdirs.append(os.path.dirname(fp))
            elif fp.endswith('.bb'):
                recipefiles.append(fp)
                patchdirs.append(os.path.dirname(fp))
    # Delete all subdirs of recipe/bbappend dirs (i.e. patch directories)
    for patchdir in patchdirs:
        try:
            for subdir in os.listdir(patchdir):
                dp = os.path.join(patchdir, subdir)
                if os.path.isdir(dp):
                    shutil.rmtree(dp)
        except FileNotFoundError:
            pass
    # Now delete all empty directories
    for root, dirs, _ in os.walk(outlayerdir, topdown=False):
        for dn in dirs:
            dp = os.path.join(root, dn)
            try:
                os.rmdir(dp)
            except OSError as e:
                if e.errno == errno.ENOTEMPTY:
                    pass

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
        (tinfoil, tempdir) = recipeparse.init_parser(settings, master_branch, bitbakepath, enable_tracking=True)
        try:
            utils.setup_core_layer_sys_path(settings, master_branch.name)

            # Start writing out log
            logfile = os.path.join(outlayerdir, 'export_layer.log')
            try:
                os.remove(logfile)
            except FileNotFoundError:
                pass
            fh = logging.FileHandler(logfile)
            formatter = logging.Formatter('%(levelname)s: %(message)s')
            fh.setFormatter(formatter)
            logger.addHandler(fh)

            logger.info('Exporting ' + str(branch))

            if not args.no_appends:
                # Handle bbappends
                cover_layerbranch = None
                recipeappendquery = ClassicRecipe.objects.filter(layerbranch=layerbranch, deleted=False, cover_status='D', export='X')
                if args.cover_layers:
                    recipeappendquery = recipeappendquery.filter(cover_layerbranch__layer__name__in=args.cover_layers.split(','))

                for recipe in recipeappendquery.order_by('cover_layerbranch', 'pn'):
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
                        config_data_copy.setVar('BBLAYERS', ' '.join([cover_layerdir, outlayerdir]))
                    recipefile = str(os.path.join(layerfetchdir, cover_layerbranch.vcs_subdir, cover_recipe.filepath, cover_recipe.filename))
                    rd = tinfoil.parse_recipe_file(recipefile, appends=False, config_data=config_data_copy)
                    write_bbappend(args, outlayerdir, recipe, cover_recipe, cover_layerdir, rd)

            # Handle recipes
            import oe.recipeutils
            recipequery = ClassicRecipe.objects.filter(layerbranch=layerbranch, deleted=False, export='R')
            if args.cover_layers:
                recipequery = recipequery.filter(Q(cover_layerbranch__layer__name__in=args.cover_layers.split(',')) | Q(cover_layerbranch__isnull=True))
            config_data_copy = recipeparse.setup_layer(tinfoil.config_data, fetchdir, outlayerdir, logger=logger)
            config_data_copy.setVar('BBLAYERS', outlayerdir)
            recipes = {}
            for recipefile in recipefiles:
                rd = tinfoil.parse_recipe_file(recipefile, appends=False)
                recipes[rd.getVar('PN')] = rd
            for recipe in recipequery.order_by('pn'):
                rd = recipes.get(recipe.pn, None)
                if rd is None:
                    logger.warn('Recipe %s is set to export type "Recipe" but was not found in output layer' % recipe.pn)
                    continue
                update_recipe(args, recipe, rd, tinfoil)
        finally:
            tinfoil.shutdown()
    finally:
        utils.unlock_file(lockfile)

    if args.patch:
        if args.patch.endswith('.gz'):
            patch = args.patch[:-3]
        else:
            patch = args.patch
        cmd = ['git', 'add', '-A', '.']
        logger.debug('Executing %s' % cmd)
        return_code = subprocess.call(cmd, cwd=os.path.abspath(args.outdir))
        if return_code != 0:
            logger.error('git add failed')
            return 1

        cmd = ['git', '-c', 'diff.renameLimit=2048', 'diff', '--cached', '-p']
        with open(patch, 'w') as f:
            logger.debug('Executing %s' % cmd)
            return_code = subprocess.call(cmd, cwd=os.path.abspath(args.outdir), stdout=f)
            if return_code != 0:
                logger.error('git diff failed')
                return 1

        if args.patch.endswith('.gz'):
            cmd = ['gzip', patch]
            logger.debug('Executing %s' % cmd)
            return_code = subprocess.call(cmd, cwd=os.path.abspath(args.outdir))
            if return_code != 0:
                logger.error('gzip failed')
                return 1

    return 0

def main():
    parser = argparse.ArgumentParser(description="Layer export utility")

    parser.add_argument('-d', '--debug', help='Enable debug output', action='store_true')
    parser.add_argument('srcdir', help='Source directory (for patches)')
    parser.add_argument('outdir', help='Output directory')
    parser.add_argument('-b', '--branch', default='clearlinux', help='Branch to use (default "%(default)s")')
    parser.add_argument('-l', '--layer', help='Layer to use (defaults to same name as branch)')
    parser.add_argument('-L', '--cover-layers', help='Limit to specific covering layers (comma-separated list)')
    parser.add_argument('-f', '--fetch-layer', help='Fetch the specified git repository into the output directory first')
    parser.add_argument('-r', '--fetch-revision', help='Checkout the specified branch/tag/revision (in conjunction with -f/--fetch-layer)')
    parser.add_argument('-s', '--subdir', help='Specify subdirectory for layer')
    parser.add_argument('-p', '--patch', help='Create a patch to update the layer')
    parser.add_argument('--dldir', help='Specify directory for downloads')
    parser.add_argument('--no-appends', action='store_true', help='Skip writing bbappends (for debugging only)')

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
