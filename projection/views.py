# Create your views here.
import datetime

from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect
from django.shortcuts import render, get_object_or_404
from django.db.models import Q, Prefetch
from django.views.generic.edit import CreateView
from django.views.generic.edit import DeleteView
from django.views.generic.edit import FormView
from events.models import Event
from events.models import Projection as ProjService
from events.models import Location
from projection.models import Projectionist, PITLevel, PitInstance
from projection.forms import ProjectionistUpdateForm
from projection.forms import ProjectionistForm
from projection.forms import PITFormset
from projection.forms import BulkUpdateForm
from projection.forms import BulkCreateForm
from projection.forms import DateEntryFormSetBase
from django.contrib.auth.decorators import login_required, permission_required
from django.forms.formsets import formset_factory
from django.utils import timezone
from helpers.mixins import LoginRequiredMixin, HasPermMixin
from crispy_forms.layout import Submit


@login_required
@permission_required('projection.view_pits', raise_exception=True)
def plist(request):
    context = {}
    users = Projectionist.objects.select_related().order_by('user__last_name')

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
        .select_related('user__first_name', 'user__last_name', 'user__username')

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
            return HttpResponseRedirect(reverse("projection-list-detail"))
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
        if self.request.POST:
            context['formset'] = PITFormset(self.request.POST)
        else:
            context['formset'] = PITFormset()
            f = context['form']
            f.helper.layout.pop(-1)
            f.helper.form_tag = False
            context['form'] = f

        return context

    def form_valid(self, form):
        context = self.get_context_data()
        pitform = context['formset']

        if form.is_valid() and pitform.is_valid():
            self.object = form.save()
            pitform.instance = self.object
            pitform.save()
            return HttpResponseRedirect(self.success_url)
        else:
            return self.render_to_response(self.get_context_data(form=form))

    model = Projectionist
    template_name = "form_crispy_projection.html"
    form_class = ProjectionistForm
    # success_url = reverse("projection-list")

    @property
    def success_url(self):
        return reverse('projection-list-detail')


class BulkUpdateView(LoginRequiredMixin, HasPermMixin, FormView):
    template_name = "form_crispy_cbv.html"
    form_class = BulkUpdateForm
    perms = 'projection.edit_pits'

    @property
    def success_url(self):
        return reverse('projection-list-detail')

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
        return reverse("projection-list-detail")


def get_saturdays_for_range(date_1, date_2):
    # saturdays are used to represent the weeks, for reference
    saturdays = []
    # set to next saturday
    date_1 = date_1 + datetime.timedelta(days=(5-date_1.weekday()+7)%7)
    # and then get all of them until we hit the end
    while date_1 <= date_2:
        saturdays.append(date_1)
        date_1 = date_1 + datetime.timedelta(days=7)
    return saturdays


### Non-Wizard Projection Bulk View
@login_required
@permission_required('projection.add_bulk_events', raise_exception=True)
def bulk_projection(request):
    context = {}
    tz = timezone.get_current_timezone()

    if not request.GET: # Step 1: get contact info and date range
        return render(request, "form_crispy.html", {
            'formset': BulkCreateForm(),
            'msg': "Bulk Movie Addition"
            })

    basicinfoform = BulkCreateForm(request.GET)
    if not basicinfoform.is_valid(): # Bad user! Give me the contact/basics!!!
        return render(request, "form_crispy.html", {
            'formset': basicinfoform,
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
                    contact = basicinfoform.cleaned_data.get('contact'),
                    org = basicinfoform.cleaned_data.get('billing'),
                    ip = request.META['REMOTE_ADDR']
                ))
            # after thats done
            context['result'] = out
            return render(request, "form_crispy_bulk_projection_done.html", context)

        else:
            context['form'] = filled
            return render(request, "form_crispy.html", context)
    else:
        #pass back the empty form
        context['msg'] = "Bulk Movie Addition - Choose Movie Details"
        context['formset'] = formset(initial=weeks)
        context['helper'] = DateEntryFormSetBase().helper
        context['helper'].add_input(Submit('submit', 'Submit'))

        return render(request, "form_crispy.html", context)
