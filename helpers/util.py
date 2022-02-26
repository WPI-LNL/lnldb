from functools import wraps, partial
from django.utils.text import slugify
from django.utils.crypto import get_random_string


def curry_class(cls, *args, **kwargs):
    return wraps(cls)(partial(cls, *args, **kwargs))


def unique_slug_generator(instance, field, new_slug=None):
    if new_slug is not None:
        slug = new_slug
    else:
        slug = slugify(field)
    Klass = instance.__class__
    max_length = Klass._meta.get_field('slug').max_length
    slug = slug[:max_length]
    existing_obj = Klass.objects.filter(slug=slug).first()

    if existing_obj:
        if existing_obj.pk == instance.pk:
            return slug
        new_slug = "{}-{}".format(slug, get_random_string(6))
        return unique_slug_generator(instance, field, new_slug)
    return slug
