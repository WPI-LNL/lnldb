# Create your views here.
import datetime

from crispy_forms.layout import Submit
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Q
from django.conf import settings
from django.forms.formsets import formset_factory
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.views.generic.edit import CreateView, DeleteView, FormView
from django.urls.base import reverse

from helpers.mixins import HasPermMixin, LoginRequiredMixin
from projection.forms import (BulkCreateForm, BulkUpdateForm, DateEntryFormSetBase, ProjectionistForm,
                              ProjectionistUpdateForm, PITRequestForm, PITRequestAdminForm, PITFormset)
from projection.models import PITLevel, Projectionist, PitRequest
from emails.generators import GenericEmailGenerator


@login_required
@permission_required('projection.view_pits', raise_exception=True)
def plist(request):
    context = {}
    users = Projectionist.objects.select_related('user').order_by('user__last_name')

    context['users'] = users
    context['h2'] = "Projectionist List"

    return render(request, 'projectionlist.html', context)


@login_required
@permission_required('projection.view_pits', raise_exception=True)
def plist_detail(request):
    context = {}
    levels = PITLevel.objects.exclude(name_short__in=['PP', 'L']) \
        .order_by('ordering')

    users = Projectionist.objects \
        .select_related('user')

    licensed = Q(pitinstances__pit_level__name_short__in=['PP', 'L'])
    alumni = Q(user__groups__name="Alumni")

    context['unlicensed_users'] = users.exclude(licensed)
    context['licensed_users'] = users.filter(licensed).exclude(alumni)
    context['alumni_users'] = users.filter(licensed).filter(alumni)
    context['levels'] = levels
    context['h2'] = "Projectionist List Detailed"

    return render(request, 'projectionlist_detail.html', context)


@login_required
@permission_required('projection.edit_pits', raise_exception=True)
def projection_update(request, id):
    projectionist = get_object_or_404(Projectionist, pk=id)
    context = {'msg': "Updating Projectionist %s" % projectionist}

    if request.method == "POST":
        form = ProjectionistUpdateForm(request.POST, instance=projectionist, prefix="main")
        formset = PITFormset(request.POST, instance=projectionist, prefix="nested")
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            return HttpResponseRedirect(reverse("projection:grid"))
        else:
            context['form'] = form
            context['formset'] = formset
    else:
        form = ProjectionistUpdateForm(instance=projectionist, prefix="main")
        formset = PITFormset(instance=projectionist, prefix="nested")
        context['form'] = form
        context['formset'] = formset
        context['pk'] = id

    return render(request, 'form_crispy_projection.html', context)


class ProjectionCreate(LoginRequiredMixin, HasPermMixin, CreateView):
    perms = 'projection.edit_pits'

    def get_context_data(self, **kwargs):
        context = super(ProjectionCreate, self).get_context_data(**kwargs)
        context['type'] = "hide"
        # No longer using the PIT form in this view
        # if self.request.POST:
        #     context['formset'] = PITFormset(self.request.POST)
        # else:
        #     context['formset'] = PITFormset()
        #     f = context['form']
        #     f.helper.layout.pop(-1)
        #     f.helper.form_tag = False
        #     context['form'] = f

        return context

    # def form_valid(self, form):
    #     context = self.get_context_data()
    #     pitform = context['formset']
    #
    #     if form.is_valid() and pitform.is_valid():
    #         self.object = form.save()
    #         pitform.instance = self.object
    #         pitform.save()
    #         return HttpResponseRedirect(self.success_url)
    #     else:
    #         return self.render_to_response(self.get_context_data(form=form))

    model = Projectionist
    template_name = "form_crispy_projection.html"
    form_class = ProjectionistForm
    # success_url = reverse("projection:list")

    @property
    def success_url(self):
        return reverse("projection:grid")


class BulkUpdateView(LoginRequiredMixin, HasPermMixin, FormView):
    template_name = "form_crispy_cbv.html"
    form_class = BulkUpdateForm
    perms = 'projection.edit_pits'

    @property
    def success_url(self):
        return reverse("projection:grid")

    def form_valid(self, form):
        # This method is called when valid form data has been POSTed.
        # It should return an HttpResponse.
        form.create_updates()
        return super(BulkUpdateView, self).form_valid(form)


