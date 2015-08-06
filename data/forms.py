from crispy_forms.bootstrap import FormActions
from crispy_forms.layout import LayoutObject, Button, Submit, Reset
from crispy_forms.utils import TEMPLATE_PACK, render_field
from django.core.exceptions import ValidationError
from django.forms import FileField

__author__ = 'Killarny'
__author__ = 'Jake Merdich'
# Taken from https://djangosnippets.org/snippets/1148/ (it was exactly what I needed)

from django import forms


class FieldAccessLevel:
    """Represents an access level for a form."""

    def __init__(self, rule, enable=None, exclude=None):
        self.rule = rule
        self.enable = enable
        self.exclude = exclude


class FieldAccessForm(forms.ModelForm):
    """This class will grant or deny access to individual fields according
    to simple rules.

    Example:

    class MyForm(FieldAccessForm):
        class FieldAccess:
            staff = FieldAccessLevel(lambda u, i: u.is_staff,
                enable = ('field1', 'field2'),
                exclude = ('field3',))
    """

    def __init__(self, request_user, *args, **kwargs):
        super(FieldAccessForm, self).__init__(*args, **kwargs)
        self.user = request_user
        if self.user.is_superuser:
            # superuser has full access to all fields
            return
        instance = kwargs.get('instance', None)
        # get available access levels
        access_levels = list()
        for FieldAccess in (getattr(self, 'FieldAccess', None),
                            getattr(self.Meta.model, 'FieldAccess', None)):
            if not FieldAccess:
                continue
            for attr in dir(FieldAccess):
                if attr.startswith('_'):
                    continue
                access_levels += [getattr(FieldAccess, attr)]
        # for any access level which the user falls under, retrieve the field
        # access data for those levels
        enable = []
        exclude = []
        for level in access_levels:
            if not level.rule(self.user, instance):
                continue
            if level.enable:
                enable += level.enable
            if level.exclude:
                exclude += level.exclude

        # disable all fields except those in enable or exclude
        for field_name, field in self.fields.items():
            if exclude and field_name in exclude:
                self.fields.pop(field_name)
            elif not enable or field_name not in enable:
                field.widget.attrs['readonly'] = 'readonly'
                field.widget.attrs['disabled'] = 'disabled'
                field.disabled = True
                field.required = False
                field.value = getattr(instance, field_name, '')

    def _clean_fields(self):
        for name, field in self.fields.items():
            # value_from_datadict() gets the data from the data dictionaries.
            # Each widget type knows how to retrieve its own data, because some
            # widgets split data over several HTML fields.

            # ignore errors and don't store values if a field is disabled
            if getattr(field, 'disabled', False):
                continue

            value = field.widget.value_from_datadict(self.data, self.files, self.add_prefix(name))
            try:
                if isinstance(field, FileField):
                    initial = self.initial.get(name, field.initial)
                    value = field.clean(value, initial)
                else:
                    value = field.clean(value)
                self.cleaned_data[name] = value
                if hasattr(self, 'clean_%s' % name):
                    value = getattr(self, 'clean_%s' % name)()
                    self.cleaned_data[name] = value
            except ValidationError as e:
                self.add_error(name, e)


class DynamicFieldContainer(LayoutObject):
    def __init__(self, *fields):
        self.fields = fields

    def render(self, form, form_style, context, template_pack=TEMPLATE_PACK):
        fields = ''
        for field in self.fields:
            try:
                fields += render_field(field, form, form_style, context, template_pack=template_pack)
            except Exception:
                # I really wish dcf had better exception handling
                continue
        return fields


class Cancel(Button):
    template = '%s_cancel_btn.html'

    def __init__(self, name, value, href=None, onclick=None, **kwargs):
        self.href = href
        self.onclick = onclick
        # take those two out of flatargs, so we can replace them if we want
        super(Cancel, self).__init__(name, value, **kwargs)


# if we change template packs, remove the formactions bit.
def FormFooter(name, *args, **kwargs):
    return FormActions(
        Submit('save_btn', name),
        Cancel('cancel_btn', 'Cancel', css_class='btn-info'),
        Reset('reset_btn', 'Reset form', css_class='btn-inverse'),
        *args, **kwargs
    )
