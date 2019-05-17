# Clear Linux Dissector - form definitions
#
# Copyright (C) 2018-2019 Intel Corporation
#
# Licensed under the MIT license, see COPYING.MIT for details

import re
from collections import OrderedDict

from django import forms
from django.db.models import Q
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.validators import EmailValidator, RegexValidator, URLValidator
from django.forms.models import inlineformset_factory, modelformset_factory
from django_registration.forms import RegistrationForm
from django_registration.validators import (DEFAULT_RESERVED_NAMES,
                                            ReservedNameValidator,
                                            validate_confusables)

import settings
from layerindex.models import Branch
from dissector.models import (ImageComparisonRecipe,
                               ImageComparison)

from layerindex.forms import StyledForm, StyledModelForm



class VersionComparisonForm(StyledForm):
    from_branch = forms.ModelChoiceField(label='From', queryset=Branch.objects.none())
    to_branch = forms.ModelChoiceField(label='To', queryset=Branch.objects.none())

    def __init__(self, *args, request=None, **kwargs):
        super(VersionComparisonForm, self).__init__(*args, **kwargs)
        qs = Branch.objects.filter(Q(imagecomparison_from_set__isnull=False, imagecomparison_from_set__user=request.user) | Q(imagecomparison_from_set__isnull=True)).distinct().order_by('sort_priority', 'name')
        self.fields['from_branch'].queryset = qs
        self.fields['to_branch'].queryset = qs
        self.request = request


class ImageComparisonCreateForm(forms.Form):
    name = forms.CharField(max_length=50, help_text="Name for the image comparison")
    file = forms.FileField()
    to_branch = forms.ModelChoiceField(queryset=Branch.objects.filter(comparison=True).filter(hidden=False).order_by('name'))

    def __init__(self, *args, request=None, **kwargs):
        super(ImageComparisonCreateForm, self).__init__(*args, **kwargs)
        self.request = request

    def clean_name(self):
        name = self.cleaned_data['name'].strip()
        if name:
            if re.compile(r'[^\w\d., -]').search(name):
                raise forms.ValidationError("Name must only contain alphanumeric characters, spaces, ., - and ,")
            if name.startswith('-'):
                raise forms.ValidationError("Name must not start with a dash")
            if name.endswith('-'):
                raise forms.ValidationError("Name must not end with a dash")
            if '--' in name:
                raise forms.ValidationError("Name cannot contain consecutive dashes")
            if ImageComparison.objects.filter(name=name, user=self.request.user).exists():
                raise forms.ValidationError('You already have an image comparison of this name')
        return name


class ImageComparisonRecipeForm(forms.ModelForm):
    class Meta:
        model = ImageComparisonRecipe
        fields = ('cover_pn', 'cover_layerbranch', 'cover_status', 'cover_comment')

    def clean(self):
        cleaned_data = super(ImageComparisonRecipeForm, self).clean()
        cover_pn = cleaned_data.get('cover_pn')
        cover_layerbranch = cleaned_data.get('cover_layerbranch')
        if cleaned_data.get('cover_status') in ['U', 'N', 'S']:
            if cover_layerbranch:
                cleaned_data['cover_layerbranch'] = None
            if cover_pn:
                cleaned_data['cover_pn'] = ''
        return cleaned_data


class NameBranchChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        if obj.short_description:
            return "%s (%s)" % (obj.short_description, obj.name)
        else:
            return obj.name

class ComparisonImportForm(forms.Form):
    IMPORT_TYPE_CHOICES=[
        ('U','Upstream Clear Linux'),
        ('D','Clear Linux derivative')
        ]
    DESTINATION_CHOICES=[
        ('N','Create new branch'),
        ('E','Update existing branch')
        ]
    import_type = forms.ChoiceField(choices=IMPORT_TYPE_CHOICES, widget=forms.RadioSelect, initial='U')
    destination = forms.ChoiceField(choices=DESTINATION_CHOICES, widget=forms.RadioSelect, initial='E')
    name = forms.CharField(max_length=50, help_text='Name for the new comparison branch (no spaces allowed)', required=False)
    short_description = forms.CharField(max_length=50, help_text='Short description for the new comparison branch', required=False)
    branch = NameBranchChoiceField(queryset=Branch.objects.filter(comparison=True).filter(hidden=False).order_by('name'), required=False)
    release = forms.IntegerField(widget=forms.TextInput, required=False)
    latest = forms.BooleanField(label='Get latest', required=False, initial=True)
    url = forms.CharField(label='Source tarball URL', max_length=255, required=False, help_text='URL to fetch derivative source tarball', widget=forms.URLInput)

    def clean(self):
        cleaned_data = super(ComparisonImportForm, self).clean()
        if cleaned_data['import_type'] == 'U':
            # Clear Linux upstream, if not latest we need a release number
            if not cleaned_data['latest']:
                release = cleaned_data.get('release', '')
                try:
                    release = int(release)
                except ValueError:
                    release = 0
                if not release > 1000:
                    raise forms.ValidationError({'release': 'Release number must be an integer > 1000'})
        else:
            url = cleaned_data.get('url', '[MISSING]')
            if not '://' in url:
                raise forms.ValidationError({'url': 'Invalid release URL'})
        if cleaned_data['destination'] == 'N':
            name = cleaned_data.get('name', '[MISSING]').strip()
            if not name:
                raise forms.ValidationError({'name': 'Name must be specified if creating a new branch'})
        return cleaned_data

    def clean_name(self):
        name = self.cleaned_data['name'].strip()
        if name:
            if re.compile(r'[^a-z0-9-]').search(name):
                raise forms.ValidationError("Name must only contain alphanumeric characters and dashes")
            if name.startswith('-'):
                raise forms.ValidationError("Name must not start with a dash")
            if name.endswith('-'):
                raise forms.ValidationError("Name must not end with a dash")
            if '--' in name:
                raise forms.ValidationError("Name cannot contain consecutive dashes")
            if Branch.objects.filter(name=name).exists():
                raise forms.ValidationError('A branch of this name already exists - select "Update existing branch" instead if that is what you want to do')
        return name
