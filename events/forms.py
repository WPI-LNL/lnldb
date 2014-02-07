from django import forms
from django.forms import Form, ModelForm, TextInput
from django.forms.extras.widgets import SelectDateWidget
from django.forms.models import inlineformset_factory
from django.db.models import Q

from django.utils.functional import curry


from django.contrib.auth.models import User
from helpers.form_fields import django_msgs
from helpers.form_text import markdown_at_msgs
from django.core.urlresolvers import reverse

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout,Fieldset,Button,ButtonHolder,Submit,Div,MultiField,Field,HTML,Hidden,Reset
from crispy_forms.bootstrap import AppendedText,InlineCheckboxes,InlineRadios,Tab,TabHolder,FormActions,PrependedText

from events.models import Event,Organization,Category,OrganizationTransfer
from events.models import Extra,Location,Lighting,Sound,Projection,Service,EventCCInstance,EventAttachment, ExtraInstance
from events.models import Billing,CCReport,Hours

from events.widgets import ExtraSelectorWidget,ValueSelectField
from events.fields import ExtraSelectorField,GroupedModelChoiceField

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
    def __init__(self,*args,**kwargs):
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        self.helper.layout = Layout(
            Field('crew'),
            FormActions(
                Submit('save', 'Save Changes'),
            )
        )
        super(CrewAssign,self).__init__(*args,**kwargs)


    class Meta:
        model = Event
        fields = ("crew",)
    crew = make_ajax_field(Event,'crew','Members',plugin_options = {'minLength':3})

class CrewChiefAssign(forms.ModelForm):
    crew_chief = make_ajax_field(Event,'crew_chief','Members',plugin_options = {'minLength':3})
    class Meta:
        model = Event
        fields = ("crew_chief",)
        
