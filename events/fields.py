from __future__ import absolute_import

from itertools import groupby

from django import forms

from .widgets import ExtraSelectorWidget


class ExtraSelectorField(forms.MultiValueField):
    def __init__(self, *args, **kwargs):
        fields = [forms.CharField(required=False) for _ in range(5)]

        self.choices = kwargs.pop("choices")
        super(ExtraSelectorField, self).__init__(fields, *args, **kwargs)
        self.widget = ExtraSelectorWidget(choices=self.choices)


# shamelessly grabbed from http://djangosnippets.org/snippets/2622/
# modified because:
# a, forms.MCI doesnt exist, while forms.models.MCI does
# b, something in the group_label became a string instead of a function

class GroupedModelChoiceField(forms.ModelChoiceField):
    def __init__(self, queryset, group_by_field, group_label=None, *args, **kwargs):
        """
        group_by_field is the name of a field on the model
        group_label is a function to return a label for each choice group
        """
        super(GroupedModelChoiceField, self).__init__(queryset, *args, **kwargs)
        self.group_by_field = group_by_field
        if group_label is None:
            self.group_label = lambda group: group
        else:
            self.group_label = group_label

    def _get_choices(self):
        """
        Exactly as per ModelChoiceField except returns new iterator class
        """
        if hasattr(self, '_choices'):
            return self._choices
        return GroupedModelChoiceIterator(self)

    choices = property(_get_choices, forms.ModelChoiceField.choices)


class GroupedModelChoiceIterator(forms.models.ModelChoiceIterator):
    def __iter__(self):
        if self.field.empty_label is not None:
            yield (u"", self.field.empty_label)
        for group, choices in groupby(self.queryset.all().order_by(self.field.group_by_field),
                                      key=lambda row: getattr(row, self.field.group_by_field)):
            yield (self.field.group_label(group), [self.choice(ch) for ch in choices])


# was going to use this for fancier grouped dropdowns. Leaving it here, but no calls to it
def get_key(row, field):
    if callable(field):
        return field(row)

    for f in field.split("__"):
        row = getattr(row, f)
    # because Managers don't use the freaking @property tag. WHY?
    if callable(row):
        row = row()
    return row
