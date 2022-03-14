import math
from datetime import timedelta
from decimal import Decimal
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Avg, Count
from django.forms.models import inlineformset_factory
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.urls.base import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.views.generic import CreateView, DeleteView, UpdateView
from django.views.decorators.http import require_GET, require_POST
from reversion.models import Version

from accounts.models import UserPreferences
from emails.generators import (ReportReminderEmailGenerator, EventEmailGenerator, BillingEmailGenerator,
                               DefaultLNLEmailGenerator as DLEG, send_survey_if_necessary)
from slack.views import cc_report_reminder
from slack.api import lookup_user, slack_post
from events.forms import (AttachmentForm, BillingForm, BillingUpdateForm, MultiBillingForm,
                          MultiBillingUpdateForm, CCIForm, CrewAssign, EventApprovalForm,
                          EventDenialForm, EventReviewForm, ExtraForm, InternalReportForm, MKHoursForm,
                          BillingEmailForm, MultiBillingEmailForm, ServiceInstanceForm, WorkdayForm, CrewCheckinForm,
                          CrewCheckoutForm, CheckoutHoursForm, BulkCheckinForm)
from events.models import (BaseEvent, Billing, MultiBilling, BillingEmail, MultiBillingEmail, Category, CCReport, Event,
                           Event2019, EventArbitrary, EventAttachment, EventCCInstance, ExtraInstance, Hours,
                           ReportReminder, ServiceInstance, PostEventSurvey, CCR_DELTA, CrewAttendanceRecord)
from helpers.mixins import (ConditionalFormMixin, HasPermMixin, HasPermOrTestMixin,
                            LoginRequiredMixin, SetFormMsgMixin)
from helpers.challenges import is_officer
from helpers.revision import set_revision_comment
from helpers.util import curry_class
from pdfs.views import (generate_pdfs_standalone, generate_event_bill_pdf_standalone,
                        generate_multibill_pdf_standalone)
from ..cal import generate_ics


@login_required
@permission_required('events.approve_event', raise_exception=True)
def approval(request, id):
    """ Approve an event (agree to provide services for the event) """
    context = {'msg': "Approve Event"}
    event = get_object_or_404(BaseEvent, pk=id)
    if not request.user.has_perm('events.approve_event', event):
        raise PermissionDenied
    if event.closed:
        messages.add_message(request, messages.ERROR, 'Event is closed.')
        return HttpResponseRedirect(reverse('events:detail', args=(event.id,)))
    if event.approved:
        messages.add_message(request, messages.INFO, 'Event has already been approved!')
        return HttpResponseRedirect(reverse('events:detail', args=(event.id,)))
    is_event2019 = isinstance(event, Event2019)
    context['is_event2019'] = is_event2019
    if is_event2019:
        mk_serviceinstance_formset = inlineformset_factory(BaseEvent, ServiceInstance, extra=3, exclude=[])
        mk_serviceinstance_formset.form = curry_class(ServiceInstanceForm, event=event)

    if request.method == 'POST':
        form = EventApprovalForm(request.POST, instance=event)
        if is_event2019:
            services_formset = mk_serviceinstance_formset(request.POST, request.FILES, instance=event)
        if form.is_valid() and (not is_event2019 or services_formset.is_valid()):
            e = form.save(commit=False)
            e.approved = True
            e.approved_on = timezone.now()
            e.approved_by = request.user
            e.save()
            form.save_m2m()
            if is_event2019:
                services_formset.save()
            # Automatically add the event contact to the client (if the event has only one client)
            if e.contact is not None and e.org.count() == 1 and e.contact not in e.org.get().associated_users.all():
                set_revision_comment("Approved {}. Event contact {} automatically added to {}.".format(
                    e.event_name, e.contact, e.org.get()), form)
                e.org.get().associated_users.add(e.contact)
            else:
                set_revision_comment("Approved", form)
            # confirm with user
            messages.add_message(request, messages.INFO, 'Approved Event')
            if e.contact and e.contact.email:
                email_body = 'Your event "%s" has been approved!' % event.event_name
                email = DLEG(subject="Event Approved", to_emails=[e.contact.email], body=email_body,
                             bcc=[settings.EMAIL_TARGET_VP])
                email.send()
            else:
                messages.add_message(request, messages.INFO,
                                     'No contact info on file for approval. Please give them the good news!')

            return HttpResponseRedirect(reverse('events:detail', args=(e.id,)))
        else:
            context['form'] = form
            if is_event2019:
                context['services_formset'] = services_formset
    else:
        # has a bill, but no paid bills, and is not otherwise closed
        unbilled_events = Event.objects.filter(org__in=event.org.all())\
                                       .exclude(billings__date_paid__isnull=False)\
                                       .filter(billings__date_billed__isnull=False)\
                                       .filter(closed=False)\
                                       .filter(cancelled=False)\
                                       .filter(test_event=False)\
                                       .distinct()
        unbilled_events = map(str, unbilled_events)
        if event.org.exists() and unbilled_events:
            messages.add_message(request, messages.WARNING, "Organization has unbilled events: %s" % ", ".join(
                unbilled_events))
        for org in event.org.filter(delinquent=True):
            messages.add_message(request, messages.WARNING, "The client '%s' has been marked as delinquent. \
                    This means that the client has one or more long-outstanding bills which they should be required to \
                    pay before you approve this event." % org)
        context['form'] = EventApprovalForm(instance=event)
        if is_event2019:
            context['services_formset'] = mk_serviceinstance_formset(instance=event)
    return render(request, 'form_crispy_approval.html', context)


@login_required
def denial(request, id):
    """ Deny an incoming event (LNL will not provide services for the event) """
    context = {'msg': "Deny Event"}
    event = get_object_or_404(BaseEvent, pk=id)
    if not request.user.has_perm('events.decline_event', event):
        raise PermissionDenied
    if event.closed:
        messages.add_message(request, messages.ERROR, 'Event is closed.')
        return HttpResponseRedirect(reverse('events:detail', args=(event.id,)))
    if event.cancelled:
        messages.add_message(request, messages.INFO, 'Event has already been cancelled!')
        return HttpResponseRedirect(reverse('events:detail', args=(event.id,)))

    if request.method == 'POST':
        form = EventDenialForm(request.POST, instance=event)
        if form.is_valid():
            set_revision_comment("Denied", form)
            e = form.save(commit=False)
            e.cancelled = True
            e.cancelled_by = request.user
            e.cancelled_on = timezone.now()
            e.closed = True
            e.closed_by = request.user
            e.closed_on = timezone.now()
            e.save()
            # confirm with user
            messages.add_message(request, messages.INFO, 'Denied Event')
            if e.contact and e.contact.email:
                email_body = 'Sorry, but your event "%s" has been denied. \n Reason: "%s"' % (
                    event.event_name, event.cancelled_reason)
                email = DLEG(subject="Event Denied", to_emails=[e.contact.email], body=email_body,
                             bcc=[settings.EMAIL_TARGET_VP])
                email.send()
            else:
                messages.add_message(request, messages.INFO,
                                     'No contact info on file for denial. Please give them the bad news.')
            return HttpResponseRedirect(reverse('events:detail', args=(e.id,)))
    form = EventDenialForm(instance=event)
    context['form'] = form
    return render(request, 'form_crispy.html', context)


