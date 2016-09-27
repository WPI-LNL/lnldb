from django import template

register = template.Library()

"""
Decorator to facilitate template tag creation
"""


def easy_tag(func):
    """deal with the repetitive parts of parsing template tags"""
    def inner(parser, token):
        # divide token into args and kwargs
        args = []
        kwargs = {}
        for arg in token.split_contents():
            try:
                name, value = arg.split('=')
                kwargs[str(name)] = value
            except ValueError:
                args.append(arg)
        try:
            # try passing parser as a kwarg for tags that support it
            extrakwargs = kwargs.copy()
            return func(*args, **extrakwargs)
        except TypeError:
            # otherwise just send through the original args and kwargs
            try:
                return func(*args, **kwargs)
            except TypeError as e:
                raise template.TemplateSyntaxError('Bad arguments for tag "%s"' % args[0])
    inner.__name__ = func.__name__
    inner.__doc__ = inner.__doc__
    return inner


class AppendGetNode(template.Node):
    def __init__(self, in_dict):
        self.dict_pairs = {}
        for key in in_dict:
            self.dict_pairs[key] = template.Variable(in_dict[key])

    def render(self, context):
        get = context['request'].GET.copy()

        for key in self.dict_pairs:
            get[key] = self.dict_pairs[key].resolve(context)

        path = context['request'].META['PATH_INFO']

        # print "&".join(["%s=%s" % (key, value) for (key, value) in get.items() if value])

        if len(get):
            path += "?%s" % "&".join(["%s=%s" % (key, value) for (key, value) in get.items() if value])

        return path


@register.tag()
@easy_tag
def append_to_get(_tag_name, **mydict):
    return AppendGetNode(mydict)
