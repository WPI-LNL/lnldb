from data.models import StupidCat

from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response
from django.template import Context,RequestContext

from django.contrib.auth.decorators import login_required, user_passes_test
from helpers.challenges import is_officer

from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

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


@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING/')
def access_log(request):
    context = RequestContext(request)
    
    entries = StupidCat.objects.all()
    paginator = Paginator(entries, 50)
    
    page = request.GET.get('page')
    
    try:
        accesses = paginator.page(page)
    except PageNotAnInteger:
        # If page is not an integer, deliver first page.
        accesses = paginator.page(1)
    except EmptyPage:
        # If page is out of range (e.g. 9999), deliver last page of results.
        accesses = paginator.page(paginator.num_pages)
        
    context['accesses'] = accesses
    return render_to_response('access_log.html', context)