@login_required
def review(request, id):
    """ Review an event for billing """
    context = {'h2': "Review Event for Billing"}
    event = get_object_or_404(BaseEvent, pk=id)
    if not request.user.has_perm('events.review_event', event):
        raise PermissionDenied
    if event.closed:
        messages.add_message(request, messages.ERROR, 'Event is closed.')
        return HttpResponseRedirect(reverse('events:detail', args=(event.id,)))
    if event.reviewed:
        messages.add_message(request, messages.INFO, 'Event has already been reviewed!')
        return HttpResponseRedirect(reverse('events:detail', args=(event.id,)))

    context['event'] = event

    if request.method == 'POST':
        form = EventReviewForm(request.POST, instance=event, event=event)
        if form.is_valid():
            set_revision_comment("Reviewed for billing", form)
            e = form.save(commit=False)
            e.reviewed = True
            e.reviewed_on = timezone.now()
            e.reviewed_by = request.user
            e.save()
            form.save_m2m()
            # Remove prefilled hours that were never finished
            Hours.objects.filter(event=e, hours__isnull=True).delete()
            # Close any "active" crew member records for this event
            if isinstance(e, Event2019):
                e.crew_attendance.filter(active=True).update(active=False)
            # confirm with user
            messages.add_message(request, messages.INFO, 'Event has been reviewed and is ready for billing!')

            return HttpResponseRedirect(reverse('events:detail', args=(e.id,)) + "#billing")
        else:
            context['formset'] = form
    else:
        form = EventReviewForm(instance=event, event=event)
        context['formset'] = form
    return render(request, 'event_review.html', context)


@login_required
def reviewremind(request, id, uid):
    """
    Remind a crew chief to complete their CC report

    :param id: The primary key value of the respective event
    :param uid: The primary key value of the user to send a reminder to
    """
    event = get_object_or_404(BaseEvent, pk=id)
    if not (request.user.has_perm('events.review_event') or
            request.user.has_perm('events.review_event', event)):
        raise PermissionDenied
    if event.closed:
        messages.add_message(request, messages.ERROR, 'Event is closed.')
        return HttpResponseRedirect(reverse('events:detail', args=(event.id,)))
    if event.reviewed or not event.approved:
        messages.add_message(request, messages.ERROR, 'You can only send reminders for an event that is approved and '
                                                      'has not yet been reviewed.')
        return HttpResponseRedirect(reverse('events:detail', args=(event.id,)))

    cci = event.ccinstances.filter(crew_chief_id=uid).first()
    if cci:
        # only do heavy lifting if we need to
        prefs, created = UserPreferences.objects.get_or_create(user=cci.crew_chief)
        send_notification = True
        if cci.crew_chief == request.user and prefs.ignore_user_action:
            send_notification = False
        if send_notification and prefs.cc_report_reminders in ['email', 'all']:
            pdf_handle = generate_pdfs_standalone([event.id])
            filename = "%s.workorder.pdf" % slugify(event.event_name)
            attachments = [{"file_handle": pdf_handle, "name": filename}]

            reminder = ReportReminder.objects.create(event=cci.event, crew_chief=cci.crew_chief)
            email = ReportReminderEmailGenerator(reminder=reminder, attachments=attachments)
            email.send()
        if send_notification and prefs.cc_report_reminders in ['slack', 'all']:
            message = "This is a reminder that you have a pending crew chief report for %s." % event.event_name
            blocks = cc_report_reminder(cci)
            slack_user = lookup_user(cci.crew_chief.email)
            if slack_user:
                slack_post(slack_user, text=message, content=blocks)
        messages.add_message(request, messages.INFO, 'Reminder Sent')
        return HttpResponseRedirect(reverse("events:review", args=(event.id,)))
    else:
        return HttpResponse("Bad Call")


@login_required
def remindall(request, id):
    """ Remind any crew chiefs who have not yet completed a CC report for a particular event to do so """
    event = get_object_or_404(BaseEvent, pk=id)
    if not (request.user.has_perm('events.review_event') or
            request.user.has_perm('events.review_event', event)):
        raise PermissionDenied
    if event.closed:
        messages.add_message(request, messages.ERROR, 'Event is closed.')
        return HttpResponseRedirect(reverse('events:detail', args=(event.id,)))
    if event.reviewed or not event.approved:
        messages.add_message(request, messages.ERROR, 'Can only send reminders for an event that is approved and not '
                                                      'reviewed.')
        return HttpResponseRedirect(reverse('events:detail', args=(event.id,)))

    if event.num_crew_needing_reports == 0:
        messages.add_message(request, messages.INFO, 'All crew chiefs have already submitted reports.')
        return HttpResponseRedirect(reverse("events:review", args=(event.id,)))

    pdf_handle = generate_pdfs_standalone([event.id])
    filename = "%s.workorder.pdf" % slugify(event.event_name)
    attachments = [{"file_handle": pdf_handle, "name": filename}]

    for cci in event.crew_needing_reports:
        prefs, created = UserPreferences.objects.get_or_create(user=cci.crew_chief)
        if cci.crew_chief == request.user and prefs.ignore_user_action:
            continue
        if prefs.cc_report_reminders in ['email', 'all']:
            reminder = ReportReminder.objects.create(event=event, crew_chief=cci.crew_chief)
            email = ReportReminderEmailGenerator(reminder=reminder, attachments=attachments)
            email.send()
        if prefs.cc_report_reminders in ['slack', 'all']:
            message = "This is a reminder that you have a pending crew chief report for %s." % event.event_name
            blocks = cc_report_reminder(cci)
            slack_user = lookup_user(cci.crew_chief.email)
            if slack_user:
                slack_post(slack_user, text=message, content=blocks)

    messages.add_message(request, messages.INFO, 'Reminders sent to all crew chiefs needing reports for %s' %
                         event.event_name)
    if 'next' in request.GET:
        return HttpResponseRedirect(request.GET['next'])
    else:
        return HttpResponseRedirect(reverse('events:detail', args=(event.id,)))


@login_required
@require_POST
def close(request, id):
    """ Close an event (not to be confused with cancel). POST only. """
    set_revision_comment("Closed", None)
    event = get_object_or_404(BaseEvent, pk=id)
    if not request.user.has_perm('events.close_event', event):
        raise PermissionDenied
    event.closed = True
    event.closed_by = request.user
    event.closed_on = timezone.now()

    event.save()

    return HttpResponseRedirect(reverse('events:detail', args=(event.id,)))


@login_required
@require_POST
def cancel(request, id):
    """ Cancel an event (LNL will no longer provide services for this event). POST only. """
    set_revision_comment("Cancelled", None)
    event = get_object_or_404(BaseEvent, pk=id)
    if not request.user.has_perm('events.cancel_event', event):
        raise PermissionDenied
    if event.closed:
        messages.add_message(request, messages.ERROR, 'Event is closed.')
        return HttpResponseRedirect(reverse('events:detail', args=(event.id,)))
    event.cancelled = True
    event.cancelled_by = request.user
    event.cancelled_on = timezone.now()
    event.save()

    if event.contact and event.contact.email:
        targets = [event.contact.email]
    else:
        targets = []

    email_body = 'The event "%s" has been cancelled by %s. If this is incorrect, please contact our vice president ' \
                 'at lnl-vp@wpi.edu.' % (event.event_name, str(request.user))
    if request.user.email:
        email_body = email_body[:-1]
        email_body += " or try them at %s." % request.user.email
    email = DLEG(subject="Event Cancelled", to_emails=targets, body=email_body, bcc=[settings.EMAIL_TARGET_VP])
    email.send()
    return HttpResponseRedirect(reverse('events:detail', args=(event.id,)))


@login_required
@require_POST
def reopen(request, id):
    """ Reopen an event that has already been closed. POST only. """
    set_revision_comment("Reopened", None)
    event = get_object_or_404(BaseEvent, pk=id)
    if not request.user.has_perm('events.reopen_event', event):
        raise PermissionDenied
    event.closed = False
    event.closed_by = None
    event.closed_on = None

    event.save()

    return HttpResponseRedirect(reverse('events:detail', args=(event.id,)))


@login_required
def rmcrew(request, id, user):
    """
    Remove a user from the list of crew members who attended an event (pre-2019 events only)

    :param id: The primary key value of the event
    :param user: The primary key value of the user
    """
    event = get_object_or_404(Event, pk=id)
    if not (request.user.has_perm('events.edit_event_hours') or
            request.user.has_perm('events.edit_event_hours', event)):
        raise PermissionDenied
    if event.closed:
        messages.add_message(request, messages.ERROR, 'Event is closed.')
        return HttpResponseRedirect(reverse('events:detail', args=(event.id,)))
    event.crew.remove(user)
    return HttpResponseRedirect(reverse("events:add-crew", args=(event.id,)))