class ProjectionistDelete(LoginRequiredMixin, HasPermMixin, DeleteView):
    model = Projectionist
    template_name = "form_delete_cbv.html"
    msg = "Deleted Projectionist"
    perms = 'projection.edit_pits'

    def get_success_url(self):
        return reverse("projection:grid")


def get_saturdays_for_range(date_1, date_2):
    # saturdays are used to represent the weeks, for reference
    saturdays = []
    # set to next saturday
    date_1 = date_1 + datetime.timedelta(days=(5 - date_1.weekday() + 7) % 7)
    # and then get all of them until we hit the end
    while date_1 <= date_2:
        saturdays.append(date_1)
        date_1 = date_1 + datetime.timedelta(days=7)
    return saturdays


# Non-Wizard Projection Bulk View
@login_required
@permission_required('projection.add_bulk_events', raise_exception=True)
def bulk_projection(request):
    context = {}

    if not request.GET:  # Step 1: get contact info and date range
        return render(request, "form_crispy.html", {
            'form': BulkCreateForm(),
            'msg': "Bulk Movie Addition"
        })

    basicinfoform = BulkCreateForm(request.GET)
    if not basicinfoform.is_valid():  # Bad user! Give me the contact/basics!!!
        return render(request, "form_crispy.html", {
            'form': basicinfoform,
            'msg': "Bulk Movie Addition (Errors)"
        })

    # Past this point, we have enough info for the full form

    # create our new form and pass it back
    date_start = basicinfoform.cleaned_data.get('date_first')
    date_end = basicinfoform.cleaned_data.get('date_second')

    # prepopulate things
    weeks = [{"date": date} for date in get_saturdays_for_range(date_start, date_end)]
    formset = formset_factory(DateEntryFormSetBase, extra=0)

    # depending on the return, do other things.
    if request.POST:
        # here we have our params and data
        filled = formset(request.POST, initial=weeks)
        if filled.is_valid():
            out = []
            for form in filled:
                out.extend(form.save_objects(
                    user=request.user,
                    contact=basicinfoform.cleaned_data.get('contact'),
                    org=basicinfoform.cleaned_data.get('billing'),
                    ip=request.META['REMOTE_ADDR']
                ))
            # after thats done
            context['result'] = out
            return render(request, "form_crispy_bulk_projection_done.html", context)

        else:
            context['form'] = filled
            return render(request, "form_crispy.html", context)
    else:
        # pass back the empty form
        context['msg'] = "Bulk Movie Addition - Choose Movie Details"
        context['form'] = formset(initial=weeks)
        context['helper'] = DateEntryFormSetBase().helper
        context['helper'].add_input(Submit('submit', 'Submit'))

        return render(request, "form_crispy.html", context)


def send_request_notification(form, update=False):
    name = form.instance.projectionist.user.get_full_name()
    pit = form.instance.level.name_long
    requested_date = form.instance.scheduled_for
    if requested_date is None:
        requested_date = "None"
    else:
        requested_date = requested_date.strftime('%b %d, %Y, %I:%M %p')
    message_context = {'CUSTOM_URL': True}
    message = "<strong>Projectionist:</strong> " + name + "<br><strong>PIT Level:</strong> " + \
              pit + "<br><strong>Requested Date:</strong> " + requested_date + \
              "<br><br><a href='https://lnl.wpi.edu" + reverse("projection:pit-schedule") + "'>Review</a>"
    if update:
        email = GenericEmailGenerator(subject="PIT Request Updated", to_emails=settings.EMAIL_TARGET_HP, body=message,
                                      context=message_context)
    else:
        email = GenericEmailGenerator(subject="New PIT Request", to_emails=settings.EMAIL_TARGET_HP, body=message,
                                      context=message_context)
    email.send()


