from django.forms import widgets
from django import forms
from django.utils.safestring import mark_safe


class ExtraSelectorWidget(widgets.MultiWidget):
    _choices = ()

    def __init__(self, choices, attrs=None):
        self._choices = choices
        _widgets = (
            widgets.CheckboxInput(attrs=attrs),
            widgets.TextInput()
        )
        super(ExtraSelectorWidget, self).__init__(_widgets, attrs=None)

    def render(self, name, value, attrs=None):
        output = []
        for id, zname in self._choices:
            # output.append('<div class="form-group"><label class="control-label" for="inputEmail">%s</label>
            # <div class="controls"><input type="text" name="extra_%s"></input></div></div>' % (zname,id))
            output.append(
                '<div><input class="input-mini" type="text" name="extra_%s" value=0></input>'
                '<span class="help-inline">%s</span></div><i class="glyphicon glyphicon-plus"></i>' % (id, zname))
        return mark_safe(self.format_output(output))

    def decompress(self, value):
        if value:
            return [value.id, value.count]
        return [None, None]


# attempt2
class ValueSelectWidget(forms.MultiWidget):
    def __init__(self, hidetext=False, disappear=False, *args, **kwargs):
        if hidetext:
            textattrs = {'value': 0, 'class': 'hide', "disappear": disappear}
            checkattrs = {"disappear": disappear}
        else:
            textattrs = {'value': 0, "disappear": disappear}
            checkattrs = {'class': 'hide', "disappear": disappear}

        widgets_override = (
            forms.TextInput(attrs=textattrs),
            forms.CheckboxInput(attrs=checkattrs)  # i forgot what this was for

        )
        super(ValueSelectWidget, self).__init__(widgets_override, *args, **kwargs)

    def decompress(self, value):
        if value:
            val = value.split(',')
            return [val[0], val[1]]
        else:
            return [None, None]


class ValueSelectField(forms.MultiValueField):
    def __init__(self, fields=None, widget=None, hidetext=False, disappear=False, *args, **kwargs):
        # if not fields:
        fields = (
            forms.IntegerField(min_value=0, ),
            forms.BooleanField()
        )
        widget = ValueSelectWidget(hidetext=hidetext, disappear=disappear)
        # noinspection PyArgumentList
        super(ValueSelectField, self).__init__(fields=fields, widget=widget, *args, **kwargs)

    def compress(self, data_list):
        return data_list
