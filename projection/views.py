# Create your views here.
from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response, get_object_or_404
from django.template import Context,RequestContext

from django.contrib.auth.models import User

from django.views.generic.edit import UpdateView
from django.views.generic.edit import CreateView
from django.views.generic.edit import FormView


from projection.models import Projectionist,PitInstance,PITLevel
from projection.forms import ProjectionistUpdateForm
from projection.forms import ProjectionistForm
from projection.forms import PITFormset
from projection.forms import BulkUpdateForm

from django.contrib.auth.decorators import permission_required
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages

from helpers.challenges import is_officer
from helpers.mixins import LoginRequiredMixin, OfficerMixin

@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING')
def plist(request):
    
    context = RequestContext(request)
    users = Projectionist.objects.all().order_by('user__last_name')
    
    context['users'] = users
    context['h2'] = "Projectionist List"
    
    return render_to_response('projectionlist.html', context)

def plist_detail(request):
    
    context = RequestContext(request)
    levels = PITLevel.objects.exclude(name_short__in=['PP','L']).order_by('ordering')
    unlicensed_users = Projectionist.objects.exclude(pitinstances__pit_level__name_short__in=['PP','L'])
    licensed_users = Projectionist.objects.filter(pitinstances__pit_level__name_short__in=['PP','L']).exclude(user__groups__name="Alumni")
    alumni_users = Projectionist.objects.filter(pitinstances__pit_level__name_short__in=['PP','L']).filter(user__groups__name="Alumni")
    
    context['unlicensed_users'] = unlicensed_users
    context['licensed_users'] = licensed_users
    context['alumni_users'] = alumni_users
    context['levels'] = levels
    context['h2'] = "Projectionist List Detailed"
    
    return render_to_response('projectionlist_detail.html', context)


def projection_update(request,id):
    projectionist = get_object_or_404(Projectionist,pk=id)
    context = RequestContext(request)
    context['msg'] = "Updating Projectionist %s" % projectionist
    
    if request.method == "POST":
        form = ProjectionistUpdateForm(request.POST,instance=projectionist,prefix="main")
        formset = PITFormset(request.POST,instance=projectionist,prefix="nested")
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            return HttpResponseRedirect(reverse("projection-list"))
        else:
            context['form'] = form
            context['formset'] = formset
    else:
        form = ProjectionistUpdateForm(instance=projectionist,prefix="main")
        formset = PITFormset(instance=projectionist,prefix="nested")
        context['form'] = form
        context['formset'] = formset
        
    return render_to_response('form_crispy_helpers.html',context)
    
       
    
class ProjectionCreate(OfficerMixin,LoginRequiredMixin,CreateView):
    model = Projectionist
    template_name = "form_crispy_cbv.html"
    form_class = ProjectionistForm
    #success_url = reverse("projection-list")
    success_url = "/lnadmin/projection/list"
    
class BulkUpdateView(OfficerMixin,LoginRequiredMixin,FormView):
    template_name = "form_crispy_cbv.html"
    form_class = BulkUpdateForm
    success_url = "/lnadmin/projection/list/"

    def form_valid(self, form):
        # This method is called when valid form data has been POSTed.
        # It should return an HttpResponse.
        form.create_updates()
        return super(BulkUpdateView, self).form_valid(form)    