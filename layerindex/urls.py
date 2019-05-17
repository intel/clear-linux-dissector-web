# layerindex-web - URL definitions
#
# Copyright (C) 2013, 2018 Intel Corporation
#
# Licensed under the MIT license, see COPYING.MIT for details

from django.conf.urls import *
from django.views.generic import TemplateView, DetailView, ListView, RedirectView
from django.views.defaults import page_not_found
from django.core.urlresolvers import reverse_lazy
from layerindex.views import LayerListView, LayerReviewListView, LayerReviewDetailView, RecipeSearchView, \
    MachineSearchView, LayerDetailView, edit_layer_view, delete_layer_view, edit_layernote_view, delete_layernote_view, \
    HistoryListView, EditProfileFormView, AdvancedRecipeSearchView, BulkChangeView, BulkChangeSearchView, \
    bulk_change_edit_view, bulk_change_patch_view, BulkChangeDeleteView, RecipeDetailView, RedirectParamsView, \
    ClassicRecipeSearchView, ClassicRecipeDetailView, ClassicRecipeStatsView, LayerUpdateDetailView, UpdateListView, \
    UpdateDetailView, StatsView, publish_view, LayerCheckListView, BBClassCheckListView, TaskStatusView, \
    ComparisonRecipeSelectView, ComparisonRecipeSelectDetailView, task_log_view, task_stop_view, email_test_view
from layerindex.models import LayerItem, Recipe, RecipeChangeset
from rest_framework import routers
from . import restviews
from django.conf.urls import include

router = routers.DefaultRouter()
router.register(r'branches', restviews.BranchViewSet)
router.register(r'layerItems', restviews.LayerItemViewSet)
router.register(r'layerBranches', restviews.LayerBranchViewSet)
router.register(r'layerDependencies', restviews.LayerDependencyViewSet)
router.register(r'layerMaintainers', restviews.LayerMaintainerViewSet)
router.register(r'layerNotes', restviews.LayerNoteViewSet)
router.register(r'recipes', restviews.RecipeViewSet)
router.register(r'machines', restviews.MachineViewSet)
router.register(r'distros', restviews.DistroViewSet)
router.register(r'classes', restviews.ClassViewSet)
router.register(r'layers', restviews.LayerViewSet, 'layers')

urlpatterns = [
    # FIXME: REST API disabled for now
    #url(r'^api/', include(router.urls)),

    url(r'^layers/$',
        RedirectView.as_view(url=reverse_lazy('layer_list', args=('master',)), permanent=False)),
    url(r'^layer/(?P<slug>[-\w]+)/$',
        RedirectParamsView.as_view(permanent=False), {'redirect_name': 'layer_item', 'branch': 'master'}),
    url(r'^recipes/$',
        RedirectView.as_view(url=reverse_lazy('recipe_search', args=('master',)), permanent=False)),
    url(r'^machines/$',
        RedirectView.as_view(url=reverse_lazy('machine_search', args=('master',)), permanent=False)),
    url(r'^distros/$',
        RedirectView.as_view(url=reverse_lazy('distro_search', args=('master',)), permanent=False)),
    url(r'^classes/$',
        RedirectView.as_view(url=reverse_lazy('class_search', args=('master',)), permanent=False)),

    url(r'^layer/(?P<slug>[-\w]+)/addnote/$',
        edit_layernote_view, {'template_name': 'layerindex/editlayernote.html'}, name="add_layernote"),
    url(r'^layer/(?P<slug>[-\w]+)/editnote/(?P<pk>[-\w]+)/$',
        edit_layernote_view, {'template_name': 'layerindex/editlayernote.html'}, name="edit_layernote"),
    url(r'^layer/(?P<slug>[-\w]+)/deletenote/(?P<pk>[-\w]+)/$',
        delete_layernote_view, {'template_name': 'layerindex/deleteconfirm.html'}, name="delete_layernote"),
    url(r'^recipe/(?P<pk>[-\w]+)/$',
        RecipeDetailView.as_view(
            template_name='layerindex/recipedetail.html'),
        name='recipe'),
    url(r'^layer/(?P<name>[-\w]+)/publish/$', publish_view, name="publish"),
    url(r'^layerupdate/(?P<pk>[-\w]+)/$',
        LayerUpdateDetailView.as_view(
            template_name='layerindex/layerupdate.html'),
        name='layerupdate'),
    url(r'^branch/(?P<branch>[-\w]+)/',
        include('layerindex.urls_branch')),
    url(r'^updates/$',
        UpdateListView.as_view(
            template_name='layerindex/updatelist.html'),
        name='update_list'),
    url(r'^updates/(?P<pk>[-\w]+)/$',
        UpdateDetailView.as_view(
            template_name='layerindex/updatedetail.html'),
        name='update'),
    url(r'^history/$',
        HistoryListView.as_view(
            template_name='layerindex/history.html'),
        name='history_list'),
    url(r'^profile/$',
        EditProfileFormView.as_view(
            template_name='layerindex/profile.html'),
        name="profile"),
    url(r'^about$',
        TemplateView.as_view(
            template_name='layerindex/about.html'),
        name="about"),
    url(r'^stats/$',
        StatsView.as_view(
            template_name='layerindex/stats.html'),
        name='stats'),
    url(r'^comparison/recipes/(?P<branch>[-\w]+)/$',
        ClassicRecipeSearchView.as_view(
            template_name='layerindex/classicrecipes.html'),
        name='comparison_recipe_search'),
    url(r'^comparison/search-csv/(?P<branch>[-\w]+)/$',
        ClassicRecipeSearchView.as_view(
            template_name='layerindex/classicrecipes_csv.txt',
            paginate_by=0,
            content_type='text/csv'),
        name='comparison_recipe_search_csv'),
    url(r'^comparison/stats/(?P<branch>[-\w]+)/$',
        ClassicRecipeStatsView.as_view(
            template_name='layerindex/classicstats.html'),
        name='comparison_recipe_stats'),
    url(r'^comparison/recipe/(?P<pk>[-\w]+)/$',
        ClassicRecipeDetailView.as_view(
            template_name='layerindex/classicrecipedetail.html'),
        name='comparison_recipe'),
    url(r'^comparison/select/(?P<pk>[-\w]+)/$',
        ComparisonRecipeSelectView.as_view(
            template_name='layerindex/comparisonrecipeselect.html'),
        name='comparison_select'),
    url(r'^comparison/selectdetail/(?P<selectfor>[-\w]+)/(?P<pk>[-\w]+)/$',
        ComparisonRecipeSelectDetailView.as_view(
            template_name='layerindex/comparisonrecipeselectdetail.html'),
        name='comparison_select_detail'),

    url(r'^email_test/$',
        email_test_view,
        name='email_test'),
    url(r'^task/(?P<task_id>[-\w]+)/$',
        TaskStatusView.as_view(
            template_name='layerindex/task.html'),
        name='task_status'),
    url(r'^tasklog/(?P<task_id>[-\w]+)/$',
        task_log_view,
        name='task_log'),
    url(r'^stoptask/(?P<task_id>[-\w]+)/$',
        task_stop_view,
        name='task_stop'),
    url(r'^ajax/layerchecklist/(?P<branch>[-\w]+)/$',
        LayerCheckListView.as_view(
            template_name='layerindex/layerchecklist.html'),
        name='layer_checklist'),
    url(r'^ajax/classchecklist/(?P<branch>[-\w]+)/$',
        BBClassCheckListView.as_view(
            template_name='layerindex/classchecklist.html'),
        name='class_checklist'),
    url(r'.*', page_not_found, kwargs={'exception': Exception("Page not Found")})
]