@login_required
def assigncrew(request, id):
    """
    - Pre-2019 Events: Assign crew members to an event
    - Newer Events: Redirect to crew list
    """
    context = {'msg': "Crew"}

    event = get_object_or_404(BaseEvent, pk=id)

    # The new events model doesn't really use this anymore
    if isinstance(event, Event2019):
        return HttpResponseRedirect(reverse('events:detail', args=[event.id]) + "#crew")

    if not (request.user.has_perm('events.edit_event_hours') or
            request.user.has_perm('events.edit_event_hours', event)):
        raise PermissionDenied
    if event.closed:
        messages.add_message(request, messages.ERROR, 'Event is closed.')
        return HttpResponseRedirect(reverse('events:detail', args=(event.id,)))
    context['event'] = event

    if request.method == 'POST':
        formset = CrewAssign(request.POST, instance=event)
        if formset.is_valid():
            formset.save()
            return HttpResponseRedirect(reverse('events:detail', args=(event.id,)))
    else:
        formset = CrewAssign(instance=event)

    context['formset'] = formset

    return render(request, 'form_crew_add.html', context)


@login_required
def hours_bulk_admin(request, id):
    """ Update crew member hours in bulk """
    context = {'msg': "Bulk Hours Entry"}

    event = get_object_or_404(BaseEvent, pk=id)
    if not event.reports_editable and not request.user.has_perm('events.edit_event_hours') and \
            request.user.has_perm('events.edit_event_hours', event):
        return render(request, 'too_late.html', {'days': CCR_DELTA, 'event': event})
    if not (request.user.has_perm('events.edit_event_hours') or
            request.user.has_perm('events.edit_event_hours', event) and event.reports_editable):
        raise PermissionDenied
    if event.closed:
        messages.add_message(request, messages.ERROR, 'Event is closed.')
        return HttpResponseRedirect(reverse('events:detail', args=(event.id,)))
    context['event'] = event
    context['oldevent'] = isinstance(event, Event)

    mk_hours_formset = inlineformset_factory(BaseEvent, Hours, extra=15, exclude=[])
    mk_hours_formset.form = curry_class(MKHoursForm, event=event)

    if request.method == 'POST':
        formset = mk_hours_formset(request.POST, instance=event)
        if formset.is_valid():
            formset.save()
            return HttpResponseRedirect(reverse('events:detail', args=(event.id,)))
    else:
        formset = mk_hours_formset(instance=event)

    context['formset'] = formset
    return render(request, 'formset_hours_bulk.html', context)


@login_required
@require_GET
def hours_prefill_self(request, id):
    """
    Log the current user as a crew member for an event. This only works after setup begins and will continue to work up
    until 3 hours after the event. GET requests only.
    """
    event = get_object_or_404(BaseEvent, pk=id)
    if not event.ccinstances.exists():
        raise PermissionDenied
    if event.hours.filter(user=request.user).exists():
        messages.add_message(request, messages.ERROR, 'You already have hours for this event.')
        return HttpResponseRedirect(reverse('events:detail', args=(event.id,)))
    if timezone.now() < min(event.ccinstances.values_list('setup_start', flat=True)):
        messages.add_message(request, messages.ERROR, 'You cannot use this feature until the event setup has started.')
        return HttpResponseRedirect(reverse('events:detail', args=(event.id,)))
    if timezone.now() > event.datetime_end + timedelta(hours=3):
        messages.add_message(request, messages.ERROR, 'This feature is disabled 3 hours after the event end time.')
        return HttpResponseRedirect(reverse('events:detail', args=(event.id,)))
    Hours.objects.create(event=event, user=request.user)
    messages.add_message(request, messages.SUCCESS, 'You have been added as crew for this event.')
    return HttpResponseRedirect(reverse('events:detail', args=(event.id,)))


@login_required
@require_GET
def crew_tracker(request):
    """ Event checkin / checkout menu for crew members. GET requests only. """
    context = {'NO_FOOT': True, 'NO_NAV': True, 'NO_API': True, 'LIGHT_THEME': True}
    return render(request, 'crew_checkin.html', context)


@login_required
def checkin(request):
    """ Event checkin page for crew members """
    context = {'NO_FOOT': True, 'NO_NAV': True, 'NO_API': True, 'LIGHT_THEME': True}

    if not request.user.is_lnl:
        raise PermissionDenied

    events = Event2019.objects.filter(
        sensitive=False, closed=False, ccinstances__setup_start__lte=timezone.now(),
        datetime_end__gt=timezone.now() + timezone.timedelta(hours=-5), cancelled=False).distinct()
    for event in events:
        if event.max_crew and event.crew_attendance.filter(active=True).count() == event.max_crew:
            events = events.exclude(pk=event.pk)
    if events.count() == 0:
        context['page'] = {"title": "There are currently no events available for checkin",
                           "body": "<a href='" + reverse("events:crew-tracker") + "' class='btn btn-primary'>Back</a>"}
        return render(request, 'static_page.html', context)

    if request.user.event_records.filter(active=True).exists():
        context['page'] = {"title": "You are already checked into an event",
                           "body": "<a href='" + reverse("events:crew-tracker") + "' class='btn btn-primary'>Back</a>"}
        return render(request, 'static_page.html', context)

    if request.method == 'POST':
        form = CrewCheckinForm(request.POST, events=events, title="Checkin")
        if form.is_valid():
            event = Event2019.objects.get(pk=request.POST['event'])
            event.crew_attendance.create(user=request.user)
            if not event.hours.filter(user=request.user).exists():
                event.hours.create(user=request.user)
            name = request.user.nickname
            if not name:
                name = request.user.first_name
            messages.success(request, "Welcome, %s. You have checked in successfully!" % name, extra_tags="success")
            return HttpResponseRedirect(reverse("events:detail", args=[event.pk]))
    else:
        form = CrewCheckinForm(events=events, title="Checkin")
    context['form'] = form
    return render(request, 'form_crispy_static.html', context)


