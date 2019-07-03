# Clear Linux Dissector - view definitions
#
# Copyright (C) 2018-2019 Intel Corporation
#
# Licensed under the MIT license, see COPYING.MIT for details

import os
import sys
from datetime import datetime
from itertools import islice

import reversion
from django import forms
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import Permission, User
from django.contrib.messages.views import SuccessMessageMixin
from django.contrib.sites.models import Site
from django.core.exceptions import PermissionDenied
from django.core.urlresolvers import resolve, reverse, reverse_lazy
from django.db import transaction
from django.db.models import Count, Q
from django.db.models.functions import Lower
from django.db.models.query import QuerySet
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_list_or_404, get_object_or_404, render
from django.template.loader import get_template
from django.utils.decorators import method_decorator
from django.utils.html import escape
from django.views.decorators.cache import never_cache
from django.views.generic import DetailView, ListView, TemplateView
from django.views.generic.base import RedirectView
from django.views.generic.edit import (CreateView, DeleteView, FormView,
                                       UpdateView)
from pkg_resources import parse_version

import settings
from dissector.forms import (ImageComparisonCreateForm,
                              ImageComparisonRecipeForm,
                              VersionComparisonForm, ComparisonImportForm)
from dissector.models import (ImageComparison, ImageComparisonRecipe,
                               VersionComparison, VersionComparisonDifference,
                               VersionComparisonFileDiff)
from layerindex.models import (Branch, LayerItem, LayerBranch, ClassicRecipe,
                              Source, Patch, Update)
from layerindex.views import (ClassicRecipeSearchView, ClassicRecipeDetailView,
                              ClassicRecipeLinkWrapper)

from layerindex import tasks, utils



