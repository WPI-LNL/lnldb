# Create your views here.

from events.forms import named_event_tmpls
from events.models import Event

from django.contrib.formtools.wizard.views import NamedUrlSessionWizardView
from django.core.urlresolvers import reverse

from django.http import HttpResponse, HttpResponseRedirect

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
    
class EventWizard(NamedUrlSessionWizardView):
    def done(self, form_list, **kwargs):
        #return HttpResponse([form.cleaned_data for form in form_list])
        event = Event.event_mg.consume_workorder_formwiz(form_list,self)
        return HttpResponseRedirect(reverse('events.views.my.myeventdetail',args=(event.id,)))
    def get_template_names(self):
        return [named_event_tmpls[self.steps.current]]
