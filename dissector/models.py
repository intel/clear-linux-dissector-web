# Clear Linux Dissector - model definitions
#
# Copyright (C) 2018-2019 Intel Corporation
#
# Licensed under the MIT license, see COPYING.MIT for details

from django.db import models
from django.contrib.auth.models import User
from django.dispatch import receiver
import os
import re

from layerindex.models import Branch, LayerBranch, Recipe, ClassicRecipe

class ImageComparison(models.Model):
    user = models.ForeignKey(User)
    name = models.CharField(max_length=255)
    from_branch = models.ForeignKey(Branch, related_name='imagecomparison_from_set')
    to_branch = models.ForeignKey(Branch, related_name='imagecomparison_to_set')

    class Meta:
        unique_together = ('user', 'name',)

    def user_can_view(self, user):
        if user.is_authenticated():
            if self.user == user or user.is_superuser:
                return True
        return False

    def user_can_edit(self, user):
        return self.user_can_view(user)

    def __str__(self):
        return '%s' % (self.name)

@receiver(models.signals.post_delete, sender=ImageComparison)
def delete_image_compare_patches(sender, instance, *args, **kwargs):
    # Ensure that patches imported with an image comparison get deleted when it is deleted
    import settings
    import shutil
    patchdir = getattr(settings, 'IMAGE_COMPARE_PATCH_DIR', '')
    if patchdir:
        comppatchdir = os.path.join(patchdir, str(instance.id))
        if os.path.isdir(comppatchdir):
            shutil.rmtree(comppatchdir)


class ImageComparisonRecipe(Recipe):
    COVER_STATUS_CHOICES = [
        ('U', 'Unknown'),
        ('N', 'Not available'),
        ('S', 'Distro-specific'),
        ('O', 'Obsolete'),
        ('E', 'Equivalent functionality'),
        ('D', 'Direct match'),
    ]
    comparison = models.ForeignKey(ImageComparison)
    cover_layerbranch = models.ForeignKey(LayerBranch, verbose_name='Covering layer', blank=True, null=True)
    cover_pn = models.CharField('Covering recipe', max_length=100, blank=True)
    cover_status = models.CharField(max_length=1, choices=COVER_STATUS_CHOICES, default='U')
    cover_comment = models.TextField(blank=True)
    sha256sum = models.CharField(max_length=64, blank=True)

    def get_cover_recipe(self):
        if self.cover_layerbranch and self.cover_pn:
            return ClassicRecipe.objects.filter(layerbranch=self.cover_layerbranch).filter(pn=self.cover_pn).first()
        else:
            return None

    def sub_file_url(self, path):
        import settings
        prefix = getattr(settings, 'IMAGE_COMPARE_PATCH_URL_PREFIX', None)
        if prefix:
            return os.path.join(prefix, str(self.comparison.id), self.pn, os.path.basename(path))
        else:
            return ''

    def __str__(self):
        return '%s: %s' % (self.comparison, self.pn)

class VersionComparison(models.Model):
    STATUS_CHOICES = (
        ('I', 'In progress'),
        ('F', 'Failed'),
        ('S', 'Succeeded'),
    )
    from_branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='versioncomparison_from_set')
    to_branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='versioncomparison_to_set')
    status = models.CharField(max_length=1, choices=STATUS_CHOICES, default='I')

    def __str__(self):
        return '%s to %s' % (self.from_branch, self.to_branch)


