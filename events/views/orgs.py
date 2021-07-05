# Create your views here.

import datetime

import pytz
# so that we can know to send Email
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls.base import reverse
from django.utils import timezone
from django.views.generic import CreateView
from reversion.models import Version
import reversion

from emails.generators import generate_transfer_email
from events.forms import (ExternalOrgUpdateForm, IOrgForm, IOrgVerificationForm, OrgXFerForm)
from events.models import (BaseEvent, Organization, OrganizationTransfer, OrgBillingVerificationEvent)
from helpers.mixins import HasPermMixin, LoginRequiredMixin, SetFormMsgMixin
from helpers.revision import set_revision_comment


# ORGANIZATION VIEWS


@login_required
@permission_required('events.view_org', raise_exception=True)
def vieworgs(request):
    """ Lists all organizations """
    # todo add filters
    context = {}

    orgs = Organization.objects \
        .filter(archived=False) \
        .select_related('user_in_charge').all()

    context['orgs'] = orgs

    return render(request, 'orgs.html', context)


@login_required
def addeditorgs(request, org_id=None):
    """
    internal form for adding/editing an org
    Clients should not have access to this page. The accounts field autocomplete exposes ALL funds,
    and this form also allows the owner of the org to be changed without the email verification done
    by the org transfer form. Clients should use the much less confusing 'orgedit' view.
    """
    if not request.user.has_perm('events.view_org'):
        raise PermissionDenied
    context = {}
    if org_id:
        instance = get_object_or_404(Organization, pk=org_id)
        msg = "Edit Client"
        if not request.user.has_perm('events.edit_org'):
            raise PermissionDenied
    else:
        instance = None
        msg = "New Client"
        if not request.user.has_perm('events.list_org_members') \
                or not request.user.has_perm('events.transfer_org_ownership'):
            raise PermissionDenied

    if request.method == 'POST':
        form = IOrgForm(request.user, request.POST, instance=instance)
        if form.is_valid():
            if instance:
                set_revision_comment('Edited', form)
            else:
                set_revision_comment('Created client', None)
            org = form.save()
            messages.add_message(request, messages.SUCCESS, 'Changes saved.')
            # return HttpResponseRedirect(reverse("home", kwargs={'msg':SUCCESS_MSG_ORG}))
            return HttpResponseRedirect(reverse('orgs:detail', kwargs={'org_id': org.pk}))
        else:
            context['form'] = form
            messages.add_message(request, messages.WARNING, 'Invalid Data. Please try again.')
    else:
        form = IOrgForm(request.user, instance=instance)
        context['form'] = form

    context['msg'] = msg

    return render(request, 'form_crispy.html', context)


@login_required
def orgdetail(request, org_id):
    """ Organization detail page """
    context = {}
    perms = ('events.view_org',)
    try:
        org = Organization.objects.prefetch_related('associated_users').get(pk=org_id)
    except (Organization.DoesNotExist, Organization.MultipleObjectsReturned):
        raise Http404('No Organization matches the given query.')
    if not (request.user.has_perms(perms) or
            request.user.has_perms(perms, org)):
        raise PermissionDenied
    context['org'] = org
    context['history'] = Version.objects.get_for_object(org)
    context['events'] = BaseEvent.objects.filter(org=org).prefetch_related('hours__user', 'ccinstances__crew_chief',
                                                                           'location', 'org')
    return render(request, 'org_detail.html', context)


