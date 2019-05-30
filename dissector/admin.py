# Clear Linux Dissector - admin interface definitions
#
# Copyright (C) 2018-2019 Intel Corporation
#
# Licensed under the MIT license, see COPYING.MIT for details

from dissector.models import *
from django.contrib import admin


class VersionComparisonDifferenceAdmin(admin.ModelAdmin):
    search_fields = ['pn']
    list_filter = ['comparison', 'change_type']
    readonly_fields = ['comparison']
    def has_add_permission(self, request, obj=None):
        return False

class VersionComparisonFileDiffAdmin(admin.ModelAdmin):
    search_fields = ['difference__pn']
    list_filter = ['difference__comparison', 'status']
    readonly_fields = ['difference', 'get_diff_path']
    def has_add_permission(self, request, obj=None):
        return False

admin.site.register(ImageComparison)
admin.site.register(ImageComparisonRecipe)
admin.site.register(VersionComparison)
admin.site.register(VersionComparisonDifference, VersionComparisonDifferenceAdmin)
admin.site.register(VersionComparisonFileDiff, VersionComparisonFileDiffAdmin)
