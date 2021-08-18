from threading import Thread


def process_in_thread(method):
    """
    Use this decorator to indicate that a method should be processed on a separate thread.

    WARNING: Refrain from interacting with the database while using this decorator (i.e. no read / write). If you do
    access the database, be sure to call ``connection.close()`` (from django.db import connection) at the end of the
    method.
    """

    def decorator(*args, **kwargs):
        t = Thread(target=method, args=args, kwargs=kwargs)
        t.daemon = True
        t.start()
    return decorator
