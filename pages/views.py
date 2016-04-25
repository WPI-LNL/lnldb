from pages.models import Page

from django.shortcuts import render, get_object_or_404
from django.template import RequestContext

from processors import navs

# Create your views here.


def page(request, slug):
    context = {}
    page_obj = get_object_or_404(Page, slug=slug)
    nav = navs(request)
    context['page'] = page_obj
    # the processors are on crack :-\
    context['navs'] = nav
    return render(request, 'static_page.html', context, )
    # context_instance=context)
