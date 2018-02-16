# Django settings for lnldb project.

from __future__ import print_function

import os
import re
import sys
import environ


try:
    from django.urls import reverse, NoReverseMatch
except ImportError:
    from django.core.urlresolvers import reverse, NoReverseMatch


def here(*x):
    return os.path.abspath(os.path.join(os.path.abspath(os.path.dirname(__file__)), *x))


def from_root(*x):
    return here('..', *x)


def from_runtime(*x):
    return here(from_root('runtime'), *x)


env = environ.Env()
env.read_env(from_root(".env"))

GIT_RELEASE = env.str("SOURCE_VERSION", None)
if GIT_RELEASE is None:
    try:
        import raven
        path = from_root('.')
        GIT_RELEASE = raven.fetch_git_sha(path)
    except Exception as e:
        print(e, file=sys.stderr)
        GIT_RELEASE = "unknown build"

sentry_uri = env.get_value("SENTRY_DSN", default=None)
if sentry_uri is not None:
    RAVEN_CONFIG = {
        'dsn': sentry_uri,
        'release': GIT_RELEASE,
    }

TESTING = sys.argv[1:2] == ['test']

DEBUG = env.bool("DEBUG", default=True)

ADMINS = (
    # ('Your Name', 'your_email@example.com'),
    ('LNL Webmaster', 'lnl-w@wpi.edu'),
)

MANAGERS = ADMINS

# important: first of these are used for absolute links in some places
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[]) + ['lnl.wpi.edu', '127.0.0.1', 'localhost', 'users.wpi.edu', 'userweb.wpi.edu']
INTERNAL_IPS = ['127.0.0.1']

if env.str('EMAIL_URL', ""):
    vars().update(env.email_url("EMAIL_URL"))
elif env.str("SENDGRID_USERNAME", ""):
    EMAIL_HOST = 'smtp.sendgrid.net'
    EMAIL_HOST_USER = env.str("SENDGRID_USERNAME")
    EMAIL_HOST_PASSWORD = env.str("SENDGRID_PASSWORD")
    EMAIL_PORT = 587
    EMAIL_USE_TLS = True
elif env.str("MAILGUN_SMTP_LOGIN", ""):
    EMAIL_HOST = env.str("MAILGUN_SMTP_SERVER")
    EMAIL_HOST_USER = env.str("MAILGUN_SMTP_LOGIN")
    EMAIL_HOST_PASSWORD = env.str("MAILGUN_SMTP_PASSWORD")
    EMAIL_PORT = env.int("MAILGUN_SMTP_PORT")
    EMAIL_USE_TLS = True
else:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
    print("Warning: using console as an email server.", file=sys.stderr)

DATABASES = {
    'default': env.db(default="sqlite:///" + from_runtime('lnldb.db'))
}
CCC_PASS = env.str("CCC_PASS", "")
SECRET_KEY = env.str("SECRET_KEY", "I am insecure.")

# options we don't want in our env variables...
for key in DATABASES:
    db = DATABASES[key]
    # use relatively persistent connections
    db['CONN_MAX_AGE'] = 30

    # fix mysql unicode stupidity
    if db['ENGINE'] == 'django.db.backends.mysql':
        if not 'OPTIONS' in db:
            db['OPTIONS'] = {}
        db['OPTIONS'].update({
            'sql_mode': 'TRADITIONAL',
            'charset': 'utf8mb4',
            'init_command': 'SET '
                            'storage_engine=INNODB,'
                            'character_set_connection=utf8mb4,'
                            'collation_connection=utf8mb4_unicode_ci,'
                            'SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED',
        })  # Now we have a mild degree of confidence :-) Oh, MySQL....


SESSION_ENGINE = 'django.contrib.sessions.backends.cached_db'

# Local time zone for this installation. Choices can be found here:
# http://en.wikipedia.org/wiki/List_of_tz_zones_by_name
# although not all choices may be available on all operating systems.
# In a Windows environment this must be set to your system time zone.
TIME_ZONE = 'America/New_York'

# Language code for this installation. All choices can be found here:
# http://www.i18nguy.com/unicode/language-identifiers.html
LANGUAGE_CODE = 'en-us'

