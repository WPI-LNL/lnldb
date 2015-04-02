from data.models import StupidCat

from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect
from django.shortcuts import render

from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils.datastructures import MultiValueDictKeyError
from helpers.challenges import is_officer

from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

# Create your views here.
import watson


@login_required
def fuckoffkitty(request):
    if request.GET.__contains__('next'):
        requested_uri = request.GET['next']
        StupidCat.objects.create(
            user=request.user,
            user_ip=request.META['REMOTE_ADDR'],
            requested_uri=requested_uri
        )
        return HttpResponseRedirect(reverse('data.views.fuckoffkitty'))
    else:
        context = {}
        kitty = StupidCat.objects.filter(user=request.user).latest()
        context['kitty'] = kitty
        context['foo'] = 'foo'

        return render(request, 'kitty.html', context)


@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING/')
def access_log(request):
    context = {}

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
    return render(request, 'access_log.html', context)


@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING/')
def search(request):
    context = {}
    q = ""
    try:
        if request.POST:
            q = request.POST['q']
        else:
            q = request.GET['q']
    except MultiValueDictKeyError:
        q = ""
    context['query'] = q
    context['search_entry_list'] = watson.search(q)
    return render(request, 'search.html', context)
