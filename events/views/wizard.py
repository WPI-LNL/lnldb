# Create your views here.

from events.forms import named_event_tmpls
from events.models import Event

from django.contrib.formtools.wizard.views import NamedUrlSessionWizardView
from django.core.urlresolvers import reverse

from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response, get_object_or_404
from django.template import Context,RequestContext

#CBV NuEventForm
def show_lighting_form_condition(wizard):
    cleaned_data = wizard.get_cleaned_data_for_step('select') or {}
    types = cleaned_data.get('eventtypes')
    try:
        if '0' in types:
            return True
        else:
            return False    
    except:
        return False

def show_sound_form_condition(wizard):
    cleaned_data = wizard.get_cleaned_data_for_step('select') or {}
    types = cleaned_data.get('eventtypes')
    try:
        if '1' in types:
            return True
        else:
            return False    
    except:
        return False
    
def show_projection_form_condition(wizard):
    cleaned_data = wizard.get_cleaned_data_for_step('select') or {}
    types = cleaned_data.get('eventtypes')
    try:
        if '2' in types:
            return True
        else:
            return False    
    except:
        return False
    
def show_other_services_form_condition(wizard):
    cleaned_data = wizard.get_cleaned_data_for_step('select') or {}
    types = cleaned_data.get('eventtypes')
    try:
        if '3' in types:
            return True
        else:
            return False    
    except:
        return False
    
class EventWizard(NamedUrlSessionWizardView):
    def done(self, form_list, **kwargs):
        #return HttpResponse([form.cleaned_data for form in form_list])
        event = Event.event_mg.consume_workorder_formwiz(form_list,self)
        #return HttpResponseRedirect(reverse('events.views.my.myeventdetail',args=(event.id,)))
        
        context = RequestContext(self.request)
        return render_to_response('wizard_finished.html',context)
    
    def get_form_initial(self, step):
        initial = self.initial_dict.get(step, {})
        if step == "contact": #contact
            u = self.request.user
            first_last = "%s %s" % (u.first_name, u.last_name)
            initial.update({'email': u.email,"name":first_last,"phone":u.profile.phone})
        return initial
    def get_form_kwargs(self, step):
        user = self.request.user
        if step == 'organization':
            return {'user':user}
        else:
            return {}
    
    def get_template_names(self):
        return [named_event_tmpls[self.steps.current]]
