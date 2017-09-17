import mimetypes
import os
import stat

from django.contrib.auth.decorators import login_required
from django.http import FileResponse, HttpResponseNotModified
from django.shortcuts import render
from django.utils.datastructures import MultiValueDictKeyError
from django.utils.http import http_date, urlquote_plus
from django.views.static import was_modified_since
from watson import search as watson


@login_required
# TODO: adjust for perm test
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
    return render(request, '403.html', context, status=403)


def err404(request, *args, **kwargs):
    context = {}
    return render(request, '404.html', context, status=404)


def err500(request, *args, **kwargs):
    context = {}
    return render(request, '500.html', context, status=500)