class PITRequest(LoginRequiredMixin, HasPermMixin, FormView):
    perms = 'projection.view_pits'
    model = PitRequest
    template_name = "projection_pit_request.html"
    form_class = PITRequestForm

    def get_context_data(self, **kwargs):
        context = super(PITRequest, self).get_context_data(**kwargs)
        context['title'] = "Request PIT"
        context['desc'] = "Select the level of training you would like to receive. Then, if you\'d like, you may " \
                          "also request a specific date and time."
        context['NO_FOOT'] = True
        return context

    def form_valid(self, form):
        if self.request.POST:
            projectionist = Projectionist.objects.filter(user=self.request.user).first()
            if projectionist is None:
                projectionist = Projectionist.objects.create(user=self.request.user)
            form.instance.projectionist = projectionist
            form.save()
            send_request_notification(form)
            messages.add_message(self.request, messages.SUCCESS, 'You have successfully requested your next PIT. '
                                                                 'The HP will reach out to you shortly.')
            return HttpResponseRedirect(reverse('projection:grid'))


@login_required
@permission_required('projection.edit_pits', raise_exception=True)
def pit_schedule(request):
    context = {}

    approved = PitRequest.objects.filter(approved=True)
    pending = PitRequest.objects.filter(approved=False)

    context['approved'] = approved
    context['pending'] = pending
    context['NO_FOOT'] = True

    return render(request, 'projection_pit_schedule.html', context)


class CancelPITRequest(LoginRequiredMixin, HasPermMixin, DeleteView):
    model = PitRequest
    template_name = "form_cancel_request.html"
    msg = "Cancelled PIT Request"
    perms = 'projection.view_pits'

    def get_success_url(self):
        if self.request.user.has_perm('projection.edit_pits', self):
            return reverse("projection:pit-schedule")
        else:
            return reverse("projection:grid")


@login_required
@permission_required('projection.view_pits', raise_exception=True)
def pit_request_update(request, id):
    pit_request = get_object_or_404(PitRequest, pk=id)

    context = {'title': "Update PIT Request"}

    if request.method == "POST":
        form = PITRequestForm(request.POST, instance=pit_request, prefix="main")
        if form.is_valid():
            form.save()
            send_request_notification(form, True)
            if request.user.has_perm('projection.edit_pits', pit_request):
                return HttpResponseRedirect(reverse("projection:pit-schedule"))
            else:
                return HttpResponseRedirect(reverse("projection:grid"))
        else:
            context['form'] = form
    else:
        form = PITRequestForm(instance=pit_request, prefix="main")
        context['form'] = form
        context['pk'] = id

    return render(request, 'projection_pit_request.html', context)


@login_required
@permission_required('projection.edit_pits', raise_exception=True)
def manage_pit_request(request, id):
    pit_request = get_object_or_404(PitRequest, pk=id)

    context = {'title': "Manage PIT Request"}

    if request.method == "POST":
        form = PITRequestAdminForm(request.POST, instance=pit_request, prefix="main")
        if form.is_valid():
            form.save()
            user = form.instance.projectionist.user.email
            pit = form.instance.level.name_long
            requested_date = form.instance.scheduled_for.strftime('%b %d, %Y at %I:%M %p')
            message_context = {'CUSTOM_URL': True}
            message = "Your PIT request has been approved! You're now scheduled to get " + pit + " on <strong>" + \
                      requested_date + "</strong>. In the event that you need to reschedule or cancel this " \
                                       "appointment, please use the links below.<br><br><a href='https://lnl.wpi.edu"\
                      + reverse("projection:edit-request", args=[id]) + \
                      "'>Reschedule</a><br><a href='https://lnl.wpi.edu" + \
                      reverse("projection:cancel-request", args=[id]) + "'>Cancel</a>"
            email = GenericEmailGenerator(to_emails=user, subject="PIT Scheduled", body=message,
                                          context=message_context, reply_to=[settings.EMAIL_TARGET_HP])
            if form.instance.approved is True:
                email.send()
            return HttpResponseRedirect(reverse("projection:pit-schedule"))
        else:
            context['form'] = form
    else:
        form = PITRequestAdminForm(instance=pit_request, prefix="main")
        context['form'] = form
        context['pk'] = id

    return render(request, 'projection_pit_request.html', context)
