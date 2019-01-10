from functools import wraps, partial
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.forms.models import inlineformset_factory
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls.base import reverse
import reversion
from reversion.views import create_revision

from emails.generators import EventEmailGenerator
from events.forms import InternalEventForm, ServiceInstanceForm
from events.models import BaseEvent, Event, Event2019, ServiceInstance
from helpers.revision import set_revision_comment


def curry_class(cls, *args, **kwargs):
    return wraps(cls)(partial(cls, *args, **kwargs))

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
        if isinstance(instance, Event2019):
            mk_serviceinstance_formset = inlineformset_factory(BaseEvent, ServiceInstance, extra=3, exclude=[])
            mk_serviceinstance_formset.form = curry_class(ServiceInstanceForm, event=instance)
            is_event2019 = True
        else:
            is_event2019 = False
    else:
        instance = None
        context['new'] = True
        is_event2019 = False
        perms = ['events.add_raw_event']
        if not request.user.has_perms(perms):
            raise PermissionDenied
    context['is_event2019'] = is_event2019

    if request.method == 'POST':
        if instance:
            # calculate whether an email should be sent based on the event information *before* saving the form.
            should_send_email = not instance.test_event
            if should_send_email:
                bcc=[settings.EMAIL_TARGET_VP]
                if instance.projection:
                    bcc.append(settings.EMAIL_TARGET_HP)

        form = InternalEventForm(data=request.POST, request_user=request.user, instance=instance)
        if is_event2019:
            services_formset = mk_serviceinstance_formset(request.POST, request.FILES, instance=instance)

        if form.is_valid() and (not is_event2019 or services_formset.is_valid()):
            if instance:
                set_revision_comment('Edited', form)
                res = form.save()
                if is_event2019:
                    services_formset.save()
                if should_send_email:
                    # BCC the crew chiefs
                    for ccinstance in res.ccinstances.all():
                        if ccinstance.crew_chief.email:
                            bcc.append(ccinstance.crew_chief.email)
                    if res.reviewed:
                        subject = "Reviewed Event Edited"
                        email_body = "The following event was edited by %s after the event was reviewed for billing." % request.user.get_full_name()
                        bcc.append(settings.EMAIL_TARGET_T)
                    elif res.approved:
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
                    if res.projection and not settings.EMAIL_TARGET_HP in bcc:
                        bcc.append(settings.EMAIL_TARGET_HP)
                    to_emails=[]
                    if request.user.email:
                        to_emails.append(request.user.email)
                    email = EventEmailGenerator(event=res, subject=subject, to_emails=to_emails, body=email_body, bcc=bcc)
                    email.send()
            else:
                set_revision_comment('Created event', form)
                res = form.save(commit=False)
                res.submitted_by = request.user
                res.submitted_ip = request.META.get('REMOTE_ADDR')
                res.save()
                form.save_m2m()
                if is_event2019:
                    services_formset.save()
            return HttpResponseRedirect(reverse('events:detail', args=(res.id,)))
        else:
            context['e'] = form.errors
            context['form'] = form
            if is_event2019:
                context['services_formset'] = services_formset
    else:
        context['form'] = InternalEventForm(request_user=request.user, instance=instance)
        if is_event2019:
            context['services_formset'] = mk_serviceinstance_formset(instance=instance)
        if instance:
            context['msg'] = "Edit Event"
        else:
            context['msg'] = "New Event"

    return render(request, 'form_crispy_event.html', context)
