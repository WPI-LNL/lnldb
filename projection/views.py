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

    users = Projectionist.objects .select_related(
        'user__first_name', 'user__last_name', 'user__username')

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
        form = ProjectionistUpdateForm(
            request.POST, instance=projectionist, prefix="main")
        formset = PITFormset(
            request.POST,
            instance=projectionist,
            prefix="nested")
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


# Non-Wizard Projection Bulk View
@login_required
@permission_required('projection.add_bulk_events', raise_exception=True)
def bulk_projection(request):
    context = {}
    tz = timezone.get_current_timezone()

    if request.GET:
        # always build the formset
        formbulk = BulkCreateForm(request.GET)
        if formbulk.is_valid():
            # create our new form and pass it back
            date_1 = formbulk.cleaned_data.get('date_first')
            date_2 = formbulk.cleaned_data.get('date_second')
            # date_1 = datetime.datetime.strptime(datestr_1,"%Y-%m-%d")
            #date_2 = datetime.datetime.strptime(datestr_2,"%Y-%m-%d")

            end_of_term_1 = date_1 + datetime.timedelta(days=56)
            end_of_term_2 = date_2 + datetime.timedelta(days=66)

            range_1 = []
            iterator_1 = date_1
            while iterator_1 <= end_of_term_1:
                if iterator_1.weekday() in [5, 6]:
                    range_1.append(iterator_1)

                iterator_1 = iterator_1 + datetime.timedelta(days=1)

            range_2 = []
            iterator_2 = date_2
            while iterator_2 <= end_of_term_2:
                if iterator_2.weekday() in [5, 6]:
                    range_2.append(iterator_2)

                iterator_2 = iterator_2 + datetime.timedelta(days=1)

            ranges_combined = range_1 + range_2

            # prepopulate things
            out = []
            for i in ranges_combined:
                out.append({"date": i})

            formset = formset_factory(DateEntryFormSetBase, extra=0)
            form_params = formset(initial=out)
            context['form'] = form_params

            # depending on the return, do other things.
            if request.POST:
                # here we have our params and data
                filled = formset(request.POST, initial=out)
                if filled.is_valid():
                    out = []
                    for form in filled.cleaned_data:
                        kwargs = {}  # this is super nice
                        date = form['date']
                        name = form['name']
                        matinee = form['matinee']

                        # only populate db entries if the name has been filled
                        if name:
                            # first lets hammer out some details

                            kwargs['event_name'] = name
                            # get stuff from our bulk create form...
                            contact = formbulk.cleaned_data.get('contact')
                            kwargs['contact'] = contact

                            billing = formbulk.cleaned_data.get('billing')
                            # used below in e.add(org)

                            # various other important things
                            kwargs['submitted_by'] = request.user
                            kwargs['submitted_ip'] = request.META[
                                'REMOTE_ADDR']

                            l = Location.objects.filter(name__icontains="Perreault Hall U")[
                                0]  # change to settings later (the u is for upper)
                            kwargs['location'] = l
                            # matinee determines the time
                            if matinee:
                                t_setupcomplete = datetime.time(13, 30)
                                t_starttime = datetime.time(14)
                                t_endtime = datetime.time(17)
                            else:
                                t_setupcomplete = datetime.time(19, 30)
                                t_starttime = datetime.time(20)
                                t_endtime = datetime.time(23)
                            # then we combine our date and time objects, cast
                            # them as EST and stuff them into the kwargs
                            dt_setupcomplete = datetime.datetime.combine(
                                date, t_setupcomplete)
                            dt_setupcomplete = tz.localize(dt_setupcomplete)
                            kwargs['datetime_setup_complete'] = dt_setupcomplete

                            dt_start = datetime.datetime.combine(
                                date, t_starttime)
                            dt_start = tz.localize(dt_start)
                            kwargs['datetime_start'] = dt_start

                            dt_end = datetime.datetime.combine(date, t_endtime)
                            dt_end = tz.localize(dt_end)
                            kwargs['datetime_end'] = dt_end
                            # we'll assume its a digital projection "dp" event
                            # at this point
                            s = ProjService.objects.get(shortname="dp")
                            kwargs['projection'] = s
                            kwargs['billed_by_semester'] = True
                            # return HttpResponse(kwargs.values())

                            # here's where this kwargs assignment pays off.
                            e = Event.objects.create(**kwargs)
                            e.org.add(billing)
                            out.append(e)
                        else:
                            # no blank entries
                            pass
                    # after thats done
                    context['result'] = out
                    return render(
                        request, "form_crispy_bulk_projection_done.html", context)

                else:
                    context['form'] = filled
                    return render(
                        request,
                        "form_crispy_bulk_projection_entries.html",
                        context)
            else:
                # pass back the empty form
                context['msg'] = "Bulk Movie Addition"
                context['formset'] = formbulk

                return render(
                    request,
                    "form_crispy_bulk_projection_entries.html",
                    context)
        else:
            # here we only have our params
            context['msg'] = "Bulk Movie Addition (Errors)"
            context['formset'] = formbulk
            return render(request, "form_crispy.html", context)
    else:
        # here we have nothing
        form = BulkCreateForm()
        context['formset'] = form
        context['msg'] = "Bulk Movie Addition"
        return render(request, "form_crispy.html", context)
