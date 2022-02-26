from django import template

register = template.Library()


@register.filter()
def artists(data):
    """
    Parses a list of artist objects and returns a list of their names
    """

    output = []
    for artist in data:
        output.append(artist['name'])
    return ', '.join(output)


@register.filter()
def pretty_duration(ms):
    """
    Converts a duration in ms to a minutes and seconds
    """

    minutes = ms // 60000
    seconds = (ms / 1000) - (minutes * 60)
    return "%d:%02d" % (minutes, seconds)
