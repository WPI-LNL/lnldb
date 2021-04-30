from ajax_select.fields import AutoCompleteSelectField
from crispy_forms.bootstrap import FormActions
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Field, Layout, Submit, Div, HTML
from django import forms
from django.conf import settings
from django.utils import timezone
from pagedown.widgets import PagedownWidget

from .models import SMSMessage, aliases
from events.models import BaseEvent, ServiceInstance


class SrvAnnounceSendForm(forms.Form):
    subject = forms.CharField(max_length=128)
    message = forms.CharField(widget=PagedownWidget)
    email_to = forms.ChoiceField(choices=aliases)
    slack_channel = forms.ChoiceField(choices=(
        ('', 'No, email only'),
        (settings.SLACK_TARGET_WEBDEV, '#webdev'),
        (settings.SLACK_TARGET_EXEC, '#exec'),
        (settings.SLACK_TARGET_ACTIVE, '#active'),
        (settings.SLACK_TARGET_GENERAL, '#general'),
        (settings.SLACK_TARGET_TESTING, '#api-testing')
    ), label='Post in Slack?', required=False, help_text='Select a channel to post on Slack as well')

    def __init__(self, *args, **kwargs):
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
                css_class="container"
            ),
            Div(
                Div(
                    'slack_channel',
                    css_class="col-md-6"
                ),
                css_class="col-md-12"
            ),
            Div(
                HTML("<br>"),
                FormActions(
                    Submit('save', 'Send'),
                ),
                css_class="col-md-12"
            ),
        )
        super(SrvAnnounceSendForm, self).__init__(*args, **kwargs)


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
    email_to = forms.ChoiceField(choices=(('lnl-active@wpi.edu', 'Active Members'),
                                          ('gr-lnl-needcc@wpi.edu', 'Need CCs')))
    slack = forms.BooleanField(label='Post in Slack?', required=False)

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
                'slack',
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
