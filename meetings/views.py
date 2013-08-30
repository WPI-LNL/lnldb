# Create your views here.

from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response, get_object_or_404
from django.template import Context,RequestContext

from meetings.forms import MeetingAdditionForm as MAF
from meetings.models import Meeting

from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

from django.contrib.auth.decorators import permission_required
from django.contrib.auth.decorators import login_required, user_passes_test
from helpers.challenges import is_officer



@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING/')
def viewattendance(request,id):
    context = RequestContext(request)
    m = get_object_or_404(Meeting,pk=id)
    context['m'] = m
    return render_to_response('meeting_view.html', context)

@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING/')
def editattendance(request,id):
    context = RequestContext(request)
    context['msg'] = "Edit Meeting"
    m = get_object_or_404(Meeting,pk=id)
    if request.method == 'POST':
        formset = MAF(request.POST,instance=m)
        if formset.is_valid():
            m = formset.save()
            return HttpResponseRedirect(reverse('meetings.views.viewattendance',args=(m.id,)))
        else:
            context['formset'] = formset
    else:
        formset = MAF(instance=m)
    return render_to_response('form_crispy.html', context)
        
@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING/')
def listattendance(request,page=1):
    context = RequestContext(request)
    attend = Meeting.objects.all()
    paginated = Paginator(attend,10)

    try:
        attend = paginated.page(page)
    except:
        attend = paginated.page(1)
        
    context['attend'] = attend
    return render_to_response('meeting_list.html', context)
        
@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING/')
def newattendance(request):
    context = RequestContext(request)
    if request.method == 'POST':
        formset = MAF(request.POST)
        if formset.is_valid():
            m = formset.save()
            return HttpResponseRedirect(reverse('meetings.views.viewattendance',args=(m.id,)))
    else:
        formset = MAF()
        context['formset'] = formset
        context['msg'] = "New Meeting"
        return render_to_response('form_crispy.html', context)


@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING/')
def sendnotice(request,id):
    pass

    # create form to customize 