class ImageCompareView(FormView):
    form_class = ImageComparisonCreateForm

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super(ImageCompareView, self).dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super(ImageCompareView, self).get_form_kwargs()
        kwargs.update(request=self.request)
        return kwargs

    def form_valid(self, form):
        import tarfile
        import tempfile
        import shutil
        import codecs
        import json
        import recipeparse
        from collections import OrderedDict
        if not self.request.user.is_authenticated():
            raise PermissionDenied

        patchdir = getattr(settings, 'IMAGE_COMPARE_PATCH_DIR', None)
        if not patchdir:
            raise Exception('IMAGE_COMPARE_PATCH_DIR not set')

        jsdata = []
        tmpoutdir = tempfile.mkdtemp(prefix='layerindex-')
        try:
            def file_cb(fn, tarinfo):
                if fn == 'data.json':
                    with tar.extractfile(tarinfo) as f:
                        tstream = codecs.getreader("utf-8")(f)
                        jsd = json.load(tstream, object_pairs_hook=OrderedDict)
                        jsdata.append(jsd)

            with tarfile.open(None, "r:gz", self.request.FILES['file']) as tar:
                if not utils.check_tar_contents(tar, file_cb):
                    return HttpResponse('Invalid image comparison tarball')
                tar.extractall(tmpoutdir)

            # FIXME recipe file links may not work because versions may not match up (might have built an older version)

            comparison = None
            if jsdata:
                jsdata = jsdata[0]
                with transaction.atomic():
                    branch = Branch()
                    origname = form.cleaned_data['name'].replace(' ', '_')
                    name = origname
                    i = 1
                    while Branch.objects.filter(name=name).exists():
                        i += 1
                        name = '%s_%d' % (origname, i)
                    branch.name = name
                    branch.bitbake_branch = 'N/A'
                    branch.short_description = 'Image comparison %s' % form.cleaned_data['name']
                    if i > 1:
                        branch.short_description += ' (%d)' % i
                    branch.updates_enabled = False
                    branch.comparison = True
                    branch.hidden = True
                    branch.save()

                    # Have a function to create layers on the fly so that we don't create any we don't need to
                    layerbranches = {}
                    def get_layerbranch(layername, local_path):
                        layerbranch = layerbranches.get(layername, None)
                        if layerbranch:
                            return layerbranch
                        actualname = layername
                        if layername == 'meta':
                            actualname = settings.CORE_LAYER_NAME
                        jslayer = jsdata['layers'][layername]
                        layer, created = LayerItem.objects.get_or_create(name=actualname)
                        if created:
                            layer.status = 'X'
                            layer.layer_type = 'M'
                            layer.summary = 'N/A'
                            layer.description = 'N/A'
                            layer.vcs_url = jslayer['vcs_url']
                            layer.comparison = True
                            layer.save()
                        layerbranch = LayerBranch()
                        layerbranch.layer = layer
                        layerbranch.branch = branch
                        layerbranch.vcs_subdir = jslayer.get('vcs_subdir', '')
                        layerbranch.actual_branch = jslayer.get('actual_branch', '')
                        layerbranch.local_path = local_path
                        layerbranch.save()
                        layerbranches[layername] = layerbranch
                        return layerbranch

                    comparison = ImageComparison()
                    comparison.user = self.request.user
                    comparison.name = form.cleaned_data['name']
                    comparison.from_branch = branch
                    comparison.to_branch = form.cleaned_data['to_branch']
                    comparison.save()

                    local_path = str(comparison.id)

                    # Copy patch files
                    extdir = os.path.join(tmpoutdir, os.listdir(tmpoutdir)[0])
                    comppatchdir = os.path.join(patchdir, local_path)
                    os.makedirs(comppatchdir)
                    for entry in os.listdir(extdir):
                        # We skip out the json file by only copying directories
                        entrypath = os.path.join(extdir, entry)
                        if os.path.isdir(entrypath):
                            shutil.move(entrypath, comppatchdir)

                    for pn, jsrecipe in jsdata['recipes'].items():
                        recipe = ImageComparisonRecipe()
                        recipe.comparison = comparison
                        recipe.layerbranch = get_layerbranch(jsrecipe['layer'], local_path)
                        recipe.filepath = os.path.dirname(jsrecipe['filepath'])
                        recipe.filename = os.path.basename(jsrecipe['filepath'])
                        for key,value in jsrecipe.items():
                            if key in ['filepath', 'layer', 'inherits', 'patches', 'source_urls', 'DEPENDS', 'PACKAGECONFIG', 'packageconfig_opts']:
                                continue
                            if key.startswith('EXTRA_OE'):
                                continue
                            keylower = key.lower()
                            if value and hasattr(recipe, keylower):
                                setattr(recipe, keylower, value)
                        recipe.inherits = ' '.join(jsrecipe.get('inherits', []))
                        for confvar in ['EXTRA_OEMESON', 'EXTRA_OECMAKE', 'EXTRA_OESCONS', 'EXTRA_OECONF']:
                            recipe.configopts = jsrecipe.get(confvar, '')
                            if recipe.configopts:
                                break
                        else:
                            recipe.configopts = ''

                        # Cover info
                        cover_recipe = ClassicRecipe.objects.filter(layerbranch__branch=comparison.to_branch).filter(cover_layerbranch__layer__name=recipe.layerbranch.layer.name).filter(cover_pn=pn).first()
                        if cover_recipe:
                            recipe.cover_pn = cover_recipe.pn
                            # FIXME cover_layerbranch needs to be handled specially
                            recipe.cover_layerbranch = cover_recipe.layerbranch
                            # FIXME cover_status might not match
                            recipe.cover_status = cover_recipe.cover_status

                        recipe.sha256sum = jsrecipe.get('filepath', '')

                        recipe.save()

                        # Take care of dependencies
                        depends = jsrecipe.get('DEPENDS', '')
                        packageconfig_opts = jsrecipe.get('packageconfig_opts', {})
                        recipeparse.handle_recipe_depends(recipe, depends, packageconfig_opts)

                        for jsurl in jsrecipe.get('source_urls', []):
                            source = Source()
                            source.recipe = recipe
                            source.url = jsurl
                            source.save()
                        for jspatch in jsrecipe.get('patches', []):
                            patch = Patch()
                            patch.recipe = recipe
                            patch.path = jspatch[1]
                            # FIXME handle bbappends - this is will only work for patches in the original recipe (also fetched patches)
                            patch.src_path = os.path.relpath(patch.path, recipe.filepath)
                            try:
                                patchfn = os.path.join(comppatchdir, pn, os.path.basename(patch.path))
                                patch.read_status_from_file(patchfn)
                                patch.sha256sum = utils.sha256_file(patchfn)
                            except Exception as e:
                                print('Failed to read patch status for %s: %s' % (patch.path, e))
                            patch.save()

        finally:
            shutil.rmtree(tmpoutdir)

        if comparison:
            return HttpResponseRedirect(reverse('image_comparison_search', args=(comparison.id,)))
        else:
            # FIXME handle this properly
            return HttpResponse('Invalid JSON data')

    def get_context_data(self, **kwargs):
        context = super(ImageCompareView, self).get_context_data(**kwargs)
        context['comparisons'] = ImageComparison.objects.filter(user=self.request.user)
        return context