SITE_ID = 1

# If you set this to False, Django will make some optimizations so as not
# to load the internationalization machinery.
USE_I18N = False

# If you set this to False, Django will not format dates, numbers and
# calendars according to the current locale.
USE_L10N = True
TIME_FORMAT = "%I:%M %p"
DATETIME_FORMAT = '%Y-%m-%d %H:%M'
TIME_INPUT_FORMATS = ['%I:%M %p', '%I:%M:%S.%f %p', '%I:%M %p',
                      '%I:%M%p', '%I:%M:%S.%f%p', '%I:%M%p',
                      '%H:%M:%S', '%H:%M:%S.%f', '%H:%M']


# If you set this to False, Django will not use timezone-aware datetimes.
USE_TZ = True


if env.str("AWS_ACCESS_KEY_ID", ""):
    DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
    AWS_ACCESS_KEY_ID = env.str('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = env.str('AWS_SECRET_ACCESS_KEY')
    AWS_STORAGE_BUCKET_NAME = env.str('AWS_STORAGE_BUCKET_NAME')
    AWS_S3_REGION_NAME = env.str("AWS_S3_REGION_NAME")
    # if env.str("AWS_S3_HOST", ""):
    #     AWS_S3_HOST = env.str("AWS_S3_HOST")
    S3_USE_SIGV4 = True
else:
    # Absolute filesystem path to the directory that will hold user-uploaded files.
    # Example: "/home/media/media.lawrence.com/media/"
    # noinspection PyUnresolvedReferences
    print("Warning: using local storage for a file store", file=sys.stderr)
    MEDIA_ROOT = env.str("MEDIA_ROOT", from_runtime('media/'))
    MEDIA_URL = '/media/'

# Absolute path to the directory static files should be collected to.
# Don't put anything in this directory yourself; store your static files
# in apps' "static/" subdirectories and in STATICFILES_DIRS.
# Example: "/home/media/media.lawrence.com/static/"
# noinspection PyUnresolvedReferences
STATIC_ROOT = env.str("STATIC_ROOT", from_runtime('static'))

# URL prefix for static files.
# Example: "http://media.lawrence.com/static/"
STATIC_URL = '/static/'

# Additional locations of static files
# noinspection PyUnresolvedReferences
STATICFILES_DIRS = (
    # Put strings here, like "/home/html/static" or "C:/www/django/static".
    # Always use forward slashes, even on Windows.
    # Don't forget to use absolute paths, not relative paths.
    from_root("static"),
)
FILE_UPLOAD_PERMISSIONS = 0o644

# List of finder classes that know how to find static files in
# various locations.
STATICFILES_FINDERS = (
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
    # 'django.contrib.staticfiles.finders.DefaultStorageFinder',
)

_tmpl_loaders = [
    'django.template.loaders.filesystem.Loader',
    'django.template.loaders.app_directories.Loader',
]
if not DEBUG:
    _tmpl_loaders = [('django.template.loaders.cached.Loader', _tmpl_loaders)]


TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [from_root("site_tmpl"), ],
    'OPTIONS': {
        'loaders': _tmpl_loaders,
        'context_processors': [
            'django.template.context_processors.debug',
            'django.template.context_processors.request',
            'django.contrib.auth.context_processors.auth',
            'django.contrib.messages.context_processors.messages',
            'django.template.context_processors.request',  # removed in 1.10
            'django.template.context_processors.static',
            'django.template.context_processors.media',
            'data.context_processors.flags',
            'data.context_processors.revision',
            'data.context_processors.analytics',
            # 'lnldb.processors.staticz',
            'processors.navs',
        ],
        'debug': DEBUG
    },
}]

DEBUG_TOOLBAR_CONFIG = {
    'SHOW_TOOLBAR_CALLBACK': lambda x: DEBUG and x.META['SERVER_NAME'] != "testserver"
}

USE_WHITENOISE = env.bool("USE_WHITENOISE", default=False)
WN_MIDDLEWARE = ('whitenoise.middleware.WhiteNoiseMiddleware',) if USE_WHITENOISE else tuple()

