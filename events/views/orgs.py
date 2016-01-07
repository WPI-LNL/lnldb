# Create your views here.

import datetime

import pytz
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.core.urlresolvers import reverse
from django.db.models import Count
from django.http import HttpResponse, HttpResponseRedirect, Http404
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.views.generic import CreateView

from events.forms import IOrgForm, ExternalOrgUpdateForm, OrgXFerForm, IOrgVerificationForm, FopalForm
from events.models import Organization, OrganizationTransfer, OrgBillingVerificationEvent, Fund, Event
from helpers.mixins import LoginRequiredMixin, SetFormMsgMixin, HasPermMixin

# so that we can know to send Email
from django.conf import settings
from emails.generators import generate_transfer_email

### ORGANIZATION VIEWS


@login_required
@permission_required('events.view_org', raise_exception=True)
def vieworgs(request):
    """ Views all organizations, """
    # todo add filters
    context = {}

    orgs = Organization.objects \
        .filter(archived=False) \
        .annotate(fund_count=Count('accounts')) \
        .select_related('user_in_charge__first_name',
                        'user_in_charge__last_name',
                        'user_in_charge__username', ).all()

    context['orgs'] = orgs

    return render(request, 'orgs.html', context)


@login_required
### TODO: edit form with perm logic
def addeditorgs(request, id=None):
    """form for adding an org """
    # need to fix this
    context = {}
    edit_perms = ('events.edit_org',)
    mk_perms = ('events.add_org',)
    if id:
        instance = get_object_or_404(Organization, pk=id)
        msg = "Edit Client"
        if not (request.user.has_perms(edit_perms) or
                request.user.has_perms(edit_perms, instance)):
            raise PermissionDenied
    else:
        instance = None
        msg = "New Client"
        if not request.user.has_perms(edit_perms):
            raise PermissionDenied

    if request.method == 'POST':
        formset = IOrgForm(request.POST, instance=instance)
        if formset.is_valid():
            org = formset.save()
            messages.add_message(request, messages.SUCCESS, 'Changes saved.')
            # return HttpResponseRedirect(reverse('events.views.admin', kwargs={'msg':SUCCESS_MSG_ORG}))
            return HttpResponseRedirect(reverse('events.views.orgs.orgdetail', kwargs={'id': org.pk}))
        else:
            context['formset'] = formset
            messages.add_message(request, messages.WARNING, 'Invalid Data. Please try again.')
    else:
        formset = IOrgForm(instance=instance)
        context['formset'] = formset

    context['msg'] = msg

    return render(request, 'form_crispy.html', context)


@login_required
def fund_edit(request, id=None, org=None):
    """form for adding an fund """
    # need to fix this
    context = {}
    edit_perms = ('events.modify_fund',)
    mk_perms = ('events.add_fund',)
    if id:
        instance = get_object_or_404(Fund, pk=id)
        msg = "Edit Fund"
        if not (request.user.has_perms(edit_perms) or
                request.user.has_perms(edit_perms, instance)):
            raise PermissionDenied
    else:
        instance = None
        msg = "New Fund"
        if not request.user.has_perms(mk_perms):
            raise PermissionDenied

    if request.method == 'POST':
        formset = FopalForm(request.POST, instance=instance)
        if formset.is_valid():
            instance = formset.save()
            messages.add_message(request, messages.SUCCESS, 'Changes saved.')
            if org:
                try:
                    org_instance = Organization.objects.get(pk=org)
                    org_instance.accounts.add(instance)
                    return HttpResponseRedirect(reverse('events.views.orgs.orgdetail', args=(org,)))
                except ObjectDoesNotExist:
                    messages.add_message(request, messages.ERROR, 'Failed to add fund to organization.')
            # return HttpResponseRedirect(reverse('events.views.admin', kwargs={'msg':SUCCESS_MSG_ORG}))
            return HttpResponseRedirect(reverse('events.views.orgs.vieworgs'))
        else:
            context['formset'] = formset
            messages.add_message(request, messages.WARNING, 'Invalid Data. Please try again.')
    else:
        formset = FopalForm(instance=instance)
        context['formset'] = formset

    context['msg'] = msg

    return render(request, 'form_crispy.html', context)


