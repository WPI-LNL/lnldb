from django import forms
from widgets import ExtraSelectorWidget

class ExtraSelectorField(forms.MultiValueField):
    def __init__(self, *args,**kwargs):
        fields = [forms.CharField(required=False) for i in range(5)]
        
        self.choices = kwargs.pop("choices")
        super(ExtraSelectorField, self).__init__(fields,*args,**kwargs)
        self.widget = ExtraSelectorWidget(choices=self.choices)