# External Form Editing Views (NOW DEPRECATED!)
# @login_required
# def orglist(request):
#     context = {}
#     orgs = Organization.objects.filter(user_in_charge=request.user)
#     context['orgs'] = orgs
#
#     return render(request, 'myorgsincharge.html', context)
#
#
@login_required
def orgedit(request, id):
    """ Form for editing organization details (client view) """
    context = {}
    if request.user.is_superuser:
        orgs = Organization.objects.all()
    else:
        orgs = Organization.objects.filter(user_in_charge=request.user)

    org = get_object_or_404(orgs, pk=id)
    msg = "> Modify Organization"
    context['msg'] = msg

    if request.method == 'POST':
        formset = ExternalOrgUpdateForm(request.POST, instance=org)
        if formset.is_valid():
            set_revision_comment('Edited', formset)
            formset.save()
            return HttpResponseRedirect(reverse('orgs:detail', args=(org.pk,)))
    else:
        formset = ExternalOrgUpdateForm(instance=org)

    context['formset'] = formset

    return render(request, 'mycrispy.html', context)


# Transfer Views
@login_required
def org_mkxfer(request, id):
    """ Begin the process of transferring ownership of an organization """
    context = {}
    org = get_object_or_404(Organization, pk=id)
    if not request.user.has_perm('events.transfer_org_ownership', org):
        raise PermissionDenied
    context['msg'] = 'Orgs: <a href="%s">%s</a> &middot; Transfer Ownership' % (
        reverse("orgs:detail", args=(org.id,)), org.name)
    user = request.user
    now = timezone.now()
    wfn = now + datetime.timedelta(days=7)

    if request.method == "POST":
        form = OrgXFerForm(org, user, request.POST)
        if form.is_valid():
            f = form.save(commit=False)
            f.expiry = wfn
            f.save()
            if settings.SEND_EMAIL_ORG_TRANSFER:
                email = generate_transfer_email(f)
                email.send()
            if email:
                messages.add_message(request, messages.SUCCESS, 'Created transfer request. To complete \
                the transfer, you must use the link that was just emailed to ' + ', '.join(email.to))
            else:
                messages.add_message(request, messages.SUCCESS, 'Created transfer request. To complete \
                the transfer, you must use the link that was just emailed.')
            return HttpResponseRedirect(reverse("orgs:detail", args=(org.id,)))

    else:
        form = OrgXFerForm(org, user)
        context['formset'] = form

    return render(request, 'mycrispy.html', context)


def org_acceptxfer(request, idstr):
    """ Complete an organization transfer """
    context = {}
    transfer = get_object_or_404(OrganizationTransfer, uuid=idstr)

    if transfer.completed:
        context['msg'] = 'This transfer has been completed'
        context['status'] = 'Already Completed'
        context['msgclass'] = "alert-info"

    elif transfer.is_expired:
        context['msg'] = 'This transfer has expired, please make a new one (you had a week :-\)'
        context['status'] = 'Expired'

    else:
        with reversion.create_revision():
            reversion.set_user(transfer.initiator)
            set_revision_comment('Transferred owner from {} to {}'.format(
                transfer.org.user_in_charge, transfer.new_user_in_charge), None)
            transfer.org.user_in_charge = transfer.new_user_in_charge
            transfer.org.save()
        transfer.completed_on = datetime.datetime.now(pytz.utc)
        transfer.completed = True
        transfer.save()
        context['msg'] = 'Transfer Complete: %s is the new user in charge!' % transfer.new_user_in_charge
        context['status'] = 'Success'
        context['msgclass'] = 'alert-success'

    return render(request, 'mytransfer.html', context)


class OrgVerificationCreate(SetFormMsgMixin, HasPermMixin, LoginRequiredMixin, CreateView):
    """ Verify that a client's billing details are valid """
    model = OrgBillingVerificationEvent
    form_class = IOrgVerificationForm
    template_name = "form_crispy_cbv.html"
    msg = "Mark Client billing as valid"
    perms = ('events.create_verifications',)

    def get_form_kwargs(self):
        kwargs = super(OrgVerificationCreate, self).get_form_kwargs()
        org = get_object_or_404(Organization, pk=self.kwargs['org_id'])
        kwargs['org'] = org
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Org Marked as Validated", extra_tags='success')
        return super(OrgVerificationCreate, self).form_valid(form)

    def get_success_url(self):
        return reverse("orgs:detail", args=(self.kwargs['org_id'],))
