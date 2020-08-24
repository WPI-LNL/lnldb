from ajax_select.fields import AutoCompleteSelectField
from crispy_forms.bootstrap import FormActions
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Field, Layout, Submit, Div, HTML
from django import forms
from django.utils import timezone
from pagedown.widgets import PagedownWidget

from .models import ServiceAnnounce, SMSMessage
from events.models import BaseEvent, ServiceInstance


class SrvAnnounceSendForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super(SrvAnnounceSendForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_class = 'form-horizontal container'
        self.helper.layout = Layout(
            Div(
                Div(
                    'subject',
                    css_class="col-md-12"
                ),
                css_class="col-md-6"
            ),
            Div(
                Div(
                    'email_to',
                    css_class="col-md-12"
                ),
                css_class="col-md-6"
            ),
            Div(
                'message',
                FormActions(
                    Submit('save', 'Send'),
                ),
                css_class="container"
            ),
        )

    def save(self, commit=True):
        self.instance = super(SrvAnnounceSendForm, self).save(commit=False)
        if commit:
            self.instance.save()
            self.save_m2m()
        return self.instance

    class Meta:
        model = ServiceAnnounce
        fields = ('subject', 'message', 'email_to')
        widgets = {
            'message': PagedownWidget(),
        }


class SMSForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super(SMSForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_class = 'form-horizontal col-md-6'
        self.helper.layout = Layout(
            Field('message'),
            FormActions(
                Submit('save', 'Send')
            )
        )
        super(SMSForm, self).__init__(*args, **kwargs)

    class Meta:
        model = SMSMessage
        fields = ('message',)


class TargetedSMSForm(SMSForm):
    def __init__(self, *args, **kwargs):
        super(TargetedSMSForm, self).__init__(*args, **kwargs)
        self.helper.layout = Layout(
            Field('user'),
            Field('message'),
            FormActions(
                Submit('save', 'Send')
            )
        )

    class Meta:
        model = SMSMessage
        fields = ('message', 'user')

    user = AutoCompleteSelectField('Users', required=True)


class PokeCCForm(forms.Form):
    events = forms.MultipleChoiceField()
    message = forms.CharField(widget=forms.Textarea)
    email_to = forms.ChoiceField(choices=(('lnl-active@wpi.edu', 'Active Members'),))

    def __init__(self, *args, **kwargs):
        preview = None
        if 'preview' in kwargs:
            preview = kwargs.pop('preview')
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal container"
        if preview is not None:
            result = Div(HTML('<h4>Preview</h4>'), Div(HTML(preview.replace('\n', '<br>')), css_class="well"),
                         css_class="col-md-6")
        else:
            result = None
        self.helper.layout = Layout(
            Div(
                'events',
                'message',
                'email_to',
                FormActions(
                    Submit('save', 'Preview'),
                    Submit('save', 'Send')
                ),
                HTML('<br><br>'),
                css_class="col-md-6"
            ),
            result
        )
        super(PokeCCForm, self).__init__(*args, **kwargs)
        options = []
        events = BaseEvent.objects.filter(approved=True, closed=False, cancelled=False, test_event=False)\
            .filter(datetime_start__gt=timezone.now()).exclude().distinct()
        for event in events:
            for instance in ServiceInstance.objects.filter(event=event):
                options.append((instance.pk, instance))
        self.fields['events'].choices = options
