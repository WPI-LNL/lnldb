from django import template
register = template.Library()

@register.filter(is_safe=False)
def sub(value, arg):
    """Subtract the arg from the value."""
    try:
        return int(value) - int(arg)
    except (ValueError, TypeError):
        try:
            return value + arg
        except Exception:
            return ""