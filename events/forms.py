from django import forms
from django.forms import Form, ModelForm, TextInput
from django.forms.extras.widgets import SelectDateWidget
from django.db.models import Q

from django.contrib.auth.models import User
from helpers.form_fields import django_msgs
from django.core.urlresolvers import reverse

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout,Fieldset,Button,ButtonHolder,Submit,Div,MultiField,Field,HTML
from crispy_forms.bootstrap import AppendedText,InlineCheckboxes,InlineRadios,Tab,TabHolder,FormActions

from events.models import Event,Organization,Category,Extra,Location,Lighting,Sound,Projection,Service
from events.widgets import ExtraSelectorWidget,ValueSelectField
from events.fields import ExtraSelectorField

from bootstrap_toolkit.widgets import BootstrapDateInput, BootstrapTextInput, BootstrapUneditableInput

from django.core.exceptions import ValidationError
import datetime
import pytz

from ajax_select import make_ajax_field
from ajax_select.fields import AutoCompleteSelectMultipleField,AutoCompleteSelectField

CAT_LIGHTING = Category.objects.get(name="Lighting")
CAT_SOUND = Category.objects.get(name="Sound")
CAT_PROJ = Category.objects.get(name="Projection")

LIGHT_EXTRAS = Extra.objects.filter(category=CAT_LIGHTING)
LIGHT_EXTRAS_ID_NAME = LIGHT_EXTRAS.values_list('id','name')
#LIGHT_EXTRAS_NAMES = [[v[1],HTML("br")] for v in LIGHT_EXTRAS_ID_NAME]
LIGHT_EXTRAS_NAMES = ["e_%s" % v[0] for v in LIGHT_EXTRAS_ID_NAME]

SOUND_EXTRAS = Extra.objects.filter(category=CAT_SOUND)
SOUND_EXTRAS_ID_NAME = SOUND_EXTRAS.values_list('id','name')
#SOUND_EXTRAS_NAMES = [[v[1],HTML("br")] for v in SOUND_EXTRAS_ID_NAME]
SOUND_EXTRAS_NAMES = ["e_%s" % v[0] for v in SOUND_EXTRAS_ID_NAME]

