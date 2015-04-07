import re
import os
from data.models import StupidCat
from django.conf import settings

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
def status(request):
    context = {}
    try:
        # want to keep the git revision stuff on one page ONLY, so I'll stick it all here.
        git_change_file = open(os.path.join(settings.SITE_ROOT, '.git', 'COMMIT_EDITMSG'))
        context['CHANGELOG'] = "\n".join(git_change_file.readlines())
        git_change_file.close()

        git_hash_file = open(os.path.join(settings.SITE_ROOT, '.git', 'HEAD'))
        git_hash_text = '\n'.join(git_hash_file.readlines())
        git_hash_file.close()
        while 'ref:' in git_hash_text:
            follow_path = re.search('^ref: (.+)$', git_hash_text).group(1)
            followed_file = open(os.path.join(settings.SITE_ROOT, '.git', follow_path))
            git_hash_text = "\n".join(followed_file.readlines())
            followed_file.close()
        context['REVISION'] = git_hash_text[:6]
    except:
        pass

    return render(request, 'status_page.html', context)


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
