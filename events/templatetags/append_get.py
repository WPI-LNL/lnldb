from django import template

register = template.Library()

@register.simple_tag(takes_context=True)
def append_to_get(context, replace=True, **kwargs):
    """
    Adds/deletes arguments to the current GET value
     and returns a querystring containing it.

    @argument replace: If true, any existing argument
      named in kwargs will have their value overridden.
      If false, kwargs are appended only.
    @argument kwargs: key-val pairs to add, with a value of 
      None for deletion. (Use "None" if you don't want that)
    """
    updated = context['request'].GET.copy()

    if not replace:
        # duplicates will be appended to the query
        updated.update(kwargs)
    else:
        # duplicates will be replaced
        for arg, val in kwargs.items():
            updated[arg] = val

    # if the kwarg is None delete it instead
    for arg, val in kwargs.items():
        if val is None:
            updated.pop(arg)
    if updated:
        return "?" + updated.urlencode()
    else:
        return ""
