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
        super(ExtraSelectorWidget, self).__init__(_widgets,attrs=None)
    def render(self,name,value,attrs=None):
        output = []
        for id,zname in self._choices:
            #output.append('<div class="control-group"><label class="control-label" for="inputEmail">%s</label><div class="controls"><input type="text" name="extra_%s"></input></div></div>' % (zname,id))
            output.append('<div><input class="input-mini" type="text" name="extra_%s" value=0></input><span class="help-inline">%s</span></div>' % (id,zname))
        return mark_safe(self.format_output(output))
    
    def decompress(self,value):
        if value:
            return [value.id,value.count]
        return [None,None]
    
    
###attempt2
#
class ValueSelectWidget(forms.MultiWidget):
    def __init__(self,widgets=None, *args, **kwargs):
        widgets = (
            forms.TextInput(attrs={'value':0}),
            #forms.CheckboxInput() # i forgot what this was for
            forms.HiddenInput()
            )
        super(ValueSelectWidget,self).__init__(widgets=widgets, *args, **kwargs)
    def  decompress(self,value):
        if value:
            val = value.split(',')
            raturn [val[0],val[1]]
        else:
            return [None,None]
        
class ValueSelectField(forms.MultiValueField):
    def __init__(self,fields=None,widget=None,*args,**kwargs):
        fields = (
            forms.IntegerField(),
            forms.BooleanField()
        )
        widget = ValueSelectWidget()
        super(ValueSelectField,self).__init__(fields=fields,widget=widget, *args, **kwargs)
    def compress(self,data_list):
        return data_list