class ImageCompareDetailView(DetailView):
    model = ImageComparison


class ImageCompareRecipeSearchView(ListView):
    context_object_name = 'recipe_list'
    paginate_by = 50

    def get_queryset(self):
        comparison = get_object_or_404(ImageComparison, pk=self.kwargs['pk'])
        if not comparison.user_can_view(self.request.user):
            raise PermissionDenied
        qs = ImageComparisonRecipe.objects.filter(comparison=comparison).order_by(Lower('pn'))
        return ClassicRecipeLinkWrapper(qs)

    def get_context_data(self, **kwargs):
        context = super(ImageCompareRecipeSearchView, self).get_context_data(**kwargs)
        context['comparison'] = get_object_or_404(ImageComparison, pk=self.kwargs['pk'])
        return context

class ImageCompareRecipeDetailView(SuccessMessageMixin, UpdateView):
    form_class = ImageComparisonRecipeForm
    model = ImageComparisonRecipe
    context_object_name = 'recipe'

    def get_success_message(self, cleaned_data):
        return "Comparison saved successfully"

    def get_success_url(self):
        return reverse_lazy('image_comparison_recipe', args=(self.object.id,))

    def get_context_data(self, **kwargs):
        context = super(ImageCompareRecipeDetailView, self).get_context_data(**kwargs)
        recipe = self.get_object()
        if recipe:
            context['packageconfigs'] = recipe.packageconfig_set.order_by('feature')
            context['staticdependencies'] = recipe.staticbuilddep_set.order_by('name')
            cover_recipe = recipe.get_cover_recipe()
            context['cover_recipe'] = cover_recipe
            context['recipes'] = [recipe, cover_recipe]
        context['layerbranch_desc'] = recipe.layerbranch.layer.name
        context['layerbranch_addtext'] = ' (from %s)' % recipe.comparison
        context['to_desc'] = recipe.comparison.to_branch
        context['can_edit'] = self.request.user.is_authenticated()
        return context


class ImageCompareRecipeSelectView(ClassicRecipeSearchView):
    def get_context_data(self, **kwargs):
        context = super(ImageCompareRecipeSelectView, self).get_context_data(**kwargs)
        recipe = get_object_or_404(ImageComparisonRecipe, pk=self.kwargs['pk'])
        if not recipe.comparison.user_can_view(self.request.user):
            raise PermissionDenied
        context['select_for'] = recipe
        context['existing_cover_recipe'] = recipe.get_cover_recipe()
        comparison_form = ImageComparisonRecipeForm(prefix='selectrecipedialog', instance=recipe)
        comparison_form.fields['cover_pn'].widget = forms.HiddenInput()
        comparison_form.fields['cover_layerbranch'].widget = forms.HiddenInput()
        context['comparison_form'] = comparison_form
        context['can_edit'] = recipe.comparison.user_can_edit(self.request.user)
        context['image_comparison'] = True
        return context

    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated():
            raise PermissionDenied

        recipe = get_object_or_404(ImageComparisonRecipe, pk=self.kwargs['pk'])
        form = ImageComparisonRecipeForm(request.POST, prefix='selectrecipedialog', instance=recipe)

        if form.is_valid():
            form.save()
            messages.success(request, 'Changes to image comparison recipe %s saved successfully.' % recipe.pn)
            return HttpResponseRedirect(reverse('image_comparison_recipe', args=(recipe.id,)))
        else:
            # FIXME this is ugly because HTML gets escaped
            messages.error(request, 'Failed to save changes: %s' % form.errors)

        return self.get(request, *args, **kwargs)


