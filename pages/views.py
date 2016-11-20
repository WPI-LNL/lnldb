from django.shortcuts import render, get_object_or_404

from pages.models import Page
from processors import navs


def page(request, slug):
    context = {}
    page_obj = get_object_or_404(Page, slug=slug)
    nav = navs(request)
    context['page'] = page_obj
    # the processors are on crack :-\
    context['navs'] = nav
    return render(request, 'static_page.html', context, )
    # context_instance=context)