@login_required
def orgdetail(request, id):
    context = {}
    perms = ('events.view_org',)
    try:
        org = Organization.objects.prefetch_related('accounts', 'associated_users').get(pk=id)
    except (Organization.DoesNotExist, Organization.MultipleObjectsReturned):
        raise Http404('No Organization matches the given query.')
    context['events'] = Event.objects.filter(org=org).prefetch_related('hours__user', 'ccinstances__crew_chief',
                                                                       'location', 'org')
    if not (request.user.has_perms(perms) or
            request.user.has_perms(perms, org)):
        raise PermissionDenied
    context['org'] = org
    return render(request, 'org_detail.html', context)


### External Form Editing Views (NOW DEPRECATED!)
@login_required
def orglist(request):
    context = {}
    orgs = Organization.objects.filter(user_in_charge=request.user)
    context['orgs'] = orgs

    return render(request, 'myorgsincharge.html', context)


@login_required
def orgedit(request, id):
    context = {}
    orgs = Organization.objects.filter(user_in_charge=request.user)

    org = get_object_or_404(orgs, pk=id)
    msg = "> Modify Organization"
    context['msg'] = msg

    if request.method == 'POST':
        formset = ExternalOrgUpdateForm(request.POST, instance=org)
        if formset.is_valid():
            formset.save()
            # return HttpResponseRedirect(reverse('events.views.admin', kwargs={'msg':SUCCESS_MSG_ORG}))
            return HttpResponseRedirect(reverse('events.views.orgs.orglist'))

        else:
            context['formset'] = formset
    else:

        formset = ExternalOrgUpdateForm(instance=org)

        context['formset'] = formset

    return render(request, 'mycrispy.html', context)


### Transfer Views
@login_required
def org_mkxfer(request, id):
    context = {}

    orgs = Organization.objects.filter(user_in_charge=request.user)
    org = get_object_or_404(orgs, pk=id)

    context['msg'] = 'Orgs: <a href="%s">%s</a> &middot; Transfer Ownership' % (
        reverse("my-orgs-incharge-edit", args=(org.id,)), org.name)

    user = request.user

    now = timezone.now()
    wfn = now + datetime.timedelta(days=7)
    #
    # OrganizationTransfer.objects.filter(old_user_in_charge=

    if request.method == "POST":
        formset = OrgXFerForm(org, user, request.POST)
        if formset.is_valid():
            f = formset.save(commit=False)
            f.old_user_in_charge = user
            f.org = org
            f.created = now
            f.expiry = wfn
            f.save()
            if settings.SEND_EMAIL_ORG_TRANSFER:
                generate_transfer_email(f)
            else:
                pass
            return HttpResponse('k')

    else:
        formset = OrgXFerForm(org, user)
        context['formset'] = formset

    return render(request, 'mycrispy.html', context)


@login_required
def org_acceptxfer(request, idstr):
    context = {}
    transfer = get_object_or_404(OrganizationTransfer, uuid=idstr)

    if transfer.completed:
        context['msg'] = 'This transfer has been completed'
        context['status'] = 'Already Completed'
        context['msgclass'] = "alert-info"

    if transfer.is_expired:
        context['msg'] = 'This transfer has expired, please make a new one (you had a week :-\)'
        context['status'] = 'Expired'

    if request.user == transfer.old_user_in_charge:
        transfer.org.user_in_charge = transfer.new_user_in_charge
        transfer.org.save()
        transfer.completed_on = datetime.datetime.now(pytz.utc)
        transfer.completed = True
        transfer.save()
        context['msg'] = 'Transfer Complete: %s is the new user in charge!' % transfer.new_user_in_charge
        context['status'] = 'Success'
        context['msgclass'] = 'alert-success'
    else:
        context['msg'] = "This isn\'t your transfer"
        context['status'] = 'Not Yours.'
        context['msgclass'] = "alert-error"

    return render(request, 'mytransfer.html', context)


class OrgVerificationCreate(SetFormMsgMixin, HasPermMixin, LoginRequiredMixin, CreateView):
    model = OrgBillingVerificationEvent
    form_class = IOrgVerificationForm
    template_name = "form_crispy_cbv.html"
    msg = "Mark Client billing as valid"
    perms = ('events.verify_org',)

    def get_form_kwargs(self):
        kwargs = super(OrgVerificationCreate, self).get_form_kwargs()
        org = get_object_or_404(Organization, pk=self.kwargs['org'])
        kwargs['org'] = org
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Org Marked as Validated", extra_tags='success')
        return super(OrgVerificationCreate, self).form_valid(form)

    def get_success_url(self):
        return reverse("admin-orgdetail", args=(self.kwargs['org'],))