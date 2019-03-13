from functools import wraps, partial

def curry_class(cls, *args, **kwargs):
    return wraps(cls)(partial(cls, *args, **kwargs))