USE_SILKY = not TESTING
SILKY_MIDDLEWARE = (
    'silk.middleware.SilkyMiddleware',
) if USE_SILKY else tuple()

MIDDLEWARE_CLASSES = (
    'django.middleware.common.CommonMiddleware',
) + WN_MIDDLEWARE + (
    'django.contrib.sessions.middleware.SessionMiddleware',
) + SILKY_MIDDLEWARE + (
    'django.middleware.csrf.CsrfViewMiddleware',
    'watson.middleware.SearchContextMiddleware',
    'reversion.middleware.RevisionMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    # Uncomment the next line for simple clickjacking protection:
    # 'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # 'events.middleware.ContactReminderMiddleware',
    'debug_toolbar.middleware.DebugToolbarMiddleware',
    'data.middleware.SwappableRedirectMiddleware',
)

ROOT_URLCONF = 'lnldb.urls'

# Python dotted path to the WSGI application used by Django's runserver.
WSGI_APPLICATION = 'lnldb.wsgi.application'

INSTALLED_APPS = (
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.sites',
    'django.contrib.redirects',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Uncomment the next line to enable the admin:
    'django.contrib.admin',
    # Uncomment the next line to enable admin documentation:
    'django.contrib.admindocs',
    'markdown_deux',
    'django_cas_ng',
    'django_extensions',

    'accounts',
    'events',
    'inventory',
    'data',
    'projection',
    'acct',
    'pages',
    'meetings',
    'emails',
    'members',
    'mptt',

    'bootstrap_toolkit',
    'crispy_forms',
    'lineage',
    'django_bootstrap_calendar',
    'ajax_select',
    'watson',
    'debug_toolbar',
    'raven.contrib.django.raven_compat',
    'permission',
    'reversion',
    'hijack',
    'pagedown',
    'compat',
    'silk',
)
if TESTING:
    # bypass migrations for unit tests. **MUCH** faster
    try:
        import test_without_migrations # NOQA
        INSTALLED_APPS += ('test_without_migrations',)
    except:
        pass

MIGRATION_MODULES = {'redirects': 'data.redirects_migrations'}

SHOW_HIJACKUSER_IN_ADMIN = False
HIJACK_ALLOW_GET_REQUESTS = True
# Needed since Hijack doesn't support custom UserAdmin


GA_ID = env.str("GA_ID", "")

# A sample logging configuration. The only tangible logging
# performed by this configuration is to send an email to
# the site admins on every HTTP 500 error when DEBUG=False.
# See http://docs.djangoproject.com/en/dev/topics/logging for
# more details on how to customize your logging configuration.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse'
        }
    },
    'handlers': {
        'mail_admins': {
            'level': 'ERROR',
            'filters': ['require_debug_false'],
            'class': 'django.utils.log.AdminEmailHandler'
        },
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
        },
        'sentry': {
            'level': 'ERROR', 
            'filters': ['require_debug_false'],
            'class': 'raven.contrib.django.raven_compat.handlers.SentryHandler',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'sentry'],
        },
    }
}

AUTH_USER_MODEL = 'accounts.User'

# AJAX_SELECT_BOOTSTRAP = False
# AJAX_SELECT_INLINES = False
# let's just shit all over the page. its okay. I'm fine with it :-\
AJAX_SELECT_BOOTSTRAP = False
# AJAX_SELECT_INLINES = 'staticfiles'

AJAX_LOOKUP_CHANNELS = {
    'Users': ('accounts.lookups', 'UserLookup'),
    'Orgs': ('events.lookups', 'OrgLookup'),
    'UserLimitedOrgs': ('events.lookups', 'UserLimitedOrgLookup'),
    'Officers': ('accounts.lookups', 'OfficerLookup'),
    'Members': ('accounts.lookups', 'MemberLookup'),
    'AssocMembers': ('accounts.lookups', 'AssocMemberLookup'),
    'Funds': ('events.lookups', 'FundLookup'),
    'FundsLimited': ('events.lookups', 'FundLookupLimited'),
    'EquipmentClass': ('inventory.lookups', 'ClassLookup'),
    'EquipmentContainer': ('inventory.lookups', 'ContainerLookup')
}

