from django.contrib.auth.decorators import login_required
from django.conf.urls import url

from ..views import wizard
from .. import forms

event_wizard = wizard.EventWizard.as_view(
    forms.named_event_forms,
    url_name='wizard:step',
    done_step_name='finished',
    condition_dict={
        'lighting': wizard.show_lighting_form_condition,
        'sound': wizard.show_sound_form_condition,
        'projection': wizard.show_projection_form_condition,
        'other': wizard.show_other_services_form_condition,
    }
)

urlpatterns = [
    url(r'^(?P<step>.+)/$', login_required(event_wizard), name='step'),
    url(r'^$', login_required(event_wizard), name='start'),
]