@login_required
def checkout(request):
    """ Event checkout page for crew members """
    context = {'NO_FOOT': True, 'NO_NAV': True, 'NO_API': True, 'LIGHT_THEME': True,
               'styles': ".control {\n\tpadding: .375rem .75rem;\n\tfont-size: 1rem;\n\tline-height: 1.5;\n\t"
                         "border-radius: .25rem;\n\tborder: 1px solid #cde4da;\n\tbackground-clip: padding-box;}"}

    if not request.user.is_lnl:
        raise PermissionDenied

    record = CrewAttendanceRecord.objects.filter(user=request.user, active=True).first()
    if record is None:
        context['page'] = {"title": "Whoops! It appears you haven't checked in yet.",
                           "body": "<a href='" + reverse("events:crew-tracker") + "' class='btn btn-primary'>Back</a>"}
        return render(request, 'static_page.html', context)

    categories = []
    for category in ServiceInstance.objects.filter(event=record.event).values_list('service__category', flat=True) \
            .distinct():
        categories.append(Category.objects.get(pk=int(category)))

    # Calculate hours worked
    if record.checkout:
        delta = record.checkout - record.checkin
        quarter_hrs = delta.seconds / 900
        hours = math.floor(delta.seconds / 3600)
        remainder = math.floor(quarter_hrs % 4) * 0.25
        total = hours + remainder

    if request.method == 'POST':
        if not record.checkout:
            form = CrewCheckoutForm(request.POST)
            if form.is_valid():
                checkin_datetime = timezone.make_aware(timezone.datetime.strptime(
                    "%s%s" % (request.POST['checkin_0'], request.POST['checkin_1']), "%Y-%m-%d%I:%M %p"))
                checkout_datetime = timezone.make_aware(timezone.datetime.strptime(
                    "%s%s" % (request.POST['checkout_0'], request.POST['checkout_1']), "%Y-%m-%d%I:%M %p"))
                # Ensure that no one can have a checkin time before setup starts
                if checkin_datetime < min(record.event.ccinstances.values_list('setup_start', flat=True)):
                    checkin_datetime = min(record.event.ccinstances.values_list('setup_start', flat=True))
                record.checkin = checkin_datetime
                record.checkout = checkout_datetime
                record.save()

                delta = checkout_datetime - checkin_datetime
                quarter_hrs = delta.seconds / 900
                hours = math.floor(delta.seconds / 3600)
                remainder = math.floor(quarter_hrs % 4) * 0.25
                total = hours + remainder
                form = CheckoutHoursForm(categories=categories, total_hrs=total)
        else:
            form = CheckoutHoursForm(request.POST, categories=categories, total_hrs=total)
            if form.is_valid():
                record.active = False
                record.save()

                hour_fields = []
                # Get the hours fields
                for field in request.POST:
                    if "hour" in field:
                        hour_fields.append(field)
                # If values were entered, save to hours log
                for field in hour_fields:
                    hour_input = request.POST[field]
                    if hour_input not in [None, ''] and Decimal(hour_input) != 0:
                        cat = field.replace('hours_', '')
                        category = Category.objects.get(name=cat)
                        # Check for pending hour record
                        placeholder = Hours.objects.filter(category__isnull=True, event=record.event,
                                                           user=request.user).first()
                        if placeholder:
                            placeholder.category = category
                            placeholder.hours = 0
                            placeholder.save()
                        hour_record, created = Hours.objects.get_or_create(event=record.event, user=request.user,
                                                                           category=category)
                        if created:
                            hour_record.hours = Decimal(hour_input)
                        else:
                            hour_record.hours += Decimal(hour_input)
                        hour_record.save()
                messages.success(request, "You have successfully checked out!", extra_tags="success")
                return HttpResponseRedirect(reverse("events:detail", args=[record.event.pk]))
    else:
        if not record.checkout:
            form = CrewCheckoutForm(initial={'checkin': record.checkin, 'checkout': timezone.now()})
        else:
            form = CheckoutHoursForm(categories=categories, total_hrs=total)
    context['form'] = form
    return render(request, 'form_crispy_static.html', context)


@login_required
def bulk_checkin(request):
    """ Scan or swipe a registered WPI ID to checkin or checkout of an event as a crew member """
    context = {'NO_FOOT': True, 'NO_NAV': True, 'NO_API': True, 'LIGHT_THEME': True}

    if not request.user.is_lnl:
        raise PermissionDenied

    event_id = request.GET.get('id', None)
    if event_id:
        event = get_object_or_404(Event2019, pk=event_id)

        if request.method == 'POST':
            form = BulkCheckinForm(request.POST, result=None, user_name=None, event=event.event_name)
            if form.is_valid():
                student_id = request.POST['id']
                user = get_user_model().objects.filter(student_id=student_id).first()
                name = ""
                if not user:
                    # Could not match user to id
                    result = "fail"
                else:
                    existing_checkin = CrewAttendanceRecord.objects.filter(user=user, active=True).first()
                    if existing_checkin and existing_checkin.event != event:
                        # User is checked in somewhere else
                        result = "checkin-fail"
                    else:
                        # Check for crew limit
                        if event.max_crew and event.crew_attendance.filter(active=True).count() == event.max_crew and \
                                not existing_checkin:
                            result = "checkin-limit"
                        else:
                            record, created = CrewAttendanceRecord.objects.get_or_create(
                                event=event, user=user, active=True
                            )
                            if not created:
                                # Check out
                                record.checkout = timezone.now()
                                record.active = False
                                record.save()
                                result = "checkout-success"
                            else:
                                # Checked in (get user's name to display)
                                name = user.nickname
                                if not name:
                                    name = user.first_name
                                if not event.hours.filter(user=user).exists():
                                    # Record placeholder hour if hours are not already recorded
                                    event.hours.create(user=user)
                                result = "checkin-success"
                form = BulkCheckinForm(result=result, user_name=name, event=event.event_name)
        else:
            form = BulkCheckinForm(result=None, user_name=None, event=event.event_name)
    else:
        events = Event2019.objects.filter(
            datetime_end__gt=timezone.now() + timezone.timedelta(hours=-5), sensitive=False, closed=False,
            cancelled=False, ccinstances__setup_start__lte=timezone.now()).distinct()

        # Officers can use this tool even if they aren't a CC for the event
        if not is_officer(request.user):
            events = events.filter(ccinstances__crew_chief=request.user)
        for event in events:
            if event.max_crew and event.crew_attendance.filter(active=True).count() == event.max_crew:
                events = events.exclude(pk=event.pk)

        if events.count() == 0:
            context['page'] = {"title": "Hmm. We couldn't find any eligible events.",
                               "body": "<p>If you are not a crew chief, please use the standard checkin / checkout "
                                       "tools.<br><br></p><a href='" + reverse("events:crew-tracker") +
                                       "' class='btn btn-primary'>Back</a>"}
            return render(request, 'static_page.html', context)

        if request.method == 'POST':
            form = CrewCheckinForm(request.POST, events=events, title="Bulk Checkin")
            if form.is_valid():
                event = request.POST['event']
                return HttpResponseRedirect(reverse("events:crew-bulk") + "?id=" + event)
        else:
            form = CrewCheckinForm(events=events, title="Bulk Checkin")
    context['form'] = form
    return render(request, 'form_crispy_static.html', context)


@login_required
def rmcc(request, id, user):
    """
    Remove a crew chief from an event (pre-2019 events only)

    :param id: The primary key value of the event
    :param user: The primary key value of the user
    """
    event = get_object_or_404(Event, pk=id)
    if not (request.user.has_perm('events.edit_event_hours') or
            request.user.has_perm('events.edit_event_hours', event)):
        raise PermissionDenied
    if event.closed:
        messages.add_message(request, messages.ERROR, 'Event is closed.')
        return HttpResponseRedirect(reverse('events:detail', args=(event.id,)))
    event.crew_chief.remove(user)
    return HttpResponseRedirect(reverse("events:chiefs", args=(event.id,)))


@login_required
def assigncc(request, id):
    """ Assign crew chiefs to an event """
    context = {}

    event = get_object_or_404(BaseEvent, pk=id)

    if not (request.user.has_perm('events.edit_event_hours') or
            request.user.has_perm('events.edit_event_hours', event)):
        raise PermissionDenied
    if event.closed:
        messages.add_message(request, messages.ERROR, 'Event is closed.')
        return HttpResponseRedirect(reverse('events:detail', args=(event.id,)))
    context['event'] = event
    context['oldevent'] = isinstance(event, Event)

    cc_formset = inlineformset_factory(Event, EventCCInstance, extra=5, exclude=[])
    cc_formset.form = curry_class(CCIForm, event=event)

    if request.method == 'POST':
        formset = cc_formset(request.POST, instance=event)
        if formset.is_valid():
            formset.save()
            return HttpResponseRedirect(reverse('events:detail', args=(event.id,)))
    else:
        formset = cc_formset(instance=event)

    context['formset'] = formset

    return render(request, 'formset_crispy_helpers.html', context)