JOBTYPES = (
    (0,'Lighting'),
    (1,'Sound'),
    (2,'Projection'),
    (3,'Other Services'),
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
PROJ_CHOICES = (
    (16,'16mm'),
    (35,'35mm'),
    ('d','Digital'),    
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
        
        
class CrewChiefAssign(forms.ModelForm):
    crewchief = make_ajax_field(Event,'crew_chief','Users',plugin_options = {'minLength':3})
    class Meta:
        model = Event
        fields = ("crewchief",)        
        
    #crew_chief = AutoCompleteSelectMultipleField('crew_chief',plugin_options = {'minLength':3})
        
        
class CrewAssign(forms.ModelForm):
    crew = make_ajax_field(Event,'crew','Users',plugin_options = {'minLength':3})
    #crewchief = make_ajax_field(Event,'crew_chief','Users',plugin_options = {'minLength':3})
    class Meta:
        model = Event
        fields = ("crew",)

class CrewChiefAssign(forms.ModelForm):
    crew_chief = make_ajax_field(Event,'crew_chief','Users',plugin_options = {'minLength':3})
    class Meta:
        model = Event
        fields = ("crew_chief",)
        
class IOrgForm(forms.ModelForm):
    def __init__(self,*args,**kwargs):
        self.helper = FormHelper()
        self.helper.layout = Layout(
            TabHolder(
                Tab(
                    'Contact',
                    Field('name'),
                    'email',
                    'exec_email',
                    'address',
                    'phone',
                ),
                Tab(
                    'Options',
                    'email_exec',
                    'email_normal',
                    'associated_orgs',
                ),
                Tab(
                    'Money',
                    'fund',
                    'organization',
                    'account',
                ),
                Tab(
                    'People',
                    'user_in_charge',
                    'associated_users',
                )
            ),
            FormActions(
                Submit('save', 'Save changes'),
            )
        )
        super(IOrgForm,self).__init__(*args,**kwargs)
    class Meta:
        model = Organization
    #associated_orgs = make_ajax_field(Organization,'associated_orgs','Orgs',plugin_options = {'minLength':2})
    #associated_users = make_ajax_field(Organization,'associated_users','Users',plugin_options = {'minLength':3})
    #user_in_charge = AutoCompleteSelectField('Users')
    associated_orgs = AutoCompleteSelectMultipleField('Orgs',required=False)
    associated_users = AutoCompleteSelectMultipleField('Users',required=False)
class EventApprovalForm(forms.ModelForm):
    def __init__(self,*args,**kwargs):
        self.helper = FormHelper()
        self.helper.layout = Layout(
            TabHolder(
                Tab(
                    "Standard Fields",
                    Field('description',label="Description (optional)",css_class="span6"),
                    HTML('<p class="muted">This will describe the event to your CCs</p>'),
                    Field('datetime_start',label="Event Start",css_class="dtp"),
                    Field('datetime_end',label="Event End",css_class="dtp"),
                    #Field('datetime_setup_start',label="Setup Start",css_class="dtp"),
                    Field('datetime_setup_complete',label="Setup Finish",css_class="dtp"),
                        ),
                Tab(
                    "Services",
                    Field('lighting'),
                    Field('sound'),
                    Field('projection'),
                    Field('otherservices'),
                    ),
            ),
            FormActions(
                Submit('save', 'Approve Event'),
            ),
        )
        super(EventApprovalForm,self).__init__(*args,**kwargs)
        
    class Meta:
        model = Event
        fields = ['description','datetime_start','datetime_end','datetime_setup_complete','lighting','sound','projection','otherservices']
        
    datetime_start =  forms.SplitDateTimeField(initial=datetime.datetime.now())
    datetime_end =  forms.SplitDateTimeField(initial=datetime.datetime.now())
    #datetime_setup_start =  forms.SplitDateTimeField(initial=datetime.datetime.now())
    datetime_setup_complete = forms.SplitDateTimeField(initial=datetime.datetime.now())
    
    
class EventMeetingForm(forms.ModelForm):
    def __init__(self,*args,**kwargs):
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        self.helper.layout = Layout(
            Field('datetime_setup_start',label="Setup Start",css_class="dtp"),
            Field('datetime_setup_complete',label="Setup Finish",css_class="dtp"),
            Field('crew_chief',label="Crew Chief"),
            Field('crew',label="Crew"),
            FormActions(
                Submit('save', 'Update Event and Return'),
            )
        )
        super(EventMeetingForm,self).__init__(*args,**kwargs)
        
    class Meta:
        model = Event
        fields = ['datetime_setup_start','datetime_setup_complete','crew_chief','crew']
    datetime_setup_start =  forms.SplitDateTimeField(initial=datetime.datetime.now())
    datetime_setup_complete = forms.SplitDateTimeField(initial=datetime.datetime.now())
    crew_chief = AutoCompleteSelectMultipleField('Users',required=False)
    crew = AutoCompleteSelectMultipleField('Users',required=False)
    
    
class InternalEventForm(forms.ModelForm):
    def __init__(self,*args,**kwargs):
        self.helper = FormHelper()
        self.helper.layout = Layout(
            TabHolder(
                Tab(
                    'Name And Location',
                    'event_name',
                    'location',
                    'description',
                ),
                Tab(
                    'Contact',
                    'person_name',
                    'org',
                    ),
                Tab(
                    'Scheduling',
                    Field('datetime_setup_start',css_class='dtp'),
                    Field('datetime_setup_complete',css_class='dtp'),
                    Field('datetime_start',css_class='dtp'),
                    Field('datetime_end',css_class='dtp'),
                ),
                Tab(
                    'Lighting',
                    'lighting',
                    'lighting_reqs'
                ),
                Tab(
                    'Sound',
                    'sound',
                    'sound_reqs'
                ),
                Tab(
                    'Projection',
                    'projection',
                    'proj_reqs'
                    )
            ),
            FormActions(
                Submit('save', 'Save changes'),
            )
        )
        super(InternalEventForm,self).__init__(*args,**kwargs)
    class Meta:
        model = Event

    location = forms.ModelChoiceField(
            queryset = Location.objects.all()
        )
    datetime_setup_start = forms.SplitDateTimeField(initial=datetime.datetime.now()),
    person_name = AutoCompleteSelectField('Users',required=False,plugin_options={'position':"{ my : \"right top\", at: \"right bottom\", of: \"#id_person_name_text\"}"})
    org = AutoCompleteSelectMultipleField('Orgs',required=False)
    
    datetime_setup_start =  forms.SplitDateTimeField(initial=datetime.datetime.now())
    datetime_setup_complete = forms.SplitDateTimeField(initial=datetime.datetime.now())
    datetime_start = forms.SplitDateTimeField(initial=datetime.datetime.now())
    datetime_end = forms.SplitDateTimeField(initial=datetime.datetime.now())
        
        
        
class ExternalOrgUpdateForm(forms.ModelForm):
    def __init__(self,*args,**kwargs):
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        self.helper.form_method = 'post'
        self.helper.form_action = ''
        self.helper.layout = Layout(
                django_msgs,
                
                'address',
                'phone',
                'associated_users',
                FormActions(
                    Submit('save', 'Save changes'),
                )
        )
        super(ExternalOrgUpdateForm,self).__init__(*args,**kwargs)
        
    associated_users = AutoCompleteSelectMultipleField('Users',required=True,plugin_options={'position':"{ my : \"right top\", at: \"right bottom\", of: \"#id_person_name_text\"}"})
    class Meta:
        model = Organization
        fields = ('address','phone','associated_users')
        
        
        
        
        
        
        
#FormWizard Forms
class ContactForm(forms.Form):
    def __init__(self,*args,**kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.form_action = ''
        self.helper.layout = Layout(
                django_msgs,
                
                'name',
                'email',
                'phone',
                HTML('<span class="muted">To avoid entering this information again, update your <a target="_blank" href="%s">contact information</a></span>' % reverse('my-lnl')),
        )
        super(ContactForm,self).__init__(*args,**kwargs)
    name = forms.CharField()
    email = forms.EmailField()
    phone = forms.CharField()


class OrgForm(forms.Form):
    def __init__(self,*args,**kwargs):
        user = kwargs.pop('user')
        
        super(OrgForm,self).__init__(*args,**kwargs)
        self.fields['group'].queryset = Organization.objects.filter(Q(user_in_charge=user)|Q(associated_users__in=[user.id])).distinct()
        
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.form_action = ''
        self.helper.layout = Layout(
                'group',
                HTML('<span class="muted">If the organization you are looking for does not show up in the list, please contact the person in charge and tell them to use <a target="_blank" href="%s">this page</a> to grant you access</span>' % reverse('my-orgs-incharge-list')),
        )
        super(OrgForm,self).__init__(*args,**kwargs)
    group = forms.ModelChoiceField(queryset = Organization.objects.all(),label="Organization")
    #group_address = forms.CharField(
            #widget=forms.Textarea,
            #label = "Group Address",
        #)


class SelectForm(forms.Form):
    def __init__(self,*args,**kwargs):
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Fieldset(
                'Name',
                'eventname',
                'location'
            ),
            Fieldset(
                'Services',
                InlineCheckboxes('eventtypes')
                )
        )
        super(SelectForm,self).__init__(*args,**kwargs)
        
    eventname = forms.CharField(
            label = 'Event Name',
            required = True
        )
    
    location = forms.ModelChoiceField(
            queryset = Location.objects.filter(show_in_wo_form=True     )
        )
    
    
    eventtypes = forms.MultipleChoiceField(
            error_messages={'required': 'Please Select at least one service \n\r'},
            widget=forms.CheckboxSelectMultiple(attrs={'class':'checkbox'}),
            choices=JOBTYPES,
            label = "",
            required = True
            
        )

    
class LightingForm(forms.Form):
    def __init__(self,*args,**kwargs):
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Fieldset(
                'Basics', ### title
                InlineRadios('lighting',title="test"),
                Field('requirements', css_class="span8"),
                ),
            Fieldset(
                'Extras', ### title
                *LIGHT_EXTRAS_NAMES
                ),
        )
        super(LightingForm,self).__init__(*args,**kwargs)
        for extra in LIGHT_EXTRAS:
            self.fields["e_%s" % extra.id] = ValueSelectField(label=extra.name,initial=0,required=False)
            
    lighting = forms.ModelChoiceField(
            empty_label=None,
            queryset = Lighting.objects.all(),
            widget = forms.RadioSelect(attrs={'class':'radio itt'}),
        )   

    requirements = forms.CharField(
            widget=forms.Textarea,
            #widget=BootstrapTextInput(prepend='P',),
            label = "Lighting Requirements",
            required=False
        )

    #extras = ExtraSelectorField(choices=LIGHT_EXTRAS.values_list('id','name'))
    #for extra in LIGHT_EXTRAS:
        #"e__{{0}}" % extra.id = ValueSelectField(extra)
    
class SoundForm(forms.Form):
    def __init__(self,*args,**kwargs):
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Fieldset(
                'Basics', ### title
                'sound',
                Field('requirements', css_class="span8"),
                ),
            Fieldset(
                'Extras', ### title
                *SOUND_EXTRAS_NAMES
                ),
        )
        super(SoundForm,self).__init__(*args,**kwargs)
        for extra in SOUND_EXTRAS:
            self.fields["e_%s" % extra.id] = ValueSelectField(label=extra.name,initial=0,required=False)
    sound = forms.ModelChoiceField(
            empty_label=None,
            queryset = Sound.objects.all(),
            widget = forms.RadioSelect(attrs={'class':'radio'}),
        )   
    requirements = forms.CharField(
            widget=forms.Textarea,
            label = "Sound Requirements",
            required=False
        )
    
