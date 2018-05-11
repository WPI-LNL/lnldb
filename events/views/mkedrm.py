from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render

from emails.generators import EventEmailGenerator
from events.forms import InternalEventForm
from events.models import Event


@login_required
def eventnew(request, id=None):
    context = {}
    # get instance if id is passed in
    if id:
        instance = get_object_or_404(Event, pk=id)
        context['new'] = False
        perms = ['events.view_event']
        if not (request.user.has_perms(perms) or
                request.user.has_perms(perms, instance)):
            raise PermissionDenied
    else:
        instance = None
        context['new'] = True
        perms = ['events.add_raw_event']
        if not request.user.has_perms(perms):
            raise PermissionDenied

    if request.method == 'POST':
        form = InternalEventForm(
            data=request.POST,
            request_user=request.user,
            instance=instance
        )

        if form.is_valid():
            if instance:
                # calculate whether an email should be sent based on the event information *before* saving the form.
                should_send_email = not instance.test_event
                if should_send_email:
                    bcc=[settings.EMAIL_TARGET_VP]
                    if instance.projection:
                        bcc.append(settings.EMAIL_TARGET_HP)
                    for ccinstance in instance.ccinstances.all():
                        if ccinstance.crew_chief.email:
                            bcc.append(ccinstance.crew_chief.email)
                    if instance.reviewed:
                        subject = "Reviewed Event Edited"
                        email_body = "The following event was edited by %s after the event was reviewed for billing." % request.user.get_full_name()
                        bcc.append(settings.EMAIL_TARGET_T)
                    elif instance.approved:
                        subject = "Approved Event Edited"
                        email_body = "The following event was edited by %s after the event was approved." % request.user.get_full_name()
                    else:
                        subject = "Event Edited"
                        email_body = "The following event was edited by %s." % request.user.get_full_name()
                    if len(form.changed_data) > 0:
                        email_body += "\nFields changed: "
                        for field_name in form.changed_data:
                            email_body += field_name + ", "
                        email_body = email_body[:-2]
                res = form.save()
                if should_send_email:
                    # add HP to the email if projection was just added to the event
                    if res.projection and not settings.EMAIL_TARGET_HP in bcc:
                        bcc.append(settings.EMAIL_TARGET_HP)
                    to_emails=[]
                    if request.user.email:
                        to_emails.append(request.user.email)
                    email = EventEmailGenerator(event=res, subject=subject, to_emails=to_emails, body=email_body, bcc=bcc)
                    email.send()
            else:
                res = form.save(commit=False)
                res.submitted_by = request.user
                res.submitted_ip = request.META.get('REMOTE_ADDR')
                res.save()
                form.save_m2m()
            return HttpResponseRedirect(reverse('events:detail', args=(res.id,)))
        else:
            context['e'] = form.errors
            context['formset'] = form
    else:
        form = InternalEventForm(request_user=request.user,
                                 instance=instance)
        if instance:
            context['msg'] = "Edit Event"
        else:
            context['msg'] = "New Event"
        context['formset'] = form

    return render(request, 'form_crispy.html', context)
