from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render

from events.forms import InternalEventForm
from events.models import Event


@login_required
# TODO: rework form for perm logic.
def eventnew(request, id=None):
    context = {}
    edit_perms = ('events.view_event',)
    # mk_perms = ('events.add_raw_event',)
    # get instance if id is passed in
    if id:
        instance = get_object_or_404(Event, pk=id)
        context['new'] = False
        if not (request.user.has_perms(edit_perms) or
                request.user.has_perms(edit_perms, instance)):
            raise PermissionDenied
    else:
        instance = None
        context['new'] = True
        if not request.user.has_perms(edit_perms):
            raise PermissionDenied

    if request.method == 'POST':
        form = InternalEventForm(
            data=request.POST,
            request_user=request.user,
            instance=instance
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
            return HttpResponseRedirect(reverse('events:detail', args=(res.id,)))
        else:
            context['e'] = form.errors
            context['formset'] = form
    else:
        form = InternalEventForm(request_user=request.user,
                                 instance=instance)
        if instance:
            context['msg'] = "Edit Event"
        else:
            context['msg'] = "New Event"
        context['formset'] = form

    return render(request, 'form_crispy.html', context)