class ImageCompareRecipeSelectDetailView(ClassicRecipeDetailView):
    def get_context_data(self, **kwargs):
        context = super(ImageCompareRecipeSelectDetailView, self).get_context_data(**kwargs)
        recipe = get_object_or_404(ImageComparisonRecipe, pk=self.kwargs['selectfor'])
        if not recipe.comparison.user_can_view(self.request.user):
            raise PermissionDenied
        context['select_for'] = recipe
        context['existing_cover_recipe'] = recipe.get_cover_recipe()
        comparison_form = ImageComparisonRecipeForm(prefix='selectrecipedialog', instance=recipe)
        comparison_form.fields['cover_pn'].widget = forms.HiddenInput()
        comparison_form.fields['cover_layerbranch'].widget = forms.HiddenInput()
        context['comparison_form'] = comparison_form
        context['can_edit'] = False
        context['image_comparison'] = True
        return context

    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated():
            raise PermissionDenied

        recipe = get_object_or_404(ImageComparisonRecipe, pk=self.kwargs['selectfor'])
        if not recipe.comparison.user_can_edit(request.user):
            raise PermissionDenied

        form = ImageComparisonRecipeForm(request.POST, prefix='selectrecipedialog', instance=recipe)
        if form.is_valid():
            form.save()
            messages.success(request, 'Changes to image comparison recipe %s saved successfully.' % recipe.pn)
            return HttpResponseRedirect(reverse('image_comparison_recipe', args=(recipe.id,)))
        else:
            # FIXME this is ugly because HTML gets escaped
            messages.error(request, 'Failed to save changes: %s' % form.errors)

        return self.get(request, *args, **kwargs)


def image_compare_patch_view(request, comparison, path):
    if not request.user.is_authenticated():
        raise PermissionDenied

    comparobj = get_object_or_404(ImageComparison, pk=comparison)
    if not comparobj.user_can_view(request.user):
        raise PermissionDenied

    # Basic path security - probably not necessary, but let's just
    # have belt-and-braces
    path = path.lstrip('/')
    if '../' in path:
        # Nope!
        raise Http404;

    from django.utils.encoding import smart_str

    internal_dir = getattr(settings, 'IMAGE_COMPARE_PATCH_DIR')

    actual_file = os.path.join(internal_dir, comparison, path)
    if not os.path.exists(actual_file):
        raise Http404;

    if getattr(settings, 'FILE_SERVE_METHOD', 'direct') == 'nginx':
        internal_prefix = getattr(settings, 'IMAGE_COMPARE_PATCH_INTERNAL_URL_PREFIX')
        redirect_path = os.path.join(internal_prefix, comparison, path)
        response = HttpResponse(content_type='application/force-download')
        file_name = os.path.basename(path)
        response['Content-Disposition'] = 'attachment; filename=%s' % smart_str(file_name)
        response['X-Accel-Redirect'] = smart_str(redirect_path)
        response['Content-Length'] = os.path.getsize(actual_file)
    else:
        from django.http import FileResponse
        response = FileResponse(open(actual_file, 'rb'), content_type='application/force-download')
    return response


