from django import forms
from django.forms import Form, ModelForm, TextInput
from django.forms.extras.widgets import SelectDateWidget
from events.models import Event,Organization
from bootstrap_toolkit.widgets import BootstrapDateInput, BootstrapTextInput, BootstrapUneditableInput


JOBTYPES = (
    (0,'Lighting'),
    (1,'Projection'),
    (2,'Sound'),
)

LIGHT_CHOICES = (
    (1,'L1'),
    (2,'L2'),
    (3,'L3'),
    (4,'L4'),
)

SOUND_CHOICES = (
    (1,'S1'),
    (2,'S2'),
    (3,'S3'),
    (4,'S4'),
)

class WorkorderSubmit(ModelForm):
    class Meta:
        model = Event
        exclude = ('submitted_by','submitted_ip','approved','crew','crew_chief','report','closed','payment_amount','paid')
    def __init__(self, *args, **kwargs):
        super(WorkorderSubmit,self).__init__(*args,**kwargs)
        self.fields['date_setup_start'].widget = SelectDateWidget()
        #self.fields['datetime_start'].widget = datetime()
        #self.fields['datetime_end'].widget = datetime()
        
class CrewAssign(forms.ModelForm):
    class Meta:
        model = Event
        fields = ("crew",)
    
class OrgForm(forms.ModelForm):
    class Meta:
        model = Organization


#FormWizard Forms


class ContactForm(forms.Form):
    name = forms.CharField()
    email = forms.EmailField()
    phone = forms.CharField()


class OrgForm(forms.Form):
    group = forms.CharField()
    group_address = forms.CharField(
            widget=forms.Textarea,
            label = "Group Address",
        )


class SelectForm(forms.Form):
    eventtypes = forms.MultipleChoiceField(
            error_messages={'required': 'Please Select A Service \n\r'},
            widget=forms.CheckboxSelectMultiple(attrs={'class':'checkbox'}),
            choices=JOBTYPES,
            label = "",
            required = True
            
        )

    
class LightingForm(forms.Form):
    lighting = forms.ChoiceField(
            widget=forms.RadioSelect(attrs={'class':'radio'}),
            choices = LIGHT_CHOICES,
            label = "Lighting",
        )
    additional = forms.ChoiceField(
            choices=LIGHT_CHOICES,
            label = "Additional Services",
        )
    requirements = forms.CharField(
            widget=forms.Textarea,
            #widget=BootstrapTextInput(prepend='P',),
            label = "Lighting Requirements",
        )

    
class SoundForm(forms.Form):
    requirements = forms.CharField(
            widget=forms.Textarea,
            label = "Sound Requirements",
        )
    
class ProjectionForm(forms.Form):
    requirements = forms.CharField(
            widget=forms.Textarea,
            label = "Projection Requirements",
        )
class ScheduleForm(forms.Form):
    message = forms.CharField()
    
#helpers for the formwizard
named_event_forms = (
    ('contact',ContactForm),
    ('organization',OrgForm),
    ('select',SelectForm),
    ('lighting',LightingForm),
    ('sound',SoundForm),
    ('projection',ProjectionForm),
    ('schedule',ScheduleForm),
)

named_event_tmpls= {
    'organization':'eventform/org.html',
    'contact':'eventform/contact.html',
    'select':'eventform/select.html',
    'lighting':'eventform/lighting.html',
    'sound':'eventform/sound.html',
    'projection':'eventform/projection.html',
    'schedule':'eventform/schedule.html',
}