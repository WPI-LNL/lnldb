import re
from django import template
from django.conf import settings

numeric_test = re.compile("^\d+$")
register = template.Library()


def getattribute(value, arg):
    """Gets an attribute of an object dynamically from a string name"""

    if hasattr(value, str(arg)):
        return getattr(value, str(arg))
    else:
        print "Invalid %s in %s" % (arg, value)
        return settings.TEMPLATE_STRING_IF_INVALID


register.filter('getattribute', getattribute)
