import os
import sys

cwd = os.getcwd()
sys.path.append(cwd)

VENV_DIR = '/home/lnl/env'
APP_DIR = '/home/lnl/lnldb'
INTERP = VENV_DIR + "/bin/python3"

# Switch to new python
if sys.executable != INTERP:
    os.execl(INTERP, INTERP, *sys.argv)

sys.path.append(APP_DIR)
sys.path.append(APP_DIR + '/lnldb')

sys.path.insert(0, VENV_DIR + '/bin')
sys.path.insert(0, VENV_DIR + '/lib/python3.6/site-packages')

os.environ['LD_LIBRARY_PATH'] = VENV_DIR + '/lib'
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
