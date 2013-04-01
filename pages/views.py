from pages.models import Page

from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response, get_object_or_404
from django.template import Context,RequestContext

from processors import navs

# Create your views here.

def page(request,slug):
    context = RequestContext(request)
    page = get_object_or_404(Page,slug=slug)
    nav = navs(request)
    context['page'] = page
    #the processors are on crack :-\
    context['navs'] = nav
    
    return render_to_response('static_page.html', context,) #context_instance=context)