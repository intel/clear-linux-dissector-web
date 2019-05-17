# Clear Linux Dissector - admin interface definitions
#
# Copyright (C) 2018-2019 Intel Corporation
#
# Licensed under the MIT license, see COPYING.MIT for details

from dissector.models import *
from django.contrib import admin

admin.site.register(ImageComparison)
admin.site.register(ImageComparisonRecipe)
admin.site.register(VersionComparison)
admin.site.register(VersionComparisonDifference)
admin.site.register(VersionComparisonFileDiff)
