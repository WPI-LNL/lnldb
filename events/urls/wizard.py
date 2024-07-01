# from django.contrib.auth.decorators import login_required
# from django.urls import re_path
#
# from ..views import wizard
# from .. import forms
#
# app_name = 'lnldb'
#
# event_wizard = wizard.EventWizard.as_view(
#     forms.named_event_forms,
#     url_name='wizard:step',
#     done_step_name='finished',
#     condition_dict={
#         'lighting': wizard.show_lighting_form_condition,
#         'sound': wizard.show_sound_form_condition,
#         'projection': wizard.show_projection_form_condition,
#         'other': wizard.show_other_services_form_condition,
#     }
# )
#
# urlpatterns = [
#     re_path(r'^(?P<step>.+)/$', login_required(event_wizard), name='step'),
#     re_path(r'^$', login_required(event_wizard), name='start'),
# ]
