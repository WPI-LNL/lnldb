from django.apps import apps
from django.conf import settings
from django.contrib.sites.shortcuts import get_current_site
from django.core.exceptions import ImproperlyConfigured
from django.template import loader
from django.http import HttpResponseGone, HttpResponseRedirect, HttpResponseNotAllowed
from django.utils.deprecation import MiddlewareMixin

from .models import ResizedRedirect


class SwappableRedirectMiddleware(object):
    # Defined as class-level attributes to be subclassing-friendly.
    response_gone_class = HttpResponseGone
    response_redirect_class = HttpResponseRedirect
    redirect_model = ResizedRedirect

    def __init__(self, get_response=None):
        if not apps.is_installed('django.contrib.sites'):
            raise ImproperlyConfigured(
                "You cannot use RedirectFallbackMiddleware when "
                "django.contrib.sites is not installed."
            )
        self.get_response = get_response

    def process_response(self, request, response):
        # No need to check for a redirect for non-404 responses.
        if response.status_code != 404:
            return response

        full_path = request.get_full_path()
        current_site = get_current_site(request)

        r = None
        try:
            r = self.redirect_model.objects.get(site=current_site, old_path=full_path)
        except self.redirect_model.DoesNotExist:
            pass
        if r is None and settings.APPEND_SLASH and not request.path.endswith('/'):
            try:
                r = self.redirect_model.objects.get(
                    site=current_site,
                    old_path=request.get_full_path(),
                )
            except self.redirect_model.DoesNotExist:
                pass
        if r is not None:
            if r.new_path == '':
                return self.response_gone_class()
            return self.response_redirect_class(r.new_path)

        # No redirect was found. Return the response.
        return response

    def __call__(self, request):
        response = None
        if hasattr(self, 'process_request'):
            response = self.process_request(request)
        if not response:
            response = self.get_response(request)
        if hasattr(self, 'process_response'):
            response = self.process_response(request, response)
        return response


class HttpResponseNotAllowedMiddleware(MiddlewareMixin):
    def process_response(self, request, response):
        if response.status_code != 405:
            return response

        if isinstance(response, HttpResponseNotAllowed) and request.method == "GET":
            context = {'status': '405', 'error_message': 'Method Not Allowed (GET)'}
            response.content = loader.render_to_string("405.html", context=context, request=request)
        return response