class VersionComparisonDifference(models.Model):
    CHANGE_TYPE_CHOICES = (
        ('A', 'Add'),
        ('U', 'Upgrade'),
        ('D', 'Downgrade'),
        ('V', 'Version changes'),
        ('R', 'Remove'),
        ('M', 'Modification'),
    )
    comparison = models.ForeignKey(VersionComparison, on_delete=models.CASCADE)
    from_layerbranch = models.ForeignKey(LayerBranch, on_delete=models.CASCADE, related_name='versioncomparisondifference_from_set')
    to_layerbranch = models.ForeignKey(LayerBranch, on_delete=models.CASCADE, related_name='versioncomparisondifference_to_set')
    pn = models.CharField(max_length=100)
    change_type = models.CharField(max_length=1, choices=CHANGE_TYPE_CHOICES)
    oldvalue = models.CharField(max_length=255, blank=True)
    newvalue = models.CharField(max_length=255, blank=True)

    def from_recipe(self):
        if self.comparison.from_branch.is_image_comparison():
            if self.comparison.to_branch.is_image_comparison():
                return ImageComparisonRecipe.objects.filter(layerbranch=self.from_layerbranch, pn=self.pn).first()
            else:
                return ImageComparisonRecipe.objects.filter(layerbranch=self.from_layerbranch, cover_pn=self.pn).first()
        else:
            return ClassicRecipe.objects.filter(layerbranch=self.from_layerbranch, pn=self.pn, deleted=False).first()

    def to_recipe(self):
        if self.comparison.to_branch.is_image_comparison():
            if self.comparison.from_branch.is_image_comparison():
                return ImageComparisonRecipe.objects.filter(layerbranch=self.to_layerbranch, pn=self.pn).first()
            else:
                return ImageComparisonRecipe.objects.filter(layerbranch=self.to_layerbranch, cover_pn=self.pn).first()
        else:
            return ClassicRecipe.objects.filter(layerbranch=self.to_layerbranch, pn=self.pn, deleted=False).first()

    def get_comparison_paths(self):
        if self.change_type in ['A', 'V', 'R']:
            return None, None
        import settings
        srcdir = getattr(settings, 'VERSION_COMPARE_SOURCE_DIR')
        isrcdir = getattr(settings, 'IMAGE_COMPARE_PATCH_DIR')
        from_recipe = self.from_recipe()
        to_recipe = self.to_recipe()
        if self.comparison.from_branch.is_image_comparison():
            from_path = os.path.join(isrcdir, self.from_layerbranch.local_path, from_recipe.pn)
        else:
            from_path = os.path.join(srcdir, self.from_layerbranch.local_path, from_recipe.filepath)
        if self.comparison.to_branch.is_image_comparison():
            to_path = os.path.join(isrcdir, self.to_layerbranch.local_path, to_recipe.pn)
        else:
            to_path = os.path.join(srcdir, self.to_layerbranch.local_path, to_recipe.filepath)
        return from_path, to_path

    def package_sources_available(self):
        if self.change_type in ['A', 'V', 'R']:
            return False
        import settings
        srcdir = getattr(settings, 'VERSION_COMPARE_SOURCE_DIR')
        isrcdir = getattr(settings, 'IMAGE_COMPARE_PATCH_DIR')
        if self.comparison.from_branch.is_image_comparison():
            from_path = os.path.join(isrcdir, self.from_layerbranch.local_path)
        else:
            from_path = os.path.join(srcdir, self.from_layerbranch.local_path)
        if self.comparison.to_branch.is_image_comparison():
            to_path = os.path.join(isrcdir, self.to_layerbranch.local_path)
        else:
            to_path = os.path.join(srcdir, self.to_layerbranch.local_path)
        return os.path.exists(from_path) and os.path.exists(to_path)

    def __str__(self):
        if self.change_type == 'A':
            return 'Added %s' % self.pn
        elif self.change_type == 'U':
            return 'Upgraded %s from %s to %s' % (self.pn, self.oldvalue, self.newvalue)
        elif self.change_type == 'D':
            return 'Downgraded %s from %s to %s' % (self.pn, self.oldvalue, self.newvalue)
        elif self.change_type == 'V':
            return '%s: versions changed from %s to %s' % (self.pn, self.oldvalue, self.newvalue)
        elif self.change_type == 'R':
            return 'Removed %s' % self.pn
        elif self.change_type == 'M':
            # FIXME
            return 'Modified %s' % self.pn


class VersionComparisonFileDiff(models.Model):
    STATUS_CHOICES = (
        ('I', 'In progress'),
        ('F', 'Failed'),
        ('S', 'Succeeded'),
    )
    difference = models.ForeignKey(VersionComparisonDifference, on_delete=models.CASCADE)
    status = models.CharField(max_length=1, choices=STATUS_CHOICES, default='I')

    def get_diff_path(self):
        import settings
        internal_dir = getattr(settings, 'IMAGE_COMPARE_PATCH_DIR')
        return os.path.join(internal_dir, 'version-compare', str(self.difference.comparison.id), '%d.diff' % self.id)

    def get_redirect_path(self):
        import settings
        internal_prefix = getattr(settings, 'IMAGE_COMPARE_PATCH_INTERNAL_URL_PREFIX')
        return os.path.join(internal_prefix, 'version-compare', str(self.difference.comparison.id), '%d.diff' % self.id)

    def __str__(self):
        return str(self.difference)

@receiver(models.signals.post_delete, sender=VersionComparisonFileDiff)
def delete_image_compare_patches(sender, instance, *args, **kwargs):
    # Ensure generated diffs get deleted

    fdiff_file = instance.get_diff_path()
    try:
        os.remove(fdiff_file)
    except FileNotFoundError:
        pass
