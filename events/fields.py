from django import forms
from widgets import ExtraSelectorWidget
from itertools import groupby

class ExtraSelectorField(forms.MultiValueField):
    def __init__(self, *args,**kwargs):
        fields = [forms.CharField(required=False) for i in range(5)]
        
        self.choices = kwargs.pop("choices")
        super(ExtraSelectorField, self).__init__(fields,*args,**kwargs)
        self.widget = ExtraSelectorWidget(choices=self.choices)
        

#shamelessly grabbed from http://djangosnippets.org/snippets/2622/
#modified because:
#a, forms.MCI doesnt exist, while forms.models.MCI does
#b, something in the group_label became a string instead of a function

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
    choices = property(_get_choices, forms.ModelChoiceField._set_choices)

class GroupedModelChoiceIterator(forms.models.ModelChoiceIterator):
    def __iter__(self):
        if self.field.empty_label is not None:
            yield (u"", self.field.empty_label)
        if self.field.cache_choices and False: #disable unintelligent caching
            if self.field.choice_cache is None:
                self.field.choice_cache = [
                    (self.field.group_label(group), [self.choice(ch) for ch in choices])
                        for group,choices in groupby(self.queryset.all(),
                            key=lambda row: getattr(row, self.field.group_by_field))
                ]
            for choice in self.field.choice_cache:
                yield choice
        else:
            for group, choices in groupby(self.queryset.all(),
                    key=lambda row: getattr(row, self.field.group_by_field)):
                yield (self.field.group_label(group), [self.choice(ch) for ch in choices])
                #yield (self.field.group_label, [self.choice(ch) for ch in choices])