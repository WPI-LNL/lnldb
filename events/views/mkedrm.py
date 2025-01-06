from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.forms.models import inlineformset_factory
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls.base import reverse

from accounts.models import UserPreferences
from emails.generators import EventEmailGenerator
from slack.views import event_edited_notification
from slack.api import lookup_user, slack_post, user_add
from events.forms import InternalEventForm, InternalEventForm2019, ServiceInstanceForm
from events.models import BaseEvent, Event2019, ServiceInstance
from helpers.revision import set_revision_comment
from helpers.util import curry_class

import requests, json


@login_required
def eventnew(request, id=None):
    """
    Create or edit an event

    :param id: Defaults to None (create a new event). Otherwise, this is the primary key value of the event you intend \
    to edit
    """
    context = {}
    # get instance if id is passed in
    if id:
        instance = get_object_or_404(BaseEvent, pk=id)
        context['new'] = False
        perms = ['events.view_events']
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
            should_send_notification = not instance.test_event
            if should_send_notification:
                bcc = [settings.EMAIL_TARGET_VP_DB]
                if instance.has_projection:
                    bcc.append(settings.EMAIL_TARGET_HP)

        if is_event2019:
            if instance:
                form = InternalEventForm2019(data=request.POST, request_user=request.user, instance=instance)
            else:
                form = InternalEventForm2019(data=request.POST, request_user=request.user)
        else:
            form = InternalEventForm(data=request.POST, request_user=request.user, instance=instance)
        if is_event2019:
            services_formset = mk_serviceinstance_formset(request.POST, request.FILES, instance=instance)

        if form.is_valid() and (not is_event2019 or services_formset.is_valid()):
            if instance:
                set_revision_comment('Edited', form)

                obj:BaseEvent = form.save()

                # 25Live parsing
                if is_event2019 and obj.event_id is None:
                    if form.data.get('reference_code') != "": 
                        try:
                            url = requests.get(f"https://25live.collegenet.com/25live/data/wpi/run/list/listdata.json?compsubject=event&obj_cache_accl=0&name={form.data.get('reference_code')}")
                            text = url.text
                            jsondata = json.loads(text)
                            obj.event_id = jsondata["rows"][0]["contextId"]
                            obj.save()
                        except requests.JSONDecodeError:
                            pass
                if obj.slack_channel:
                    slack_ids = [lookup_user(cci.crew_chief) for cci in obj.ccinstances.all()]
                    response = user_add(obj.slack_channel.id, slack_ids)
                    if not response['ok']:
                        messages.add_message(request, messages.WARNING, "There was an error adding the crew chiefs "
                                                                      "to the Slack channel. (Slack error: %s)" % response['error'])
                    
                if is_event2019:
                    services_formset.save()
                if should_send_notification:
                    # BCC the crew chiefs
                    for ccinstance in obj.ccinstances.all():
                        methods = clear_to_send(ccinstance.crew_chief, request.user, form.changed_data)
                        if ccinstance.crew_chief.email and 'email' in methods:
                            bcc.append(ccinstance.crew_chief.email)
                        if 'slack' in methods:
                            blocks = event_edited_notification(obj, request.user, form.changed_data)
                            slack_user = lookup_user(ccinstance.crew_chief)
                            if slack_user:
                                slack_post(slack_user, text="%s was just edited" % obj.event_name, content=blocks)
                    if obj.reviewed:
                        subject = "Reviewed Event Edited"
                        email_body = "The following event was edited by %s after the event was reviewed for billing." \
                                     % request.user.get_full_name()
                        bcc.append(settings.EMAIL_TARGET_T)
                    elif obj.approved:
                        subject = "Approved Event Edited"
                        email_body = "The following event was edited by %s after the event was approved." % \
                                     request.user.get_full_name()
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
                    if obj.has_projection and settings.EMAIL_TARGET_HP not in bcc:
                        bcc.append(settings.EMAIL_TARGET_HP)
                    to_emails = []
                    if request.user.email and 'email' in clear_to_send(request.user, request.user, form.changed_data):
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
                    mk_serviceinstance_formset.form = curry_class(ServiceInstanceForm, event=obj)
                    services_formset = mk_serviceinstance_formset(request.POST, request.FILES, instance=instance)
                    services_formset.is_valid()
                    services_formset.save()
            return HttpResponseRedirect(reverse('events:detail', args=(obj.id,)))
        else:
            context['e'] = form.errors
            context['form'] = form
            if is_event2019 and not services_formset.is_valid():
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

    return render(request, 'form_crispy_event.html', context, status = 400 if request.method == 'POST' else 200)


def clear_to_send(to, triggered_by, fields_edited):
    """
    Helper function to determine if a user should receive an Event Edited notification

    :param to: The user the message would be sent to
    :param triggered_by: The user that edited the event
    :param fields_edited: A list of edited fields
    :returns: A list of approved communication methods
    """

    prefs, created = UserPreferences.objects.get_or_create(user=to)
    if to == triggered_by and prefs.ignore_user_action:
        return []

    subscribed = False
    for field in fields_edited:
        if field in prefs.event_edited_field_subscriptions:
            subscribed = True

    methods = []
    if subscribed and prefs.event_edited_notification_methods in ['email', 'all']:
        methods.append('email')
    if subscribed and prefs.event_edited_notification_methods in ['slack', 'all']:
        methods.append('slack')

    return methods
