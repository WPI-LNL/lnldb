from django.shortcuts import render, reverse
from django.http import HttpResponseRedirect
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from cryptography.fernet import Fernet

from accounts.models import UserPreferences
from . import forms, api


@login_required
def new_ticket(request):
    """ Form for submitting an RT ticket to the Database queue """
    context = {}
    if request.method == "POST":
        form = forms.TicketSubmissionForm(request.POST)
        if form.is_valid():
            subject = request.POST['subject']
            description = request.POST['description'] + "\n\n-----"
            description += "\nVersion: %s" % settings.GIT_RELEASE[:7]
            description += "\nSubmitted from: %s" % request.META.get('REMOTE_ADDR')
            description += "\nDevice Info: %s" % request.META.get('HTTP_USER_AGENT')
            attachments = request.FILES.getlist('attachments')
            resp = api.create_ticket("Database", request.user.email, subject, description, attachments=attachments)
            if resp.get('id', None):
                messages.success(request, "Your ticket has been submitted. Thank you!")
            else:
                messages.add_message(
                    request, messages.WARNING,
                    'Failed to open ticket: %s. Please contact the Webmaster.' % resp.get('message')
                )
            return HttpResponseRedirect(reverse("home"))
    else:
        form = forms.TicketSubmissionForm()
    context['form'] = form
    context['title'] = 'Submit a Ticket'
    return render(request, 'form_semanticui.html', context)


@login_required
def link_account(request):
    """ Page to use for linking RT account - TODO: Convert this to a POST only url? """
    context = {'title': 'Connect to your RT account'}
    if request.method == 'POST':
        form = forms.AuthTokenForm(request.POST)
        if form.is_valid():
            token = request.POST['token'].encode('utf-8')
            prefs, created = UserPreferences.objects.get_or_create(user=request.user)
            if settings.RT_CRYPTO_KEY:
                cipher_suite = Fernet(settings.RT_CRYPTO_KEY)
                prefs.rt_token = cipher_suite.encrypt(token).decode('utf-8')
                prefs.save()
            else:
                messages.add_message(request, messages.ERROR,
                                     "Security Error: Could not save token. Please contact the Webmaster.")
            return HttpResponseRedirect(reverse("accounts:me"))
    else:
        form = forms.AuthTokenForm()
    context['form'] = form
    return render(request, 'form_semanticui.html', context)

# TODO: Add a permissions page that shows what the RT integration will be able to do