@login_required
def assignattach(request, id):
    """ Update attachments for an event (file uploads) """
    context = {}

    event = get_object_or_404(BaseEvent, pk=id)
    if not (request.user.has_perm('events.event_attachments') or
            request.user.has_perm('events.event_attachments', event)):
        raise PermissionDenied
    if event.closed:
        messages.add_message(request, messages.ERROR, 'Event is closed.')
        return HttpResponseRedirect(reverse('events:detail', args=(event.id,)))
    context['event'] = event

    att_formset = inlineformset_factory(BaseEvent, EventAttachment, extra=2, exclude=[])
    att_formset.form = curry_class(AttachmentForm, event=event)

    if request.method == 'POST':
        set_revision_comment("Edited attachments", None)
        formset = att_formset(request.POST, request.FILES, instance=event)
        if formset.is_valid():
            formset.save()
            event.save()  # for revision to be created
            should_send_email = not event.test_event
            if should_send_email:
                to = [settings.EMAIL_TARGET_VP]
                if hasattr(event, 'projection') and event.projection \
                        or event.serviceinstance_set.filter(service__category__name='Projection').exists():
                    to.append(settings.EMAIL_TARGET_HP)
                for ccinstance in event.ccinstances.all():
                    if ccinstance.crew_chief.email:
                        prefs, created = UserPreferences.objects.get_or_create(user=ccinstance.crew_chief)
                        if not prefs.ignore_user_action or ccinstance.crew_chief != request.user:
                            to.append(ccinstance.crew_chief.email)
                subject = "Event Attachments"
                email_body = "Attachments for the following event were modified by %s." % request.user.get_full_name()
                email = EventEmailGenerator(event=event, subject=subject, to_emails=to, body=email_body)
                email.send()
            return HttpResponseRedirect(reverse('events:detail', args=(event.id,)))
    else:
        formset = att_formset(instance=event)

    context['formset'] = formset

    return render(request, 'formset_crispy_attachments.html', context)


@login_required
def assignattach_external(request, id):
    """ Update attachments for an event (client-view) """
    context = {}

    event = get_object_or_404(BaseEvent, pk=id)
    if event.closed:
        messages.add_message(request, messages.ERROR, 'Event is closed.')
        return HttpResponseRedirect(reverse('events:detail', args=(event.id,)))

    context['event'] = event

    mk_att_formset = inlineformset_factory(Event, EventAttachment, extra=1, exclude=[])
    # mk_att_formset.queryset = mk_att_formset.queryset.filter(externally_uploaded=True)
    mk_att_formset.form = curry_class(AttachmentForm, event=event, externally_uploaded=True)

    if request.method == 'POST':
        set_revision_comment("Edited attachments", None)
        formset = mk_att_formset(request.POST, request.FILES, instance=event,
                                 queryset=EventAttachment.objects.filter(externally_uploaded=True))
        if formset.is_valid():
            f = formset.save(commit=False)
            for i in f:
                i.externally_uploaded = True
                i.save()
            event.save()  # for revision to be created
            return HttpResponseRedirect(reverse('my:workorders', ))
    else:
        formset = mk_att_formset(instance=event, queryset=EventAttachment.objects.filter(externally_uploaded=True))

    context['formset'] = formset

    return render(request, 'formset_crispy_attachments.html', context)


@login_required
def download_ics(request, pk):
    """ Generate and download an ics file """

    event = get_object_or_404(BaseEvent, pk=pk)
    invite = generate_ics([event], None)

    response = HttpResponse(invite, content_type="text/calendar")
    response['Content-Disposition'] = "attachment; filename=event.ics"
    return response


@login_required
def extras(request, id):
    """ This form is for adding extras to an event """
    context = {'msg': "Extras"}

    event = get_object_or_404(BaseEvent, pk=id)

    if not (request.user.has_perm('events.adjust_event_charges') or
            request.user.has_perm('events.adjust_event_charges', event)):
        raise PermissionDenied
    if event.closed:
        messages.add_message(request, messages.ERROR, 'Event is closed.')
        return HttpResponseRedirect(reverse('events:detail', args=(event.id,)))
    context['event'] = event

    mk_extra_formset = inlineformset_factory(BaseEvent, ExtraInstance, extra=1, exclude=[])
    mk_extra_formset.form = ExtraForm

    if request.method == 'POST':
        set_revision_comment("Edited extras", None)
        formset = mk_extra_formset(request.POST, request.FILES, instance=event)
        if formset.is_valid():
            formset.save()
            event.save()  # for revision to be created
            return HttpResponseRedirect(reverse('events:detail', args=(event.id,)) + "#billing")
    else:
        formset = mk_extra_formset(instance=event)

    context['formset'] = formset

    if any(event.extrainstance_set.values_list('extra__disappear', flat=True)):
        messages.add_message(request, messages.ERROR, 'One or more of the existing extras of this \
        event has since been removed as an available extra. You cannot make any changes to the extras \
        of this event without deleting those rows. If you believe this is in error, contact the webmaster.')
    return render(request, 'formset_crispy_extras.html', context)


@login_required
def oneoff(request, id):
    """ This form is for adding oneoff fees to an event """
    context = {'msg': "One-Off Charges"}

    event = get_object_or_404(BaseEvent, pk=id)
    context['event'] = event

    if not (request.user.has_perm('events.adjust_event_charges') or
            request.user.has_perm('events.adjust_event_charges', event)):
        raise PermissionDenied
    if event.closed:
        messages.add_message(request, messages.ERROR, 'Event is closed.')
        return HttpResponseRedirect(reverse('events:detail', args=(event.id,)))

    mk_oneoff_formset = inlineformset_factory(BaseEvent, EventArbitrary, extra=3, exclude=[])

    if request.method == 'POST':
        set_revision_comment("Edited billing charges", None)
        formset = mk_oneoff_formset(request.POST, request.FILES, instance=event)
        if formset.is_valid():
            formset.save()
            event.save()  # for revision to be created
            return HttpResponseRedirect(reverse('events:detail', args=(event.id,)) + "#billing")
    else:
        formset = mk_oneoff_formset(instance=event)

    context['formset'] = formset

    return render(request, 'formset_crispy_arbitrary.html', context)


