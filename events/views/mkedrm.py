from events.models import Event
from events.forms import InternalEventForm as IEF

from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response, get_object_or_404
from django.template import Context,RequestContext

from django.contrib.auth.decorators import permission_required
from django.contrib.auth.decorators import login_required, user_passes_test
from helpers.challenges import is_officer

from raven.contrib.django.raven_compat.models import client

@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING/')
def eventnew(request,id=None):
    context = RequestContext(request)
    
    #get instance if id is passed in
    if id:
        instance = get_object_or_404(Event,pk = id)
        context['new'] = False
    else:
        instance = None
        context['new'] = True
        
    
    if request.method == 'POST':
        form = IEF(
            request.POST,
            instance = instance
        )
        
        if form.is_valid():
            if instance:
                res = form.save()
            else:
                res = form.save(commit=False)
                res.submitted_by = request.user
                res.submitted_ip = request.META.get('REMOTE_ADDR')
                res.save()
                form.save_m2m()
            return HttpResponseRedirect(reverse('events.views.flow.viewevent',args=(res.id,)))
        else:
            context['e'] = form.errors
            context['formset'] = form
    else:
        form = IEF(instance=instance)
        if instance:
            context['msg'] = "Edit Event"
        else:
            context['msg'] = "New Event"
        context['formset'] = form
    
    return render_to_response('form_crispy.html', context)