class VersionCompareSelectView(FormView):
    form_class = VersionComparisonForm

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super(VersionCompareSelectView, self).dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super(VersionCompareSelectView, self).get_form_kwargs()
        kwargs.update(request=self.request)
        return kwargs

    def form_valid(self, form):
        return HttpResponseRedirect(reverse_lazy('version_comparison', args=(form.cleaned_data['from_branch'].name, form.cleaned_data['to_branch'].name)))


class VersionCompareContentView(TemplateView):
    def render_to_response(self, context, **response_kwargs):
        response = super(VersionCompareContentView, self).render_to_response(context, **response_kwargs)
        response['X-Status'] = context['comparison'].status
        return response

    def get_context_data(self, **kwargs):
        context = super(VersionCompareContentView, self).get_context_data(**kwargs)
        from_branch = get_object_or_404(Branch, name=self.kwargs['from'])
        to_branch = get_object_or_404(Branch, name=self.kwargs['to'])
        if from_branch.is_image_comparison():
            if not from_branch.imagecomparison_from_set.filter(user=self.request.user).exists():
                raise PermissionDenied
        if to_branch.is_image_comparison():
            # Note: imagecomparison_from_set is *not* a mistake below!
            if not to_branch.imagecomparison_from_set.filter(user=self.request.user).exists():
                raise PermissionDenied
        vercmp, created = VersionComparison.objects.get_or_create(from_branch=from_branch, to_branch=to_branch)
        if created or vercmp.status == 'F':
            vercmp.status = 'I'
            vercmp.save()
            try:
                tasks.generate_version_comparison.apply_async((vercmp.id,))
            except:
                vercmp.status = 'F'
                vercmp.save()
                raise
        context['comparison'] = vercmp
        return context

class VersionCompareView(TemplateView):
    def get_context_data(self, **kwargs):
        context = super(VersionCompareView, self).get_context_data(**kwargs)
        from_branch = get_object_or_404(Branch, name=self.kwargs['from'])
        to_branch = get_object_or_404(Branch, name=self.kwargs['to'])
        if from_branch.is_image_comparison():
            if not from_branch.imagecomparison_from_set.filter(user=self.request.user).exists():
                raise PermissionDenied
        if to_branch.is_image_comparison():
            # Note: imagecomparison_from_set is *not* a mistake below!
            if not to_branch.imagecomparison_from_set.filter(user=self.request.user).exists():
                raise PermissionDenied
        context['from_branch'] = from_branch
        context['to_branch'] = to_branch
        return context

class VersionCompareRecipeDetailView(TemplateView):
    def get_context_data(self, **kwargs):
        context = super(VersionCompareRecipeDetailView, self).get_context_data(**kwargs)
        diff = get_object_or_404(VersionComparisonDifference, pk=kwargs['id'])
        if diff.change_type == 'A':
            recipe = diff.to_recipe()
            cover_recipe = None
        else:
            recipe = diff.from_recipe()
            cover_recipe = diff.to_recipe()
        context['diff'] = diff
        context['recipe'] = recipe
        context['cover_recipe'] = cover_recipe
        context['branch'] = recipe.layerbranch.branch
        context['layerbranch_desc'] = str(recipe.layerbranch.branch)
        if cover_recipe:
            context['to_desc'] = str(cover_recipe.layerbranch.branch)
            context['recipes'] = [recipe, cover_recipe]
        else:
            context['recipes'] = [recipe]
        context['package_sources_available'] = diff.package_sources_available()
        return context

class VersionCompareFileDiffView(TemplateView):
    def get_context_data(self, **kwargs):
        context = super(VersionCompareFileDiffView, self).get_context_data(**kwargs)
        diff = get_object_or_404(VersionComparisonDifference, pk=kwargs['id'])
        fdiff, created = VersionComparisonFileDiff.objects.get_or_create(difference=diff)
        if created or fdiff.status == 'F':
            fdiff.status = 'I'
            fdiff.save()
            try:
                tasks.generate_diff.apply_async((fdiff.id,))
            except:
                fdiff.status = 'F'
                fdiff.save()
                raise
        context['fdiff'] = fdiff
        return context


