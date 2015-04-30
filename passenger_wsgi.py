import sys
import os

cwd = os.getcwd()
sys.path.append('/isihome/lnl/lnldb')

INTERP = "/isihome/lnl/bin/python2.7"

# Switch to new python
if sys.executable != INTERP:
    os.execl(INTERP, INTERP, *sys.argv)

os.environ['DJANGO_SETTINGS_MODULE'] = "lnldb.settings"
from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()

# Test application (for when importing doesn't work)
# def application(env, start_response):
#     start_response('200 OK', [('Content-Type','text/html')])
#     return str(os.environ) + str(sys.version) + str(sys.argv)