@login_required
def viewevent(request, id):
    """ View event details """
    context = {}
    event = get_object_or_404(BaseEvent, pk=id)
    if not (request.user.has_perm('events.view_events') or request.user.has_perm('events.view_events', event)):
        raise PermissionDenied
    if event.sensitive and not request.user.has_perm('events.view_hidden_event', event):
        raise PermissionDenied

    send_survey_if_necessary(event)

    context['event'] = event
    # do not use .get_unique() because it does not follow relations
    context['history'] = Version.objects.get_for_object(event)
    if isinstance(event, Event2019):
        context['crew_count'] = event.crew_attendance.filter(active=True).values('user').count()
    if event.serviceinstance_set.exists():
        context['categorized_services_and_extras'] = {}
        for category in Category.objects.all():
            # tuple (serviceinstances, extrainstances)
            services_and_extras = (
                list(event.serviceinstance_set.filter(service__category=category)),
                list(event.extrainstance_set.filter(extra__category=category))
            )
            # do not add category if it is empty
            if services_and_extras[0] or services_and_extras[1]:
                context['categorized_services_and_extras'][category.name] = services_and_extras
    if event.surveys.exists() and request.user.has_perm('events.view_posteventsurveyresults', event.surveys.all().first()):
        context['survey_takers'] = get_user_model().objects.filter(pk__in=event.surveys.values_list('person', flat=True))
        work_order_method_choices = dict(PostEventSurvey._meta.get_field('work_order_method').choices)
        context['survey_workorder_methods'] = [work_order_method_choices[choice] for choice in event.surveys.values_list('work_order_method', flat=True)]
        context['survey_workorder_comments'] = [c for c in event.surveys.values_list('work_order_comments', flat=True) if c != '']
        context['survey_comments'] = [c for c in event.surveys.values_list('comments', flat=True) if c != '']
        context['survey_results'] = {}
        context['survey_results'].update(event.surveys.filter(services_quality__gte=0).aggregate(
            Avg('services_quality'),
            Count('services_quality'),
        ))
        context['survey_results']['services_quality__verbose_name'] = PostEventSurvey._meta.get_field('services_quality').verbose_name
        context['survey_results'].update(event.surveys.filter(lighting_quality__gte=0).aggregate(
            Avg('lighting_quality'),
            Count('lighting_quality'),
        ))
        context['survey_results']['lighting_quality__verbose_name'] = PostEventSurvey._meta.get_field('lighting_quality').verbose_name
        context['survey_results'].update(event.surveys.filter(sound_quality__gte=0).aggregate(
            Avg('sound_quality'),
            Count('sound_quality'),
        ))
        context['survey_results']['sound_quality__verbose_name'] = PostEventSurvey._meta.get_field('sound_quality').verbose_name
        context['survey_results'].update(event.surveys.filter(work_order_experience__gte=0).aggregate(
            Avg('work_order_experience'),
            Count('work_order_experience'),
        ))
        context['survey_results']['work_order_experience__verbose_name'] = PostEventSurvey._meta.get_field('work_order_experience').verbose_name
        context['survey_results'].update(event.surveys.filter(work_order_ease__gte=0).aggregate(
            Avg('work_order_ease'),
            Count('work_order_ease'),
        ))
        context['survey_results']['work_order_ease__verbose_name'] = PostEventSurvey._meta.get_field('work_order_ease').verbose_name
        context['survey_results'].update(event.surveys.filter(communication_responsiveness__gte=0).aggregate(
            Avg('communication_responsiveness'),
            Count('communication_responsiveness'),
        ))
        context['survey_results']['communication_responsiveness__verbose_name'] = PostEventSurvey._meta.get_field('communication_responsiveness').verbose_name
        context['survey_results'].update(event.surveys.filter(pricelist_ux__gte=0).aggregate(
            Avg('pricelist_ux'),
            Count('pricelist_ux'),
        ))
        context['survey_results']['pricelist_ux__verbose_name'] = PostEventSurvey._meta.get_field('pricelist_ux').verbose_name
        context['survey_results'].update(event.surveys.filter(setup_on_time__gte=0).aggregate(
            Avg('setup_on_time'),
            Count('setup_on_time'),
        ))
        context['survey_results']['setup_on_time__verbose_name'] = PostEventSurvey._meta.get_field('setup_on_time').verbose_name
        context['survey_results'].update(event.surveys.filter(crew_respectfulness__gte=0).aggregate(
            Avg('crew_respectfulness'),
            Count('crew_respectfulness'),
        ))
        context['survey_results']['crew_respectfulness__verbose_name'] = PostEventSurvey._meta.get_field('crew_respectfulness').verbose_name
        context['survey_results'].update(event.surveys.filter(price_appropriate__gte=0).aggregate(
            Avg('price_appropriate'),
            Count('price_appropriate'),
        ))
        context['survey_results']['price_appropriate__verbose_name'] = PostEventSurvey._meta.get_field('price_appropriate').verbose_name
        context['survey_results'].update(event.surveys.filter(customer_would_return__gte=0).aggregate(
            Avg('customer_would_return'),
            Count('customer_would_return'),
        ))
        context['survey_results']['customer_would_return__verbose_name'] = PostEventSurvey._meta.get_field('customer_would_return').verbose_name
        context['survey_composites'] = {}
        try:
            context['survey_composites']['vp'] = context['survey_results']['communication_responsiveness__avg']
        except TypeError:
            context['survey_composites']['vp'] = None

        crew_avg = 0
        crew_count = 4
        try:
            crew_avg += context['survey_results']['setup_on_time__avg']
        except TypeError:
            crew_count -= 1
        try:
            crew_avg += context['survey_results']['crew_respectfulness__avg']
        except TypeError:
            crew_count -= 1
        try:
            crew_avg += context['survey_results']['lighting_quality__avg']
        except TypeError:
            crew_count -= 1
        try:
            crew_avg += context['survey_results']['sound_quality__avg']
        except TypeError:
            crew_count -= 1
        if crew_count == 0:
            context['survey_composites']['crew'] = None
        else:
            context['survey_composites']['crew'] = crew_avg / crew_count

        price_avg = 0
        price_count = 2
        try:
            price_avg += context['survey_results']['pricelist_ux__avg']
        except TypeError:
            price_count -= 1
        try:
            price_avg += context['survey_results']['price_appropriate__avg']
        except TypeError:
            price_count -= 1
        if price_count == 0:
            context['survey_composites']['pricelist'] = None
        else:
            context['survey_composites']['pricelist'] = price_avg / price_count

        overall_avg = 0
        overall_count = 2
        try:
            overall_avg += context['survey_results']['services_quality__avg']
        except TypeError:
            overall_count -= 1
        try:
            overall_avg += context['survey_results']['customer_would_return__avg']
        except TypeError:
            overall_count -= 1
        if overall_count == 0:
            context['survey_composites']['overall'] = None
        else:
            context['survey_composites']['overall'] = overall_avg / overall_count

    # Determine which apps will be visible
    apps = []

    if isinstance(event, Event2019):
        # Spotify
        if event.approved and request.user.has_perm('spotify.view_session'):
            if not event.session_set.first() and not event.reviewed and not event.cancelled and not event.closed \
                    and (request.user in [cc.crew_chief for cc in event.ccinstances.all()] or
                         request.user.has_perm('spotify.add_session')):
                apps.append('spotify')
            elif event.session_set.first():
                apps.append('spotify')

        # Automatically stop accepting song requests if event is no longer eligible
        if event.session_set.first():
            session = event.session_set.first()
            if session.accepting_requests and (not event.approved or event.reviewed or event.cancelled or event.closed):
                session.accepting_requests = False
                session.save()

    context['apps'] = apps

    return render(request, 'uglydetail.html', context)


class CCRCreate(SetFormMsgMixin, HasPermOrTestMixin, ConditionalFormMixin, LoginRequiredMixin, CreateView):
    """ Create a new crew chief report """
    model = CCReport
    form_class = InternalReportForm
    template_name = "form_crispy_cbv.html"
    msg = "New Crew Chief Report"
    perms = 'events.add_event_report'

    def dispatch(self, request, *args, **kwargs):
        self.event = get_object_or_404(BaseEvent, pk=kwargs['event'])
        if not self.event.reports_editable and not request.user.has_perm(self.perms) and \
                request.user.has_perm(self.perms, self.event):
            return render(request, 'too_late.html', {'days': CCR_DELTA, 'event': self.event})
        return super(CCRCreate, self).dispatch(request, *args, **kwargs)

    def user_passes_test(self, request, *args, **kwargs):
        return self.event.reports_editable and request.user.has_perm(self.perms, self.event)

    def get_form_kwargs(self):
        kwargs = super(CCRCreate, self).get_form_kwargs()
        kwargs['event'] = self.event
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Crew Chief Report Created!", extra_tags='success')
        return super(CCRCreate, self).form_valid(form)

    def get_success_url(self):
        return reverse("events:detail", args=(self.kwargs['event'],))


class CCRUpdate(SetFormMsgMixin, ConditionalFormMixin, HasPermOrTestMixin, LoginRequiredMixin, UpdateView):
    """ Update an existing crew chief report """
    model = CCReport
    form_class = InternalReportForm
    template_name = "form_crispy_cbv.html"
    msg = "Update Crew Chief Report"
    perms = 'events.change_ccreport'

    def user_passes_test(self, request, *args, **kwargs):
        obj = self.get_object()
        return obj.event.reports_editable and request.user.has_perm(self.perms, obj)

    def get_form_kwargs(self):
        kwargs = super(CCRUpdate, self).get_form_kwargs()
        event = get_object_or_404(BaseEvent, pk=self.kwargs['event'])
        kwargs['event'] = event
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Crew Chief Report Updated!", extra_tags='success')
        return super(CCRUpdate, self).form_valid(form)

    def get_success_url(self):
        return reverse("events:detail", args=(self.kwargs['event'],))