def version_compare_diff_view(request, diff_id):
    if not request.user.is_authenticated():
        raise PermissionDenied

    fdiff = get_object_or_404(VersionComparisonFileDiff, pk=diff_id)
    if fdiff.status == 'S':
        actual_file = fdiff.get_diff_path()
        if not os.path.exists(actual_file):
            raise Http404;

        if getattr(settings, 'FILE_SERVE_METHOD', 'direct') == 'nginx':
            from django.utils.encoding import smart_str
            response = HttpResponse(content_type='text/plain')
            redirect_path = fdiff.get_redirect_path()
            response['X-Accel-Redirect'] = smart_str(redirect_path)
            response['Content-Length'] = os.path.getsize(actual_file)
        else:
            from django.http import FileResponse
            response = FileResponse(open(actual_file, 'rb'), content_type='text/plain')
    elif fdiff.status == 'I':
        response = HttpResponse('loading')
    else:
        response = HttpResponse('failed')
    response['X-Status'] = fdiff.status
    return response


def version_compare_regenerate_view(request, from_branch, to_branch):
    if not request.user.is_authenticated():
        raise PermissionDenied

    vercmp = get_object_or_404(VersionComparison, from_branch__name=from_branch, to_branch__name=to_branch)
    vercmp.delete()
    return HttpResponseRedirect(reverse_lazy('version_comparison', kwargs={'from': from_branch, 'to': to_branch}))


class ComparisonImportView(FormView):
    form_class = ComparisonImportForm

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not self.request.user.is_authenticated():
            raise PermissionDenied

        if not request.user.has_perm('layerindex.update_comparison_branch'):
            raise PermissionDenied

        return super(ComparisonImportView, self).dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        from celery import uuid

        if form.cleaned_data['destination'] == 'E':
            branch = form.cleaned_data['branch']
            if branch.is_image_comparison() or not branch.comparison:
                raise Http404
            branch_name = branch.name
            # Try to split out non-versioned part of description if any
            desc = branch.short_description
            descsplit = desc.rsplit(' ', 1)
            try:
                verpart = int(descsplit[-1])
            except ValueError:
                verpart = 0
            if verpart > 1000:
                desc = descsplit[0]
            else:
                desc = None
        else:
            branch_name = form.cleaned_data['name']
            desc = form.cleaned_data['short_description']

        srcdir = settings.VERSION_COMPARE_SOURCE_DIR
        dissector_path = settings.DISSECTOR_BINDIR

        task_id = uuid()
        # Create this here first, because inside the task we don't have all of the required info
        update = Update(task_id=task_id)
        update.started = datetime.now()
        update.triggered_by = self.request.user
        update.save()
        update_id = update.id

        cmd = ['layerindex/tools/import_clear.py', '-d', '--repo-url', 'https://download.clearlinux.org', '-u', str(update_id), '-p', dissector_path, '-o', srcdir, '-b', branch_name]

        if form.cleaned_data['import_type'] == 'D':
            cmd += ['-g', form.cleaned_data['url']]
        else:
            if not form.cleaned_data['latest']:
                release = form.cleaned_data['release']
                cmd += ['-r', str(release)]

        if desc:
            cmd += ['-n', desc]

        res = tasks.run_update_command.apply_async((branch_name, cmd), task_id=task_id)
        return HttpResponseRedirect(reverse_lazy('task_status', kwargs={'task_id': task_id}))


class FrontPageView(TemplateView):
    def get_context_data(self, **kwargs):
        context = super(FrontPageView, self).get_context_data(**kwargs)
        context['first_comparison_branch'] = Branch.objects.filter(comparison=True, hidden=False).order_by('sort_priority', 'id').first()
        context['can_import_comparison'] = self.request.user.has_perm('layerindex.update_comparison_branch')
        return context
