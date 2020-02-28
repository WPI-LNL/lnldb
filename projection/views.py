# Create your views here.
import datetime

from crispy_forms.layout import Submit
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.models import User
from django.db.models import Q
from django.forms.formsets import formset_factory
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.views.generic.edit import CreateView, DeleteView, FormView
from django.urls.base import reverse

from helpers.mixins import HasPermMixin, LoginRequiredMixin
from projection.forms import (BulkCreateForm, BulkUpdateForm,
                              DateEntryFormSetBase, PITFormset,
                              ProjectionistForm, ProjectionistUpdateForm, PITRequestForm, PITRequestAdminForm)
from projection.models import PITLevel, Projectionist, PitRequest


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
    context = {}
    context['msg'] = "Updating Projectionist %s" % projectionist

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
#         if self.request.POST:
#             context['formset'] = PITFormset(self.request.POST)
#         else:
#             context['formset'] = PITFormset()
#             f = context['form']
#             f.helper.layout.pop(-1)
#             f.helper.form_tag = False
#             context['form'] = f

        return context

    def form_valid(self, form):
        context = self.get_context_data()
        #pitform = context['formset']

        if form.is_valid():# and pitform.is_valid():
            self.object = form.save()
            #pitform.instance = self.object
            #pitform.save()
            return HttpResponseRedirect(self.success_url)
        else:
            return self.render_to_response(self.get_context_data(form=form))

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


class PITRequest(LoginRequiredMixin, HasPermMixin, FormView):
    perms = 'projection.view_pits'
    model = PitRequest
    template_name = "projection_pit_request.html"
    form_class = PITRequestForm

    def get_context_data(self, **kwargs):
        context = super(PITRequest, self).get_context_data(**kwargs)
        context['title'] = "Request PIT"
        context['desc'] = "Select the level of training you would like to receive. Then, if you\'d like, you may also request a specific date and time."
        context['NO_FOOT'] = True
        if 'title' in kwargs:
            context['title'] = kwargs['title']
            context['desc'] = kwargs['desc']
            context['form'] = ''
        return context

    def form_valid(self, form):
        if self.request.POST:
            form.instance.projectionist = get_object_or_404(Projectionist, user=self.request.user)
            if form.is_valid():
                form.save()
                return self.render_to_response(self.get_context_data(title="Request Submitted", desc="You have successfully requested your next PIT. The HP will reach out to you shortly."))


@login_required
@permission_required('projection.edit_pits', raise_exception=True)
def PITSchedule(request):
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

    context = {}
    context['title'] = "Update PIT Request"

    if request.method == "POST":
        form = PITRequestForm(request.POST, instance=pit_request, prefix="main")
        if form.is_valid():
            form.save()
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

    context = {}
    context['title'] = "Manage PIT Request"

    if request.method == "POST":
        form = PITRequestAdminForm(request.POST, instance=pit_request, prefix="main")
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(reverse("projection:pit-schedule"))
        else:
            context['form'] = form
    else:
        form = PITRequestAdminForm(instance=pit_request, prefix="main")
        context['form'] = form
        context['pk'] = id

    return render(request, 'projection_pit_request.html', context)