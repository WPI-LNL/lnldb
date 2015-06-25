from django import test
from django.core.urlresolvers import reverse
from django.conf import settings
import importlib
from django.test import modify_settings, override_settings


class UrlsTest(test.TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        self.credentials = {'username': 'testuser',
                            'password': '12345'}
        extra = {'email': 'abc@foo.com',
                 'is_staff': True,
                 'is_superuser': False}
        extra.update(self.credentials)
        get_user_model().objects._create_user(**extra)

    @override_settings(TEMPLATE_STRING_IF_INVALID='TEMPLATE_WARNING [%s]')
    def test_responses(self, allowed_http_codes=[200, 302, 403],
                       credentials=None, logout_url="", default_kwargs={}, quiet=False):
        """
        Test all pattern in root urlconf and included ones.
        Do GET requests only.
        A pattern is skipped if any of the conditions applies:
            - pattern has no name in urlconf
            - pattern expects any positinal parameters
            - pattern expects keyword parameters that are not specified in @default_kwargs
        If response code is not in @allowed_http_codes, fail the test.
        if @credentials dict is specified (e.g. username and password),
            login before run tests.
        If @logout_url is specified, then check if we accidentally logged out
            the client while testing, and login again
        Specify @default_kwargs to be used for patterns that expect keyword parameters,
            e.g. if you specify default_kwargs={'username': 'testuser'}, then
            for pattern url(r'^accounts/(?P<username>[\.\w-]+)/$'
            the url /accounts/testuser/ will be tested.
        If @quiet=False, print all the urls checked. If status code of the response is not 200,
            print the status code.
        """
        module = importlib.import_module(settings.ROOT_URLCONF)
        if credentials is None and self.credentials:
            credentials = self.credentials
        if credentials:
            res = self.client.login(**credentials)
            self.assertTrue(res)
            if not quiet:
                print("Logging in using %s... %s" % (credentials, res))

        def check_urls(urlpatterns, prefix=''):
            for pattern in urlpatterns:
                if hasattr(pattern, 'url_patterns'):
                    continue
                    # this is an included urlconf
                    new_prefix = prefix
                    if pattern.namespace:
                        new_prefix = prefix + (":" if prefix else "") + pattern.namespace
                    check_urls(pattern.url_patterns, prefix=new_prefix)
                params = {}
                skip = False
                regex = pattern.regex
                if regex.groups > 0:
                    # the url expects parameters
                    # use default_kwargs supplied
                    if regex.groups > len(regex.groupindex.keys()) \
                            or set(regex.groupindex.keys()) - set(default_kwargs.keys()):
                        # there are positional parameters OR
                        # keyword parameters that are not supplied in default_kwargs
                        # so we skip the url
                        skip = True
                        skipreason = "Unknown Arguments"
                    else:
                        for key in set(default_kwargs.keys()) & set(regex.groupindex.keys()):
                            params[key] = default_kwargs[key]
                if hasattr(pattern, "name") and pattern.name:
                    name = pattern.name
                elif hasattr(pattern, "_callback_str") and pattern._callback_str:
                    name = pattern._callback_str
                else:
                    # if pattern has no name, skip it
                    skip = True
                    skipreason = "Anonymous View"
                    name = ""
                fullname = (prefix + ":" + name) if prefix else name
                if not skip:
                    print("Trying %s %s" % (fullname, params))
                    url = reverse(fullname, kwargs=params)
                    response = self.client.get(url)
                    # print status code if it is not 200
                    status = "" if response.status_code == 200 else str(response.status_code) + " "
                    if response.status_code in (301, 302):
                        status = status + "> " + response["Location"] + " "
                    if not quiet:
                        print(status + url)
                    self.assertIn(response.status_code, allowed_http_codes)
                    if response.status_code in (301, 302):
                        self.assertNotIn('login', response["Location"])
                    self.assertNotIn("TEMPLATE_WARNING", response.content)
                    if credentials:
                        # if we just tested logout, then login again
                        self.client.login(**credentials)
                else:
                    skipreason = skipreason or ""
                    if not quiet:
                        print("SKIP /%s/ : %s [%s]" % (regex.pattern, fullname, skipreason))

        check_urls(module.urlpatterns)
