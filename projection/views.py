# Create your views here.
from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response, get_object_or_404
from django.template import Context,RequestContext

from django.contrib.auth.models import User

from django.views.generic.edit import UpdateView
from django.views.generic.edit import CreateView

from projection.models import Projectionist
from projection.forms import ProjectionistUpdateForm
from projection.forms import ProjectionistForm

from django.contrib.auth.decorators import permission_required
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages

from helpers.challenges import is_officer
from helpers.mixins import LoginRequiredMixin, OfficerMixin

@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING')
def plist(request):
    
    context = RequestContext(request)
    users = User.objects.filter(projectionist__pit_level__isnull=False)
    
    context['users'] = users
    context['h2'] = "Projectionist List"
    
    return render_to_response('projectionlist.html', context)



class ProjectionUpdate(OfficerMixin,LoginRequiredMixin,UpdateView):
    model = Projectionist
    template_name = "form_crispy_cbv.html"
    form_class = ProjectionistUpdateForm
    slug_field = 'pk'
    #success_url = reverse("projection-list")
    success_url = "/lnadmin/projection/list"
    
class ProjectionCreate(OfficerMixin,LoginRequiredMixin,CreateView):
    model = Projectionist
    template_name = "form_crispy_cbv.html"
    form_class = ProjectionistForm
    #success_url = reverse("projection-list")
    success_url = "/lnadmin/projection/list"
    