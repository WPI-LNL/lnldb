# Django settings for lnldb project.

import os
import re
import sys

try:
    from django.urls import reverse, NoReverseMatch
except ImportError:
    from django.core.urlresolvers import reverse, NoReverseMatch


def here(*x):
    return os.path.join(os.path.abspath(os.path.dirname(__file__)), *x)


def from_root(*x):
    return os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', *x)


def from_runtime(*x):
    return os.path.join(from_root('runtime'), *x)


try:
    import raven
    path = from_root('.')
    GIT_RELEASE = raven.fetch_git_sha(path)
except Exception as e:
    print(e)
    GIT_RELEASE = "unknown build"

TESTING = sys.argv[1:2] == ['test']

DEBUG = True

ADMINS = (
    # ('Your Name', 'your_email@example.com'),
)

MANAGERS = ADMINS
ALLOWED_HOSTS = ['127.0.0.1', 'localhost', 'lnl.wpi.edu',
                 'users.wpi.edu', 'userweb.wpi.edu']

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

DATABASES = {
    'default': {  # for testing
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': from_runtime('lnldb.db'),
    }
    # #  mysql template
    # 'default': {
    #     'ENGINE': 'django.db.backends.mysql',
    #     'NAME': 'lnldb2012',
    #     'USER': 'lnlcgi',
    #     'PASSWORD': '<...>',
    #     'HOST': 'mysql.wpi.edu',
    #     'PORT': '',
    #     'CONN_MAX_AGE': 30,
    #     'OPTIONS': {
    #         'sql_mode': 'TRADITIONAL',
    #         'charset': 'utf8mb4',
    #         'init_command': 'SET '
    #             'storage_engine=INNODB,'
    #             'character_set_connection=utf8mb4,'
    #             'collation_connection=utf8mb4_unicode_ci,'
    #             'SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED',
    #     }  # Now we have a mild degree of confidence :-) Oh, MySQL....
    # }
}

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

# Absolute filesystem path to the directory that will hold user-uploaded files.
# Example: "/home/media/media.lawrence.com/media/"
# noinspection PyUnresolvedReferences
MEDIA_ROOT = from_runtime('media/')

# URL that handles the media served from MEDIA_ROOT. Make sure to use a
# trailing slash.
# Examples: "http://media.lawrence.com/media/", "http://example.com/media/"
MEDIA_URL = '/media/'

# Absolute path to the directory static files should be collected to.
# Don't put anything in this directory yourself; store your static files
# in apps' "static/" subdirectories and in STATICFILES_DIRS.
# Example: "/home/media/media.lawrence.com/static/"
# noinspection PyUnresolvedReferences
STATIC_ROOT = from_runtime('static')

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

# List of finder classes that know how to find static files in
# various locations.
STATICFILES_FINDERS = (
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
    # 'django.contrib.staticfiles.finders.DefaultStorageFinder',
)

# Make this unique, and don't share it with anybody.
SECRET_KEY = '*am$3w(-v2p+i)m-6t8f0d%)%g60cr+tj6$_x1_u-$wx^0$fu%'

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
            'django.template.context_processors.request',
            'django.core.context_processors.static',
            'django.core.context_processors.media',
            'data.context_processors.airplane_mode',
            'data.context_processors.revision',
            'data.context_processors.analytics',
            # 'lnldb.processors.staticz',
            'processors.navs',
        ],
        'debug': DEBUG
    },
}]

MIDDLEWARE_CLASSES = (
    'django.middleware.common.CommonMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'watson.middleware.SearchContextMiddleware',
    'reversion.middleware.RevisionMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    # Uncomment the next line for simple clickjacking protection:
    # 'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # 'events.middleware.ContactReminderMiddleware',
    'debug_toolbar.middleware.DebugToolbarMiddleware',
)

ROOT_URLCONF = 'lnldb.urls'

# Python dotted path to the WSGI application used by Django's runserver.
WSGI_APPLICATION = 'lnldb.wsgi.application'

INSTALLED_APPS = (
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.sites',
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
)
if TESTING:
    # bypass migrations for unit tests. **MUCH** faster
    try:
        import test_without_migrations # NOQA
        INSTALLED_APPS += ('test_without_migrations',)
    except:
        pass

SHOW_HIJACKUSER_IN_ADMIN = False
HIJACK_ALLOW_GET_REQUESTS = True
# Needed since Hijack doesn't support custom UserAdmin


GA_ID = ""

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
        }
    },
    'loggers': {
        'django.request': {
            'handlers': ['mail_admins'],
            'level': 'ERROR',
            'propagate': True,
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
CCR_DAY_DELTA = 7

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

SEND_EMAIL_ORG_TRANSFER = True
SEND_START_END_EMAILS = True

EMAIL_TARGET_START_END = "gmp@h4xmb.org"
EMAIL_KEY_START_END = None

LOGIN_URL = "/local/login/"
LOGIN_REDIRECT_URL = "/my/"

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
            (re.compile("@([A-Za-z][A-Za-z0-9]*)"),
                lambda m: reverse_noexcept("accounts:by-name:detail",
                                           kwargs={'username': m.group(1)}
                                           )
             ),
            (re.compile("@([0-9]+)"),
                lambda m: reverse_noexcept("events-detail",
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


# Local Settings Imports
try:
    local_settings_file = open(here('local_settings.py'), 'r')
    local_settings_script = local_settings_file.read()
    exec(local_settings_script)
    print("Successfully loaded local settings file")
except IOError as e:
    pass

if not os.path.exists(STATIC_ROOT):
    os.makedirs(STATIC_ROOT)

if not os.path.exists(MEDIA_ROOT):
    os.makedirs(MEDIA_ROOT)