class CCRDelete(SetFormMsgMixin, HasPermOrTestMixin, LoginRequiredMixin, DeleteView):
    """ Delete a crew chief report """
    model = CCReport
    template_name = "form_delete_cbv.html"
    msg = "Deleted Crew Chief Report"
    perms = 'events.delete_ccreport'

    def user_passes_test(self, request, *args, **kwargs):
        obj = self.get_object()
        return obj.event.reports_editable and request.user.has_perm(self.perms, obj)

    def get_object(self, queryset=None):
        """ Hook to ensure object isn't closed """
        obj = super(CCRDelete, self).get_object()
        if obj.event.closed:
            raise ValidationError("Event is closed")
        else:
            return obj

    def get_success_url(self):
        return reverse("events:detail", args=(self.kwargs['event'],))


class BillingCreate(SetFormMsgMixin, HasPermMixin, LoginRequiredMixin, CreateView):
    model = Billing
    form_class = BillingForm
    template_name = "form_crispy_cbv.html"
    msg = "New Bill"
    perms = 'events.bill_event'

    def dispatch(self, request, *args, **kwargs):
        self.event = get_object_or_404(BaseEvent, pk=self.kwargs['event'])
        if self.event.closed:
            messages.add_message(request, messages.ERROR, 'Event is closed.')
            return HttpResponseRedirect(reverse('events:detail', args=(self.kwargs['event'],)))
        return super(BillingCreate, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(BillingCreate, self).get_context_data(**kwargs)
        if self.event.closed:
            raise PermissionDenied
        orgs = self.event.org.all()
        orgstrings = ",".join(["%s's billing account was last verified: %s" % (
            o.name, o.verifications.latest().date if o.verifications.exists() else "Never") for o in orgs])
        context['extra'] = orgstrings
        return context

    def get_form_kwargs(self):
        # pass "user" keyword argument with the current user to your form
        kwargs = super(BillingCreate, self).get_form_kwargs()
        kwargs['event'] = self.event
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Bill Created!", extra_tags='success')
        return super(BillingCreate, self).form_valid(form)

    def get_success_url(self):
        if 'save-and-make-email' in self.request.POST:
            return reverse("events:bills:email", args=(self.kwargs['event'], self.object.pk))
        else:
            return reverse("events:detail", args=(self.kwargs['event'],)) + "#billing"


class BillingUpdate(SetFormMsgMixin, HasPermMixin, LoginRequiredMixin, UpdateView):
    model = Billing
    form_class = BillingUpdateForm
    template_name = "form_crispy_cbv.html"
    msg = "Update Bill"
    perms = 'events.bill_event'

    def dispatch(self, request, *args, **kwargs):
        self.event = get_object_or_404(BaseEvent, pk=self.kwargs['event'])
        if self.event.closed:
            messages.add_message(request, messages.ERROR, 'Event is closed.')
            return HttpResponseRedirect(reverse('events:detail', args=(self.kwargs['event'],)))
        return super(BillingUpdate, self).dispatch(request, *args, **kwargs)

    def get_object(self, *args, **kwargs):
        """ Validate preconditions for editing a bill """
        obj = super(BillingUpdate, self).get_object(*args, **kwargs)
        if obj.event.closed:
            raise PermissionDenied
        else:
            return obj

    def get_form_kwargs(self):
        kwargs = super(BillingUpdate, self).get_form_kwargs()
        kwargs['event'] = self.event
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Billing Updated!", extra_tags='success')
        return super(BillingUpdate, self).form_valid(form)

    def get_success_url(self):
        return reverse("events:detail", args=(self.kwargs['event'],)) + "#billing"


class BillingDelete(HasPermMixin, LoginRequiredMixin, DeleteView):
    model = Billing
    template_name = "form_delete_cbv.html"
    msg = "Deleted Bill"
    perms = 'events.bill_event'

    def dispatch(self, request, *args, **kwargs):
        self.event = get_object_or_404(BaseEvent, pk=self.kwargs['event'])
        if self.event.closed:
            messages.add_message(request, messages.ERROR, 'Event is closed.')
            return HttpResponseRedirect(reverse('events:detail', args=(self.kwargs['event'],)))
        return super(BillingDelete, self).dispatch(request, *args, **kwargs)

    def get_object(self, *args, **kwargs):
        """ Validate preconditions for deleting a bill """
        obj = super(BillingDelete, self).get_object(*args, **kwargs)
        if obj.date_paid:
            raise PermissionDenied
        if obj.event.closed:
            raise PermissionDenied
        else:
            return obj

    def get_success_url(self):
        return reverse("events:detail", args=(self.kwargs['event'],)) + "#billing"


class MultiBillingCreate(SetFormMsgMixin, HasPermMixin, LoginRequiredMixin, CreateView):
    model = MultiBilling
    form_class = MultiBillingForm
    template_name = "form_crispy.html"
    msg = "New MultiBill"
    perms = 'events.bill_event'

    def get_form_kwargs(self):
        kwargs = super(MultiBillingCreate, self).get_form_kwargs()
        kwargs['show_nonbulk_events'] = self.request.GET.get('show_nonbulk_events') == 'true'
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "MultiBill Created!", extra_tags='success')
        return super(MultiBillingCreate, self).form_valid(form)

    def get_success_url(self):
        if 'save-and-make-email' in self.request.POST:
            return reverse("events:multibillings:email", args=(self.object.pk,))
        else:
            return reverse("events:multibillings:list")


class MultiBillingUpdate(SetFormMsgMixin, HasPermMixin, LoginRequiredMixin, UpdateView):
    model = MultiBilling
    form_class = MultiBillingUpdateForm
    template_name = "form_crispy.html"
    msg = "Update MultiBill"
    perms = 'events.bill_event'

    def get_object(self, *args, **kwargs):
        """ Validate preconditions for editing a multibill """
        obj = super(MultiBillingUpdate, self).get_object(*args, **kwargs)
        if obj.events.filter(closed=True).exists():
            raise PermissionDenied
        else:
            return obj

    def form_valid(self, form):
        messages.success(self.request, "MultiBill Updated!", extra_tags='success')
        return super(MultiBillingUpdate, self).form_valid(form)

    def get_success_url(self):
        return reverse("events:multibillings:list")


class MultiBillingDelete(HasPermMixin, LoginRequiredMixin, DeleteView):
    model = MultiBilling
    template_name = "form_delete_cbv.html"
    msg = "Delete MultiBill"
    perms = 'events.bill_event'

    def get_object(self, *args, **kwargs):
        """ Validate preconditions for deleting a multibill """
        obj = super(MultiBillingDelete, self).get_object(*args, **kwargs)
        if obj.date_paid:
            raise PermissionDenied
        if obj.events.filter(closed=True).exists():
            raise PermissionDenied
        else:
            return obj

    def get_success_url(self):
        return reverse("events:multibillings:list")


@require_POST
@login_required
def pay_bill(request, event, pk):
    """
    Quietly pays a bill, showing a message on the next page. POST only.
    """
    bill = get_object_or_404(Billing, event_id=event, id=pk)
    if not request.user.has_perm('events.bill_event', bill.event):
        raise PermissionDenied
    if bill.event.closed:
        messages.add_message(request, messages.ERROR, 'Event is closed.')
        return HttpResponseRedirect(reverse('events:detail', args=(bill.event_id,)))
    if bill.date_paid:
        messages.info(request, "Bill has already been paid", extra_tags="info")
    else:
        bill.date_paid = timezone.now()
        bill.save()
        if 'next' in request.GET:
            messages.success(request, "Marked latest bill paid for %s" % bill.event.event_name, extra_tags="success")
        else:
            messages.success(request, "Bill paid!", extra_tags="success")
    if 'next' in request.GET:
        return HttpResponseRedirect(request.GET['next'])
    else:
        return HttpResponseRedirect(reverse('events:detail', args=(bill.event_id,)) + "#billing")


