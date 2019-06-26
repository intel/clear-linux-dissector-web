# layerindex-web - middleware definitions
#
# Copyright (C) 2019 Intel Corporation
#
# Licensed under the MIT license, see COPYING.MIT for details

from django.utils.deprecation import MiddlewareMixin
from django.http import HttpResponseRedirect
from django.core.urlresolvers import reverse
from reversion.middleware import RevisionMiddleware
import settings
import re

class LoginRequiredMiddleware(MiddlewareMixin):
    """
    Middleware that requires a user to be authenticated to view any page.
    Exemptions to this requirement can optionally be specified
    in settings via a list of regular expressions in LOGIN_EXEMPT_URLS.

    """
    def process_request(self, request):
        try:
            if not request.user.is_authenticated:
                path = request.path_info
                if (not any(re.compile(m).match(path) for m in settings.LOGIN_EXEMPT_URLS)) and not reverse('login') == path:
                    return HttpResponseRedirect(reverse('login'))
        except AttributeError:
            return HttpResponseRedirect(reverse('login'))


class NonAtomicRevisionMiddleware(RevisionMiddleware):
    atomic = False
