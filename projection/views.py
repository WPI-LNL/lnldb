# Create your views here.
from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response, get_object_or_404
from django.template import Context,RequestContext

from django.contrib.auth.models import User

def plist(request):
    
    context = RequestContext(request)
    users = User.objects.filter(projectionist__pit_level__isnull=False)
    
    context['users'] = users
    context['h2'] = "Projectionist List"
    
    return render_to_response('projectionlist.html', context)