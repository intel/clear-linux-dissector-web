# Clear Linux Dissector - URL definitions
#
# Copyright (C) 2018-2019 Intel Corporation
#
# Licensed under the MIT license, see COPYING.MIT for details

from django.conf.urls import *
from django.views.generic import TemplateView, DetailView, ListView, RedirectView
from django.views.defaults import page_not_found
from django.core.urlresolvers import reverse_lazy
from dissector.views import FrontPageView, ImageCompareView, ImageCompareDetailView, \
    ImageCompareRecipeSearchView, ImageCompareRecipeDetailView, ImageCompareRecipeSelectView, \
    ImageCompareRecipeSelectDetailView, image_compare_patch_view, \
    VersionCompareSelectView, VersionCompareView, VersionCompareRecipeDetailView, VersionCompareFileDiffView, \
    version_compare_diff_view, VersionCompareContentView, version_compare_regenerate_view, ComparisonImportView



urlpatterns = [
    url(r'^$',
        FrontPageView.as_view(
            template_name='dissector/frontpage.html'),
        name='frontpage'),

    url(r'^comparison/import/$',
        ComparisonImportView.as_view(
            template_name='dissector/comparisonimport.html'),
        name="comparison_import"),
    url(r'^imagecompare/$',
        ImageCompareView.as_view(
            template_name='dissector/imagecompare.html'),
        name="image_comparison"),
    url(r'^imagecompare/search/(?P<pk>[-\w]+)/$',
        ImageCompareRecipeSearchView.as_view(
            template_name='dissector/imagecomparesearch.html'),
        name='image_comparison_search'),
    url(r'^imagecompare/recipe/(?P<pk>[-\w]+)/$',
        ImageCompareRecipeDetailView.as_view(
            template_name='dissector/imagecomparerecipe.html'),
        name='image_comparison_recipe'),
    url(r'^imagecompare/selectdetail/(?P<selectfor>[-\w]+)/(?P<pk>[-\w]+)/$',
        ImageCompareRecipeSelectDetailView.as_view(
            template_name='layerindex/comparisonrecipeselectdetail.html'),
        name='image_comparison_select_detail'),
    url(r'^imagecompare/select/(?P<pk>[-\w]+)/(?P<branch>[-\w]+)/$',
        ImageCompareRecipeSelectView.as_view(
            template_name='layerindex/comparisonrecipeselect.html'),
        name='image_comparison_select'),
    url(r'^imagecompare/patch/(?P<comparison>[-\w]+)/(?P<path>.+)$',
        image_compare_patch_view,
        name="image_comparison_patch"),

    url(r'^versioncompare/$',
        VersionCompareSelectView.as_view(
            template_name='dissector/versioncomparisonselect.html'),
        name="version_comparison_select"),
    url(r'^versioncompare/comparison/(?P<from>[-\w]+)/(?P<to>[-\w]+)/$',
        VersionCompareView.as_view(
            template_name='dissector/versioncomparison.html'),
        name="version_comparison"),
    url(r'^versioncompare/comparison_content/(?P<from>[-\w]+)/(?P<to>[-\w]+)/$',
        VersionCompareContentView.as_view(
            template_name='dissector/versioncomparisoncontent.html'),
        name="version_comparison_ajax"),
    url(r'^versioncompare/regenerate/(?P<from_branch>[-\w]+)/(?P<to_branch>[-\w]+)/$',
        version_compare_regenerate_view,
        name="version_comparison_regenerate"),

    url(r'^versioncompare/recipe/(?P<id>[-\w]+)/$',
        VersionCompareRecipeDetailView.as_view(
            template_name='dissector/versioncomparisonrecipe.html'),
        name="version_comparison_recipe"),
    url(r'^versioncompare/diff/(?P<id>[-\w]+)/$',
        VersionCompareFileDiffView.as_view(
            template_name='dissector/versioncomparisonfilediff.html'),
        name="version_comparison_diff"),
    url(r'^versioncompare/diff_file/(?P<diff_id>[-\w]+)/$',
        version_compare_diff_view,
        name="version_comparison_diff_ajax"),
]
