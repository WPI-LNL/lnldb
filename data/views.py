import mimetypes

import re
import stat
from django.utils.http import http_date, urlquote_plus
from django.views.static import was_modified_since
import os
from django.conf import settings
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect, FileResponse, HttpResponseNotModified
from django.shortcuts import render
from django.contrib.auth.decorators import login_required, permission_required
from django.utils.datastructures import MultiValueDictKeyError
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

from data.models import StupidCat


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
@permission_required('events.view_debug_info', raise_exception=True)
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
### TODO: adjust for perm test
def search(request):
    context = {}
    q = ""
    try:
        if request.POST:
            q = request.POST['q']
        else:
            q = request.GET['q']
    except MultiValueDictKeyError:
        pass
    context['query'] = q
    context['search_entry_list'] = watson.search(q)
    return render(request, 'search.html', context)


def serve_file(request, att_file, forced_name=None):
    statobj = os.stat(att_file.path)
    if not was_modified_since(request.META.get('HTTP_IF_MODIFIED_SINCE'),
                              statobj.st_mtime, statobj.st_size):
        return HttpResponseNotModified()
    content_type, encoding = mimetypes.guess_type(att_file.path)
    content_type = content_type or 'application/octet-stream'
    response = FileResponse(att_file, content_type=content_type)
    response["Last-Modified"] = http_date(statobj.st_mtime)
    if stat.S_ISREG(statobj.st_mode):
        response["Content-Length"] = statobj.st_size
    if encoding:
        response["Content-Encoding"] = encoding
    name = forced_name or att_file.name
    name = name.split('/')[-1]
    response["Content-Disposition"] = 'attachment; filename="%s"; filename*=UTF-8\'\'%s' % \
                                      (str(name).replace('"', ''), urlquote_plus(name))
    return response


def err403(request, *args, **kwargs):
    context = {}
    return render(request, '403.html', context)


def err404(request, *args, **kwargs):
    context = {}
    return render(request, '404.html', context)


def err500(request, *args, **kwargs):
    context = {}
    return render(request, '500.html', context)