AUTHENTICATION_BACKENDS = (
    'django.contrib.auth.backends.ModelBackend',  # default
    'data.backends.PermissionShimBackend',
    'permission.backends.PermissionBackend',
)

# Various Other Settings

# Number of hours to show on the admin landing
LANDING_TIMEDELTA = 72

# Number of days to pass before crew chief reports are locked
CCR_DAY_DELTA = 14

# email stuff
DEFAULT_TO_ADDR = "lnl@wpi.edu"
DEFAULT_FROM_ADDR = 'WPI Lens and Lights <lnl@wpi.edu>'
EMAIL_TARGET_P = "lnl-p@wpi.edu"
EMAIL_TARGET_VP = "lnl-vp@wpi.edu"
EMAIL_TARGET_S = "lnl-s@wpi.edu"
EMAIL_TARGET_T = "lnl-t@wpi.edu"
EMAIL_TARGET_TD = "lnl-td@wpi.edu"
EMAIL_TARGET_W = "lnl-w@wpi.edu"
EMAIL_TARGET_HP = "lnl-hp@wpi.edu"

SEND_EMAIL_ORG_TRANSFER = False
SEND_START_END_EMAILS = False

EMAIL_TARGET_START_END = "gmp@h4xmb.org"
EMAIL_KEY_START_END = None

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/db/"

CAS_FORCE_POST_LOGIN = False

AIRPLANE_MODE = False

# crispy_forms
CRISPY_TEMPLATE_PACK = 'bootstrap3'

# Don't mess with builtins just for the sake of permissions
PERMISSION_REPLACE_BUILTIN_IF = False


def reverse_noexcept(url, args=None, kwargs=None):
    try:
        url_out = reverse(url, args=args, kwargs=kwargs)
    except NoReverseMatch:
        url_out = "#"  # dont change the url
    return url_out


# markdown deux configuration
MARKDOWN_DEUX_STYLES = {
    "default": {
        "link_patterns": [
            (re.compile("\B@([A-Za-z][A-Za-z0-9]*)"),
                lambda m: reverse_noexcept("accounts:by-name:detail",
                                           kwargs={'username': m.group(1)}
                                           )
             ),
            (re.compile("\B@([0-9]+)"),
                lambda m: reverse_noexcept("events:detail",
                                           args=[m.group(1)]
                                           )
             ),
        ],
        "extras": {
            "code-friendly": None,
            "break-on-newline": None,
            "strike": None,
            "smarty-pants": None,
            "tables": None,
            "link-patterns": None
        },
        "safe_mode": "escape",
    },
}
# and for the html editor
EXTENSIONS = ["newlines", "smart-strong", "strikethrough",
              "smartypants", "tables"]

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'lnldb-cache'
    }
}

MPTT_ADMIN_LEVEL_INDENT = 20

# settings for profiler
SILKY_AUTHENTICATION = True          # Must be logged in to see profiler
SILKY_AUTHORISATION = True           # Must be staff to see profiler
SILKY_MAX_RESPONSE_BODY_SIZE = 0     # Don't record bodies of responses
SILKY_MAX_RECORDED_REQUESTS = 1000   # Only save the last n requests
SILKY_META = True                    # Note how much time we take to profile

if env.str("CAS_SERVER_URL", ""):
    CAS_SERVER_URL = env.str("CAS_SERVER_URL")
    #CAS_LOGOUT_COMPLETELY = True
    CAS_REDIRECT_URL = '/db/'
    AUTHENTICATION_BACKENDS = AUTHENTICATION_BACKENDS + (
        'django_cas_ng.backends.CASBackend',
    )
    USE_CAS = True
else:
    USE_CAS = False

# Local Settings Imports
try:
    local_settings_file = open(here('local_settings.py'), 'r')
    local_settings_script = local_settings_file.read()
    exec(local_settings_script)
    print("Successfully loaded local settings file", file=sys.stderr)
except IOError as e:
    pass

if "STATIC_ROOT" in locals() and not os.path.exists(STATIC_ROOT):
    os.makedirs(STATIC_ROOT)

if "MEDIA_ROOT" in locals() and not os.path.exists(MEDIA_ROOT):
    os.makedirs(MEDIA_ROOT)
