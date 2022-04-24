import base64
import qrcode
from django import template
from django.shortcuts import reverse
from django.utils.html import format_html
from io import BytesIO

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


@register.simple_tag(takes_context=True)
def qr_code(context, session, dark_mode=False):
    """
    Generate a QR Code for a Spotify session

    :param context: The view's context dictionary
    :param session: The corresponding session object
    :param dark_mode: If True, will produce a white QR code
    """

    request = context['request']
    code = qrcode.QRCode()
    code.add_data(request.build_absolute_uri(reverse("spotify:request", args=[session.slug])))
    code.make(fit=True)

    stream = BytesIO()
    if dark_mode:
        img = code.make_image(back_color=(27, 28, 29), fill_color=(255, 255, 255))
    else:
        img = code.make_image()
    img.save(stream, format="PNG")
    data = base64.b64encode(stream.getvalue()).decode()
    return format_html("<img style='width: 100&#37;' src='data:image/png;base64,%s' draggable='false'/>" % data)