class IOrgForm(forms.ModelForm):
    def __init__(self,*args,**kwargs):
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        self.helper.layout = Layout(
            TabHolder(
                Tab(
                    'Contact',
                    Field('name'),
                    'exec_email',
                    'address',
                    Field('phone',css_class="bfh-phone",data_format="(ddd) ddd dddd"),
                ),
                Tab(
                    'Options',
                    'associated_orgs',
                    Field('personal',)
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
                Submit('save', 'Save Changes'),
            )
        )
        super(IOrgForm,self).__init__(*args,**kwargs)
    class Meta:
        model = Organization
    #associated_orgs = make_ajax_field(Organization,'associated_orgs','Orgs',plugin_options = {'minLength':2})
    #associated_users = make_ajax_field(Organization,'associated_users','Users',plugin_options = {'minLength':3})
    user_in_charge = AutoCompleteSelectField('Users')
    associated_orgs = AutoCompleteSelectMultipleField('Orgs',required=False)
    associated_users = AutoCompleteSelectMultipleField('Users',required=False)
class EventApprovalForm(forms.ModelForm):
    def __init__(self,*args,**kwargs):
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        self.helper.layout = Layout(
            TabHolder(
                Tab(
                    "Standard Fields",
                    Field('description',label="Description (optional)",css_class="span6"),
                    HTML('<p class="muted offset2">This will describe the event to your CCs</p>'),
                    markdown_at_msgs,
                    Field('datetime_setup_complete',label="Setup Finish",css_class="dtp"),
                    Field('datetime_start',label="Event Start",css_class="dtp"),
                    Field('datetime_end',label="Event End",css_class="dtp"),
                    #Field('datetime_setup_start',label="Setup Start",css_class="dtp"),
                    
                        ),
                Tab(
                    "Services",
                    Field('lighting'),
                    Field('lighting_reqs',css_class="span8"),
                    Field('sound'),
                    Field('sound_reqs',css_class="span8"),
                    Field('projection'),
                    Field('proj_reqs',css_class="span8"),
                    Field('otherservices'),
                    Field('otherservice_reqs',css_class="span8")
                    ),
            ),
            FormActions(
                Submit('save', 'Approve Event'),
            ),
        )
        super(EventApprovalForm,self).__init__(*args,**kwargs)
        
    class Meta:
        model = Event
        fields = ['description','datetime_start','datetime_end','datetime_setup_complete','lighting','lighting_reqs','sound','sound_reqs','projection','proj_reqs','otherservices','otherservice_reqs']
        
    datetime_start =  forms.SplitDateTimeField(initial=datetime.datetime.now(), label="Event Start")
    datetime_end =  forms.SplitDateTimeField(initial=datetime.datetime.now(), label="Event End")
    #datetime_setup_start =  forms.SplitDateTimeField(initial=datetime.datetime.now())
    datetime_setup_complete = forms.SplitDateTimeField(initial=datetime.datetime.now(), label="Setup Completed")

class EventDenialForm(forms.ModelForm):
    def __init__(self,*args,**kwargs):
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        self.helper.layout = Layout(
                Field('cancelled_reason',label="Reason For Cancellation (optional)",css_class="span6"),
                FormActions(
                    Submit('save', 'Deny Event'),
                ),
            )
        super(EventDenialForm,self).__init__(*args,**kwargs)
    class Meta:
        model = Event
        fields = ('cancelled_reason',)
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
    crew = AutoCompleteSelectMultipleField('3',required=False)
    
    
class InternalEventForm(forms.ModelForm):
    def __init__(self,*args,**kwargs):
        self.helper = FormHelper()
        self.helper.layout = Layout(
            django_msgs,
            TabHolder(
                Tab(
                    'Name And Location',
                    'event_name',
                    'location',
                    'description',
                ),
                Tab(
                    'Contact',
                    #'person_name',
                    'contact',
                    'org',
                    ),
                Tab(
                    'Scheduling',
                    Div(
                        Div(Field('datetime_setup_complete',css_class='dtp',title="Setup Completed By"),css_class="padleft"),
                        ),
                    Div(
                        HTML('<div class="pull-left pushdown"><br /><a class="btn btn-primary" href="#" id="samedate1" title="Cascade Dates"><i class="icon-resize-small icon-white"></i>&nbsp;<i class="icon-calendar icon-white"></i></a></div>'),
                        Div(Field('datetime_start',css_class='dtp'),css_class="padleft"),
                        ),
                    Div(
                        HTML('<div class="pull-left pushdown"><br /><a class="btn btn-primary" href="#" id="samedate2" title="Cascade Dates"><i class="icon-resize-small icon-white"></i>&nbsp;<i class="icon-calendar icon-white"></i></a></div>'),
                        Div(Field('datetime_end',css_class='dtp'),css_class="padleft"),
                        ),
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
                Submit('save', 'Save Changes'),
            )
        )
        super(InternalEventForm,self).__init__(*args,**kwargs)
    class Meta:
        model = Event
        fields = ('event_name','location','description','contact','org','datetime_setup_complete','datetime_start','datetime_end','lighting','lighting_reqs','sound','sound_reqs','projection','proj_reqs',)

    location = GroupedModelChoiceField(
            queryset = Location.objects.filter(show_in_wo_form=True),
            group_by_field = "building",
            group_label = lambda group: group.name,
        )
    contact = AutoCompleteSelectField('Users',required=False,plugin_options={'position':"{ my : \"right top\", at: \"right bottom\", of: \"#id_person_name_text\"}"})
    org = AutoCompleteSelectMultipleField('Orgs',required=False)
    
    datetime_setup_complete = forms.SplitDateTimeField(initial=datetime.datetime.now(),label="Setup Completed")
    datetime_start = forms.SplitDateTimeField(initial=datetime.datetime.now(),label="Event Start")
    datetime_end = forms.SplitDateTimeField(initial=datetime.datetime.now(),label="Event End")
     
class EventReviewForm(forms.ModelForm):
    def __init__(self,*args,**kwargs):
        event = kwargs.pop('event')
        self.helper = FormHelper()
        self.helper.form_class = "form-inline"
        self.helper.layout = Layout(
            HTML("<h5>If you'd like to override the billing org, please search for it below</h5>"),
            Field('billing_org'),
            FormActions(
                HTML('<h4> Does this look good to you?</h4>'),
                Submit('save', 'Yes!', css_class='btn btn-large btn-danger'),
                HTML('<a class="btn btn-large btn-success" href="{%% url "events.views.flow.viewevent" %s %%}"> No... </a>' % event.id ), 
            ),
        )
        super(EventReviewForm,self).__init__(*args,**kwargs)
    
    class Meta:
        model = Event
        fields = ('billing_org',)
    billing_org = AutoCompleteSelectField('Orgs',required=False, label="")
    
### External Organization forms

class ExternalOrgUpdateForm(forms.ModelForm):
    def __init__(self,*args,**kwargs):
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        self.helper.form_method = 'post'
        self.helper.form_action = ''
        self.helper.layout = Layout(
                django_msgs,
                
                'address',
                Field('phone',css_class="bfh-phone",data_format="(ddd) ddd dddd"),
                'associated_users',
                FormActions(
                    Submit('save', 'Save Changes'),
                )
        )
        super(ExternalOrgUpdateForm,self).__init__(*args,**kwargs)
        
    associated_users = AutoCompleteSelectMultipleField('Users',required=True,plugin_options={'position':"{ my : \"right top\", at: \"right bottom\", of: \"#id_person_name_text\"}"})
    class Meta:
        model = Organization
        fields = ('address','phone','associated_users')
        
class OrgXFerForm(forms.ModelForm):
    def __init__(self,org,user,*args,**kwargs):
        
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        self.helper.form_method = 'post'
        self.helper.form_action = ''
        self.helper.layout = Layout(
                django_msgs,
                'new_user_in_charge',
                Hidden('org',org.id),
                Hidden('old_user_in_charge',user.id),
                HTML('<p class="muted">This form will transfer ownership of this Organization to another user associated with the Organization. A confirmation E-Mail will be sent with a link to confirm the transfer.</p>'),
                FormActions(
                    Submit('save', 'Submit Transfer'),
                )
        )
        super(OrgXFerForm,self).__init__(*args,**kwargs)
        
        self.fields['new_user_in_charge'].queryset = org.associated_users.all().exclude(id=user.id)
        
    #new_user_in_charge = AutoCompleteSelectField('Users', required=True, plugin_options={'position':"{ my : \"right top\", at: \"right bottom\", of: \"#id_person_name_text\"},'minlength':4"})
    class Meta:
        model = OrganizationTransfer
        fields = ('new_user_in_charge',)
        
class SelfServiceOrgRequestForm(forms.Form):
    def __init__(self,*args,**kwargs):
        
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        self.helper.form_method = 'post'
        self.helper.form_action = ''
        self.helper.help_text_inline = True
        self.helper.layout = Layout(
                django_msgs,
                Field('client_name',help_text_inline=True),
                'email',
                'address',
                Field('phone',css_class="bfh-phone",data_format="(ddd) ddd dddd"),
                'fund_info',
                FormActions(
                    Submit('save', 'Submit Request'),
                )
        )
        super(SelfServiceOrgRequestForm,self).__init__(*args,**kwargs)
    
    client_name = forms.CharField(max_length=128, label= "Client Name", help_text="EX: Lens & Lights")
    email = forms.EmailField(help_text="EX: lnl@wpi.edu (This should be your exec board alias)")
    address = forms.CharField(widget=forms.Textarea, help_text="EX: Campus Center 339")
    phone = forms.CharField(max_length=15, help_text="EX: (508) - 867 - 5309" )
    fund_info = forms.CharField(help_text="EX: 12345-6789-8765")
    
#### Internal Billing forms

class BillingForm(forms.ModelForm):
    def __init__(self,event,*args,**kwargs):
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        self.helper.form_method = "post"
        self.helper.form_action = ""
        
        self.helper.layout = Layout(
                django_msgs,
                Hidden('event',event.id),
                PrependedText('date_billed','<i class="icon-calendar"></i>',css_class="datepick"),
                PrependedText('amount', '<strong>$</strong>'),
                FormActions(
                    Submit('save', 'Save Changes'),
                    Reset('reset','Reset Form'),
                )
            )
        super(BillingForm,self).__init__(*args,**kwargs)
        
        self.fields['amount'].initial = str(event.cost_total)
        
    class Meta:
        model = Billing
        
class BillingUpdateForm(forms.ModelForm):
    def __init__(self,event,*args,**kwargs):
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        self.helper.form_method = "post"
        self.helper.form_action = ""
        
        self.helper.layout = Layout(
                django_msgs,
                Hidden('event',event.id),
                PrependedText('date_paid','<i class="icon-calendar"></i>',css_class="datepick"),
                PrependedText('amount', '<strong>$</strong>'),
                FormActions(
                    Submit('save', 'Save Changes'),
                    Reset('reset','Reset Form'),
                )
            )
        super(BillingUpdateForm,self).__init__(*args,**kwargs)
        
        self.fields['amount'].initial = str(event.cost_total)
        self.fields['date_paid'].initial = datetime.date.today()
        
    class Meta:
        model = Billing
        fields = ('date_paid','amount')
        
        
### CC Facing Forms
class ReportForm(forms.ModelForm):
    def __init__(self,*args,**kwargs):
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        self.helper.form_method = "post"
        self.helper.form_action = ""
        self.helper.layout = Layout(
                django_msgs,
                Field('report',css_class="span10"),
                markdown_at_msgs,
                FormActions(
                    Submit('save', 'Save Changes'),
                    Reset('reset','Reset Form'),
                )
        )
        super(ReportForm,self).__init__(*args,**kwargs)
    class Meta:
        model = CCReport
        fields = ('report',)
        
        
class MKHoursForm(forms.ModelForm):
    def __init__(self,event,*args,**kwargs):
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        self.helper.form_method = "post"
        self.helper.form_action = ""
        self.helper.layout = Layout(
                django_msgs,
                Hidden('event',event.id),
                Field('user'),
                Field('hours'),
                FormActions(
                    Submit('save', 'Save Changes'),
                    #Reset('reset','Reset Form'),
                )
        )
        super(MKHoursForm,self).__init__(*args,**kwargs)
    class Meta:
        model = Hours
    user = AutoCompleteSelectField('Members',required=True,plugin_options={'position':"{ my : \"right top\", at: \"right bottom\", of: \"#id_person_name_text\"}"})
        
class EditHoursForm(forms.ModelForm):
    def __init__(self,*args,**kwargs):
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        self.helper.form_method = "post"
        self.helper.form_action = ""
        self.helper.layout = Layout(
                django_msgs,
                Field('hours'),
                FormActions(
                    Submit('save', 'Save Changes'),
                )
        )
        super(EditHoursForm,self).__init__(*args,**kwargs)
        
    class Meta:
        model = Hours 
        fields = ('hours',)

class CCIForm(forms.ModelForm):
    def __init__(self,event,*args,**kwargs):
        self.event = event
        self.helper = FormHelper()
        self.helper.form_class = "form-inline"
        self.helper.template = 'bootstrap/table_inline_formset.html'
        self.helper.form_tag = False
        self.helper.layout = Layout( 
            Field('crew_chief',placeholder="Crew Chief",title=""),
            Field('service'),
            Field('setup_location'),
            Field('setup_start',css_class="dtp"),
            HTML('<hr>'),
        )
        super(CCIForm,self).__init__(*args,**kwargs)
        
        #x = self.instance.event.lighting
        self.fields['service'].queryset = self.get_qs_from_event(event)
        self.fields['setup_start'].initial = self.event.datetime_setup_complete
        
    def get_qs_from_event(self,event):
        if event.lighting:
            lighting_id = event.lighting.id
        else:
            lighting_id = None
        if event.sound:
            sound_id = event.sound.id
        else:
            sound_id = None
        if event.projection:
            proj_id = event.projection.id
        else:
            proj_id = None
            
        return Service.objects.filter(Q(id__in=[lighting_id])|Q(id__in=[sound_id])|Q(id__in=[proj_id])|Q(id__in=[i.id for i in event.otherservices.all()]))
    class Meta:
        model = EventCCInstance
        
    crew_chief = AutoCompleteSelectField('Members',required=True,plugin_options={'position':"{ my : \"right top\", at: \"right bottom\", of: \"#id_person_name_text\"}"})
    setup_start = forms.SplitDateTimeField(initial=datetime.datetime.now()) 
    setup_location = GroupedModelChoiceField(
            queryset = Location.objects.filter(setup_only=True),
            group_by_field = "building", 
            group_label = lambda group: group.name,
        )
    
# Forms for Inline Formsets
class AttachmentForm(forms.ModelForm):
    def __init__(self,event,*args,**kwargs):
        self.event = event
        self.helper = FormHelper()
        self.helper.form_class = "form-inline"
        self.helper.template = 'bootstrap/table_inline_formset.html'
        self.helper.form_tag = False
        self.helper.layout = Layout( 
            Field('for_service'),
            Field('attachment'),
            Field('note'),
            HTML('<hr>'),
        )
        super(AttachmentForm,self).__init__(*args,**kwargs)
        
        #x = self.instance.event.lighting
        self.fields['for_service'].queryset = self.get_qs_from_event(event)
        
    def get_qs_from_event(self,event):
        if event.lighting:
            lighting_id = event.lighting.id
        else:
            lighting_id = None
        if event.sound:
            sound_id = event.sound.id
        else:
            sound_id = None
        if event.projection:
            proj_id = event.projection.id
        else:
            proj_id = None
            
        return Service.objects.filter(Q(id__in=[lighting_id])|Q(id__in=[sound_id])|Q(id__in=[proj_id])|Q(id__in=[i.id for i in event.otherservices.all()]))
    class Meta:
        model = EventAttachment
        fields = ('for_service','attachment','note')
        
class ExtraForm(forms.ModelForm):
    class Meta:
        model = ExtraInstance
        fields = ('extra','quant')
        
    extra = GroupedModelChoiceField(
            queryset = Extra.objects.all(),
            group_by_field = "category",
            group_label = lambda group: group.name,
        ) 
#CrewChiefFS = inlineformset_factory(Event,EventCCInstance,extra=3,form=CCIForm)

#usage
#CrewChiefFS = inlineformset_factory(Event,EventCCInstance,extra=3)
#CrewChiefFS.form = staticmethod(curry(CCIForm, event=request.event))
#__        __         _                 _           
#\ \      / /__  _ __| | _____  _ __ __| | ___ _ __ 
 #\ \ /\ / / _ \| '__| |/ / _ \| '__/ _` |/ _ \ '__|
  #\ V  V / (_) | |  |   < (_) | | | (_| |  __/ |   
   #\_/\_/ \___/|_|  |_|\_\___/|_|  \__,_|\___|_|   
                                                   
 #_____                            _                  _ 
#|  ___|__  _ __ _ __ _____      _(_)______ _ _ __ __| |
#| |_ / _ \| '__| '_ ` _ \ \ /\ / / |_  / _` | '__/ _` |
#|  _| (_) | |  | | | | | \ V  V /| |/ / (_| | | | (_| |
#|_|  \___/|_|  |_| |_| |_|\_/\_/ |_/___\__,_|_|  \__,_|
                                                       
 #_____                        
#|  ___|__  _ __ _ __ ___  ___ 
#| |_ / _ \| '__| '_ ` _ \/ __|
#|  _| (_) | |  | | | | | \__ \
#|_|  \___/|_|  |_| |_| |_|___/
                              
        
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
                Field('phone',css_class="bfh-phone",data_format="(ddd) ddd dddd"),
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
        
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.form_action = ''
        # the org nl, is a special org that everyone has access to and is not listed.
        self.fields['group'].queryset = Organization.objects.filter(Q(user_in_charge=user)|Q(associated_users__in=[user.id])|Q(shortname="nl")).distinct()
        self.helper.layout = Layout(
                'group',
                HTML('<span class="muted">If the client account you are looking for does not show up in the list, please contact the person in charge of the account using <a target="_blank" href="%s">this link</a> and request authorization to submit workorder son their behalf. If you are attempting to create an client account which does not exist please click <a target="_blank" href="%s">this link</a></span>' % (reverse('my-orgs-incharge-list'),reverse('selfserivceorg'))),
        )
        #super(OrgForm,self).__init__(*args,**kwargs)
    group = forms.ModelChoiceField(queryset = Organization.objects.all(),label="Organization")
    #group = AutoCompleteSelectField('UserLimitedOrgs', required=True, plugin_options={'position':"{ my : \"right top\", at: \"right bottom\", of: \"#id_person_name_text\"}",'minLength':2})


class SelectForm(forms.Form):
    def __init__(self,*args,**kwargs):
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Fieldset(
                'Name and Location',
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
    
    #location = forms.ModelChoiceField(
            #queryset = Location.objects.filter(show_in_wo_form=True)
        #)
    
    # soon to be a 
    location = GroupedModelChoiceField(
            queryset = Location.objects.filter(show_in_wo_form=True),
            group_by_field = "building",
            group_label = lambda group: group.name,
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
    def __init__(self,*args,**kwargs):
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Fieldset(
                'Basics', ### title
                'projection',
                Field('requirements', css_class="span8"),
                ),

        )
        super(ProjectionForm,self).__init__(*args,**kwargs)
    projection = forms.ModelChoiceField(
            empty_label=None,
            queryset = Projection.objects.all(),
            widget = forms.RadioSelect(attrs={'class':'radio'}),
        )   
    requirements = forms.CharField(
            widget=forms.Textarea,
            label = "Projection Requirements",
            required = False
        )
    
class ServiceForm(forms.Form):
    def __init__(self,*args,**kwargs):
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Fieldset(
                'Basics', ### title
                'services',
                Field('otherservice_reqs', css_class="span8"),
                ),

        )
        super(ServiceForm,self).__init__(*args,**kwargs)
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
                #Field('setup_start',css_class="dtp"),
                Div(
                    HTML('<div class="pull-left"><a class="btn btn-mini btn-primary" href="#" id="samedate"><i class="icon-arrow-down icon-white"></i>&nbsp;<i class="icon-calendar icon-white"></i></a></div>'),
                    Field('setup_complete',css_class="dtp"),
                    
                    ),
                ),
            Fieldset(
                'Event', ### title
                Field('event_start',css_class="dtp"),
                Field('event_end',css_class="dtp"),
                ),
        )
        super(ScheduleForm,self).__init__(*args,**kwargs)
    today = datetime.datetime.today()
    noon = datetime.time(12)
    noontoday = datetime.datetime.combine(today,noon)
    #setup_start = forms.SplitDateTimeField(initial=datetime.datetime.now())
    setup_complete = forms.SplitDateTimeField(initial=noontoday,label="Setup Completed By")
    event_start = forms.SplitDateTimeField(initial=noontoday,label="Event Starts")
    event_end = forms.SplitDateTimeField(initial=noontoday,label="Event Ends")
    
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
        
        return cleaned_data
    
    
#helpers for the formwizard
named_event_forms = (
    ('contact',ContactForm),
    ('organization',OrgForm),
    ('select',SelectForm),
    ('lighting',LightingForm),
    ('sound',SoundForm),
    ('projection',ProjectionForm),
    ('other',ServiceForm),
    ('schedule',ScheduleForm),
)

named_event_tmpls= {
    'organization':'eventform/org.html',
    'contact':'eventform/contact.html',
    'select':'eventform/select.html',
    'lighting':'eventform/lighting.html',
    'sound':'eventform/sound.html',
    'projection':'eventform/projection.html',
    'other':'eventform/other.html',
    'schedule':'eventform/schedule.html',
}