# Create your views here.

from events.forms import named_event_tmpls
from events.forms import CAT_LIGHTING, CAT_SOUND
from events.forms import LIGHT_EXTRAS, SOUND_EXTRAS, PROJ_EXTRAS

from emails.generators import DefaultLNLEmailGenerator as DLEG

from events.models import Event
from events.models import Lighting,Sound,Projection,Service
from events.models import Extra

from django.conf import settings
from django.contrib.formtools.wizard.views import NamedUrlSessionWizardView
from django.core.urlresolvers import reverse

from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response, get_object_or_404
from django.template import Context,RequestContext

#CBV NuEventForm
def show_generic_form_condition(wizard, index):
    try:
        cleaned_data = wizard.get_cleaned_data_for_step('select') or {}
        types = cleaned_data.get('eventtypes')
        return index in types
    except:
        return False


def show_lighting_form_condition(wizard):
    return show_generic_form_condition(wizard, '0')


def show_sound_form_condition(wizard):
    return show_generic_form_condition(wizard, '1')

    
def show_projection_form_condition(wizard):
    return show_generic_form_condition(wizard, '2')

    
def show_other_services_form_condition(wizard):
    return show_generic_form_condition(wizard, '3')

    
class EventWizard(NamedUrlSessionWizardView):
    def done(self, form_list, **kwargs):
        #return HttpResponse([form.cleaned_data for form in form_list])
        event = Event.event_mg.consume_workorder_formwiz(form_list,self)
        #return HttpResponseRedirect(reverse('events.views.my.myeventdetail',args=(event.id,)))
        email_body = "You have successfully submitted an event titled %s" % event.event_name
        email = DLEG(subject="New Event Submitted", to_emails = [event.contact.email], body=email_body, bcc=[settings.EMAIL_TARGET_VP])
        email.send()
        
        if event.projection:
            email_bodyp = 'The event "%s" has a request for projection' % event.event_name
            emailp = DLEG(subject="New Event Submitted w/ Projection", to_emails = [settings.EMAIL_TARGET_HP], body=email_bodyp)
            emailp.send()
        context = RequestContext(self.request)
        return render_to_response('wizard_finished.html',context)
    
    #fills in form info on the first step
    def get_form_initial(self, step):
        initial = self.initial_dict.get(step, {})
        if step == "contact": #contact
            u = self.request.user
            first_last = "%s %s" % (u.first_name, u.last_name)
            initial.update({'email': u.email,"name":first_last,"phone":u.profile.phone})
        return initial
    
    #gives the form the user object to limit available orgs
    def get_form_kwargs(self, step):
        user = self.request.user
        if step == 'organization':
            return {'user':user}
        elif step == 'select':
            org_step = self.get_cleaned_data_for_step('organization')
            if org_step:
                return {'org':org_step.get('group')}
        else:
            return {}
        
    def get_context_data(self, form, **kwargs):
        context = super(EventWizard, self).get_context_data(form=form, **kwargs)
        if self.steps.current == 'lighting':
            context.update({'help_objs': Lighting.objects.all() })
            context.update({'help_name': "Lighting"})
            context.update({'extras': LIGHT_EXTRAS})
        if self.steps.current == 'sound':
            context.update({'help_objs': Sound.objects.all() })
            context.update({'help_name': "Sound"})
            context.update({'extras': SOUND_EXTRAS})
        if self.steps.current == 'projection':
            context.update({'help_objs': Projection.objects.all() })
            context.update({'help_name': "Projection"})
            context.update({'extras': PROJ_EXTRAS})
        percent = int(self.steps.step1 / float(self.steps.count) * 100)
        context.update({"percentage":percent})
        return context
    def get_template_names(self):
        return [named_event_tmpls[self.steps.current]]
