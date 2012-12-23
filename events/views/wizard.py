# Create your views here.

from events.forms import named_event_tmpls

from django.contrib.formtools.wizard.views import NamedUrlSessionWizardView

#CBV NuEventForm
class EventWizard(NamedUrlSessionWizardView):
    def done(self, form_list, **kwargs):
        pass
    def get_template_names(self):
        return [named_event_tmpls[self.steps.current]]
