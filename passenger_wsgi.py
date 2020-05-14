import os
import sys


cwd = os.getcwd()
sys.path.append(cwd)
sys.path.append('/home/lnl/lnldb')

INTERP = "/home/lnl/bin/python2.7"

# Switch to new python
if sys.executable != INTERP:
    os.execl(INTERP, INTERP, *sys.argv)

os.environ['LD_LIBRARY_PATH'] += ":/home/lnl/lib"
os.environ['DJANGO_SETTINGS_MODULE'] = "lnldb.settings"
from django.core.wsgi import get_wsgi_application  # NOQA isort:skip
application = _application = get_wsgi_application()

## Test application (for when importing doesn't work)
# def application(env, start_response):
#     start_response('200 OK', [('Content-Type','text/html')])
#     try:
#	application = get_wsgi_application()
#     except Exception, e:
#         return str(e)
