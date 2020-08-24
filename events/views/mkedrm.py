from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.forms.models import inlineformset_factory
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls.base import reverse
import reversion

from emails.generators import EventEmailGenerator
from events.forms import InternalEventForm, InternalEventForm2019, ServiceInstanceForm
from events.models import BaseEvent, Event, Event2019, ServiceInstance
from helpers.revision import set_revision_comment
from helpers.util import curry_class


@login_required
def eventnew(request, id=None):
    context = {}
    # get instance if id is passed in
    if id:
        instance = get_object_or_404(BaseEvent, pk=id)
        context['new'] = False
        perms = ['events.view_event']
        if not (request.user.has_perms(perms) or
                request.user.has_perms(perms, instance)):
            raise PermissionDenied
        is_event2019 = isinstance(instance, Event2019)
    else:
        instance = None
        context['new'] = True
        is_event2019 = True
        perms = ['events.add_raw_event']
        if not request.user.has_perms(perms):
            raise PermissionDenied
    if is_event2019:
        mk_serviceinstance_formset = inlineformset_factory(BaseEvent, ServiceInstance, extra=3, exclude=[])
        mk_serviceinstance_formset.form = curry_class(ServiceInstanceForm, event=instance)
    context['is_event2019'] = is_event2019

    if request.method == 'POST':
        if instance:
            # calculate whether an email should be sent based on the event information *before* saving the form.
            should_send_email = not instance.test_event
            if should_send_email:
                bcc=[settings.EMAIL_TARGET_VP]
                if instance.has_projection:
                    bcc.append(settings.EMAIL_TARGET_HP)

        if is_event2019:
            if instance:
                form = InternalEventForm2019(data=request.POST, request_user=request.user, instance=instance)
            else:
                form = InternalEventForm2019(data=request.POST, request_user=request.user, instance=Event2019())
        else:
            form = InternalEventForm(data=request.POST, request_user=request.user, instance=instance)
        if is_event2019:
            services_formset = mk_serviceinstance_formset(request.POST, request.FILES, instance=instance)

        if form.is_valid() and (not is_event2019 or services_formset.is_valid()):
            if instance:
                set_revision_comment('Edited', form)
                obj = form.save()
                if is_event2019:
                    services_formset.save()
                if should_send_email:
                    # BCC the crew chiefs
                    for ccinstance in obj.ccinstances.all():
                        if ccinstance.crew_chief.email:
                            bcc.append(ccinstance.crew_chief.email)
                    if obj.reviewed:
                        subject = "Reviewed Event Edited"
                        email_body = "The following event was edited by %s after the event was reviewed for billing." % request.user.get_full_name()
                        bcc.append(settings.EMAIL_TARGET_T)
                    elif obj.approved:
                        subject = "Approved Event Edited"
                        email_body = "The following event was edited by %s after the event was approved." % request.user.get_full_name()
                    else:
                        subject = "Event Edited"
                        email_body = "The following event was edited by %s." % request.user.get_full_name()
                    # Add list of changed fields to the email
                    if len(form.changed_data) > 0:
                        email_body += "\nFields changed: "
                        for field_name in form.changed_data:
                            email_body += field_name + ", "
                        email_body = email_body[:-2]
                    # add HP to the email if projection was just added to the event
                    if obj.has_projection and not settings.EMAIL_TARGET_HP in bcc:
                        bcc.append(settings.EMAIL_TARGET_HP)
                    to_emails=[]
                    if request.user.email:
                        to_emails.append(request.user.email)
                    email = EventEmailGenerator(event=obj, subject=subject, to_emails=to_emails, body=email_body, bcc=bcc)
                    email.send()
            else:
                set_revision_comment('Created event', None)
                obj = form.save(commit=False)
                obj.submitted_by = request.user
                obj.submitted_ip = request.META.get('REMOTE_ADDR')
                obj.save()
                form.save_m2m()
                if is_event2019:
                    services_formset.instance = obj
                    services_formset.save()
            return HttpResponseRedirect(reverse('events:detail', args=(obj.id,)))
        else:
            context['e'] = form.errors
            context['form'] = form
            if not services_formset.is_valid() and is_event2019:
                messages.add_message(request, messages.ERROR, "Whoops! There was an error updating the services "
                                                              "for this event.")
            if is_event2019:
                context['services_formset'] = services_formset
    else:
        if is_event2019:
            context['form'] = InternalEventForm2019(request_user=request.user, instance=instance)
            context['services_formset'] = mk_serviceinstance_formset(instance=instance)
        else:
            context['form'] = InternalEventForm(request_user=request.user, instance=instance)
        if instance:
            context['msg'] = "Edit Event"
        else:
            context['msg'] = "New Event"

    return render(request, 'form_crispy_event.html', context)
