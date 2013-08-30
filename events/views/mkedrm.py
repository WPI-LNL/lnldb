from events.models import Event
from events.forms import InternalEventForm as IEF

from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response, get_object_or_404
from django.template import Context,RequestContext

@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING/')
def eventnew(request,id=None):
    context = RequestContext(request)
    
    #get instance if id is passed in
    if id:
        instance = get_object_or_404(Chore,pk = id)
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
            res = form.save()
            return HttpResponseRedirect(reverse('events.views.list.viewevent',args=(res.id,)))
            #return HttpResponseRedirect(reverse('house.views.chores.choredetail',kwargs={'id':res.id}))
        else:
            context['formset'] = form
    else:
        form = IEF(instance=instance)
        if instance:
            context['msg'] = "Edit Event"
        else:
            context['msg'] = "New Event"
        context['formset'] = form
    
    return render_to_response('form_crispy.html', context)