class BillingEmailCreate(SetFormMsgMixin, HasPermMixin, LoginRequiredMixin, CreateView):
    model = BillingEmail
    form_class = BillingEmailForm
    template_name = "form_crispy.html"
    msg = "New Billing Email"
    perms = 'events.bill_event'

    def dispatch(self, request, *args, **kwargs):
        self.billing = get_object_or_404(Billing, pk=self.kwargs['billing'])
        return super(BillingEmailCreate, self).dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        # pass "user" keyword argument with the current user to your form
        kwargs = super(BillingEmailCreate, self).get_form_kwargs()
        kwargs['billing'] = self.billing
        kwargs['initial'] = {'subject': render_to_string('emails/email_billing_subject.txt', {'billing': self.billing},
                                                         request=self.request),
                             'message': render_to_string('emails/email_billing_message.txt', {'billing': self.billing},
                                                         request=self.request)}
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Billing Email Created!", extra_tags='success')
        response = super(BillingEmailCreate, self).form_valid(form)
        # send the email
        i = form.instance
        event = self.billing.event
        to = list(i.email_to_users.values_list('email', flat=True))
        to.extend(list(i.email_to_orgs.values_list('exec_email', flat=True)))
        pdf_handle = generate_event_bill_pdf_standalone(event, request=self.request)
        filename = "%s-bill.pdf" % slugify(event.event_name)
        attachments = [{"file_handle": pdf_handle, "name": filename}]
        email = BillingEmailGenerator(event=event, subject=i.subject, body=i.message, to_emails=to, attachments=attachments)
        email.send()
        i.sent_at = timezone.now()
        i.save()
        return response

    def get_success_url(self):
        return reverse("events:detail", args=(self.billing.event_id,)) + "#billing"


class MultiBillingEmailCreate(SetFormMsgMixin, HasPermMixin, LoginRequiredMixin, CreateView):
    model = MultiBillingEmail
    form_class = MultiBillingEmailForm
    template_name = "form_crispy.html"
    msg = "New Billing Email"
    perms = 'events.bill_event'

    def dispatch(self, request, *args, **kwargs):
        self.multibilling = get_object_or_404(MultiBilling, pk=self.kwargs['multibilling'])
        return super(MultiBillingEmailCreate, self).dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        # pass "user" keyword argument with the current user to your form
        kwargs = super(MultiBillingEmailCreate, self).get_form_kwargs()
        kwargs['multibilling'] = self.multibilling
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Billing Email Created!", extra_tags='success')
        response = super(MultiBillingEmailCreate, self).form_valid(form)
        # send the email
        i = form.instance
        to = list(i.email_to_users.values_list('email', flat=True))
        to.extend(list(i.email_to_orgs.values_list('exec_email', flat=True)))
        pdf_handle = generate_multibill_pdf_standalone(self.multibilling, request=self.request)
        filename = "bill.pdf"
        attachments = [{"file_handle": pdf_handle, "name": filename}]
        email = DLEG(subject=i.subject, body=i.message, to_emails=to, reply_to=[settings.EMAIL_TARGET_T],
                     bcc=[settings.EMAIL_TARGET_T], attachments=attachments)
        email.send()
        i.sent_at = timezone.now()
        i.save()
        return response

    def get_success_url(self):
        return reverse("events:multibillings:list")


class WorkdayEntry(HasPermOrTestMixin, LoginRequiredMixin, UpdateView):
    model = Event2019
    form_class = WorkdayForm
    template_name = "form_crispy_workday.html"
    perms = 'events.edit_org_billing'

    def user_passes_test(self, request, *args, **kwargs):
        obj = self.get_object()
        return request.user.has_perm(self.perms, obj.org_to_be_billed) or request.GET.get('verification') == obj.workday_form_hash

    def get_initial(self):
        initial = self.initial
        obj = self.get_object()
        org = obj.org_to_be_billed
        if obj.workday_fund is None:
            initial['workday_fund'] = org.workday_fund
        if obj.worktag is None:
            initial['worktag'] = org.worktag
        return initial

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        is_update = self.object.workday_fund is not None or self.object.worktag is not None
        if self.object.closed:
            messages.add_message(request, messages.ERROR, 'Event is closed.')
            return HttpResponseRedirect(reverse('events:detail', args=(self.object.pk,)))
        if not self.object.reviewed:
            messages.add_message(request, messages.ERROR, 'Event has not been reviewed for billing.')
            return HttpResponseRedirect(reverse('events:detail', args=(self.object.pk,)))
        if not self.object.billings.exists():
            messages.add_message(request, messages.ERROR, 'Event has not yet been billed.')
            return HttpResponseRedirect(reverse('events:detail', args=(self.object.pk,)))
        if self.object.paid:
            messages.add_message(request, messages.ERROR, 'Event has already been paid.')
            return HttpResponseRedirect(reverse('events:detail', args=(self.object.pk,)))
        if self.object.entered_into_workday:
            messages.add_message(request, messages.ERROR, 'An Internal Service Delivery has already been created in '
                                                          'Workday for this event. The worktag to charge can no longer '
                                                          'be edited through this website.')
            return HttpResponseRedirect(reverse('events:detail', args=(self.object.pk,)))
        if is_update:
            messages.add_message(request, messages.INFO, 'This bill payment form has already been filled out by {}. '
                                                         'You are editing it.'.format(self.object.workday_entered_by))
        return super(WorkdayEntry, self).dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        # Automatically add the user who submitted the workday form to the client
        org = self.object.org_to_be_billed
        if org is not None and self.request.user not in org.associated_users.all():
            set_revision_comment("Entered Workday billing info for {}. User automatically added to client.".format(
                self.object.event_name), form)
            org.associated_users.add(self.request.user)
        else:
            set_revision_comment("Entered Workday billing info", form)
        # Add workday info to organization info if not already saved
        if org.workday_fund is None or org.worktag is None:
            org.workday_fund = self.object.workday_fund
            org.worktag = self.object.worktag
            org.save()
        # If the workday info is being updated as opposed to entered for the first time, send an email to the Treasurer
        if self.object.workday_fund is not None or self.object.worktag is not None:
            email_body = "The workday billing info for the following event was updated by {}. The previous version " \
                         "had been entered by {}.".format(self.request.user, self.object.workday_entered_by)
            if len(form.changed_data) > 0:
                email_body += "\nFields changed: "
                for field_name in form.changed_data:
                    email_body += field_name + ", "
                email_body = email_body[:-2]
            email = EventEmailGenerator(
                event=self.object,
                subject='Event Workday Info Updated',
                to_emails=settings.EMAIL_TARGET_T,
                body=email_body
            )
            email.send()
        self.object.workday_entered_by = self.request.user
        messages.success(self.request, "Billing info received. Please approve the Internal Service Delivery in "
                                       "Workday when you receive it.", extra_tags='success')
        return super(WorkdayEntry, self).form_valid(form)

    def get_success_url(self):
        return reverse("events:detail", args=(self.object.pk,))


@require_POST
@login_required
def mark_entered_into_workday(request, id):
    """
    Marks an event as entered into Workday. POST only.
    """
    event = get_object_or_404(Event2019, id=id)
    if not request.user.has_perm('events.bill_event', event):
        raise PermissionDenied
    if event.closed:
        messages.add_message(request, messages.ERROR, 'Event is closed.')
        return HttpResponseRedirect(reverse('events:detail', args=(event.id,)))
    if event.entered_into_workday:
        messages.info(request, "Event has already been marked entered into Workday.", extra_tags="info")
    if not event.reviewed:
        messages.add_message(request, messages.ERROR, 'Event has not been reviewed for billing.')
        return HttpResponseRedirect(reverse('events:detail', args=(event.id,)))
    if not event.last_bill:
        messages.add_message(request, messages.ERROR, 'Event has not been billed.')
        return HttpResponseRedirect(reverse('events:detail', args=(event.id,)))
    else:
        event.entered_into_workday = True
        set_revision_comment("Marked entered into Workday", None)
        event.save()
        messages.success(request, "Marked %s as entered into Workday." % event.event_name, extra_tags="success")
    return HttpResponseRedirect(reverse('events:awaitingworkday'))
