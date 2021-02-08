import datetime

from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_GET

from events.models import BaseEvent
from pages.models import Page
from processors import navs


def page(request, slug):
    """ Generate custom page """
    context = {}
    page_obj = get_object_or_404(Page, slug=slug)
    nav = navs(request)
    context['page'] = page_obj
    context['title'] = page_obj.title
    context['description'] = page_obj.description
    context['styles'] = page_obj.css
    context['noindex'] = page_obj.noindex
    # the processors are on crack :-\
    context['navs'] = nav
    return render(request, 'static_page.html', context, )
    # context_instance=context)


@require_GET
def recruitment_page(request):
    """ Serve LNL's join page with list of upcoming or ongoing events """
    now = timezone.now()
    five_days_from_now = now + datetime.timedelta(days=5)
    events = BaseEvent.objects\
        .filter(approved=True, cancelled=False, sensitive=False, test_event=False, closed=False)\
        .filter(datetime_end__gte=now, ccinstances__setup_start__lte=five_days_from_now)\
        .order_by('datetime_start').distinct()
    return render(request, 'recruitment.html', {'events': events})
