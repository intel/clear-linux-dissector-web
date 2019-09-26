# layerindex-web - middleware definitions
#
# Copyright (C) 2019 Intel Corporation
#
# Licensed under the MIT license, see COPYING.MIT for details

from django.utils.deprecation import MiddlewareMixin
from django.http import HttpResponseRedirect
from django.core.urlresolvers import reverse
from django.contrib.auth import logout
from reversion.middleware import RevisionMiddleware
import settings
import re
from datetime import datetime

class SessionIdleTimeoutMiddleware(MiddlewareMixin):
    """
    Middleware which implements Session IDLE TIMEOUT every page.
    This requirement can be specified in settings via
    Variables in SESSION_IDLE_TIMEOUT.
    """
    def process_request(self, request):
        if request.user.is_authenticated():
            current_datetime = datetime.timestamp(datetime.now())
            request.session['last_access'] = current_datetime
            if ('last_access' in request.session):
                last = (current_datetime - request.session['last_access'])
                if getattr(settings, 'SESSION_IDLE_TIMEOUT', 0) > 0:
                    if last > settings.SESSION_IDLE_TIMEOUT:
                       logout(request)
                else:
                    return None
        return None

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
