from data.models import StupidCat

from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response
from django.template import Context,RequestContext
from django.contrib.auth.decorators import login_required
# Create your views here.

@login_required
def fuckoffkitty(request):
    if request.GET.__contains__('next'):
        requested_uri = request.GET['next']
        StupidCat.objects.create(
            user = request.user,
            user_ip = request.META['REMOTE_ADDR'],
            requested_uri = requested_uri
        )
        return HttpResponseRedirect(reverse('data.views.fuckoffkitty'))
    else:
        context = RequestContext(request)
        kitty = StupidCat.objects.filter(user=request.user).latest()
        context['kitty'] = kitty
        context['foo'] = 'foo'
        
        return render_to_response('kitty.html', context)
        
    
    return HttpResponse(requested_uri)