class ProjectionForm(forms.Form):
    projection = forms.ModelChoiceField(
            queryset = Projection.objects.all()
        )   
    requirements = forms.CharField(
            widget=forms.Textarea,
            label = "Projection Requirements",
        )
    
class ServiceForm(forms.Form):
    services = forms.ModelMultipleChoiceField(
            queryset = Service.objects.filter(category__name__in=["Misc","Power"]),
            widget = forms.CheckboxSelectMultiple(attrs={'class':'checkbox'}),
        )   
    otherservice_reqs = forms.CharField(
            widget=forms.Textarea,
            label = "Additional Information",
        )
        
        
class ScheduleForm(forms.Form):
    def __init__(self,*args,**kwargs):
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Fieldset(
                'Setup', ### title
                Field('setup_start',css_class="dtp"),
                Field('setup_complete',css_class="dtp"),
                ),
            Fieldset(
                'Event', ### title
                Field('event_start',css_class="dtp"),
                Field('event_end',css_class="dtp"),
                ),
        )
        super(ScheduleForm,self).__init__(*args,**kwargs)
    #setup_start = forms.SplitDateTimeField(initial=datetime.datetime.now())
    setup_complete = forms.SplitDateTimeField(initial=datetime.datetime.now(),label="Setup Completed By")
    event_start = forms.SplitDateTimeField(initial=datetime.datetime.now(),label="Event Starts")
    event_end = forms.SplitDateTimeField(initial=datetime.datetime.now(),label="Event Ends")
    
    def clean(self):
        cleaned_data = super(ScheduleForm, self).clean()
        
        setup_complete = cleaned_data.get("setup_complete")
        event_start = cleaned_data.get("event_start")
        event_end = cleaned_data.get("event_end")
        if event_start > event_end:
            raise ValidationError('You cannot start after you finish')
        if setup_complete > event_start:
            raise ValidationError('You cannot setup after you finish')
        if setup_complete < datetime.datetime.now(pytz.utc):
            raise ValidationError('Stop trying to time travel')
    
    
#helpers for the formwizard
named_event_forms = (
    ('contact',ContactForm),
    ('organization',OrgForm),
    ('select',SelectForm),
    ('lighting',LightingForm),
    ('sound',SoundForm),
    ('other',ServiceForm),
    ('projection',ProjectionForm),
    ('schedule',ScheduleForm),
)

named_event_tmpls= {
    'organization':'eventform/org.html',
    'contact':'eventform/contact.html',
    'select':'eventform/select.html',
    'lighting':'eventform/lighting.html',
    'sound':'eventform/sound.html',
    'other':'eventform/other.html',
    'projection':'eventform/projection.html',
    'schedule':'eventform/schedule.html',
}