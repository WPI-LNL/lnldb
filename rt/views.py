from django.shortcuts import render, reverse
from django.http import HttpResponseRedirect
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from cryptography.fernet import Fernet

from accounts.models import UserPreferences
from slack.api import lookup_user, slack_post
from slack.views import tfed_ticket
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
                ticket_id = resp['id']
                messages.success(request, "Your ticket has been submitted. Thank you!")

                # Send Slack notification
                slack_user = lookup_user(request.user.email)
                ticket_info = {
                    "url": 'https://lnl-rt.wpi.edu/rt/Ticket/Display.html?id=' + ticket_id,
                    "id": ticket_id,
                    "subject": subject,
                    "description": request.POST['description'],
                    "status": "New",
                    "assignee": None,
                    "reporter": slack_user
                }
                ticket = tfed_ticket(ticket_info)
                slack_post(settings.SLACK_TARGET_TFED_DB, text=request.POST['description'], content=ticket,
                           username='Request Tracker')
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
    """ Walks the user through connecting their RT account to their LNLDB account """

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
        # If the user hasn't yet agreed to the requested scopes, send them there first
        if reverse("accounts:scope-request") not in request.META.get('HTTP_REFERER', ''):
            request.session["app"] = "LNLDB"
            request.session["resource"] = "RT"
            request.session["icon"] = "https://lnl-rt.wpi.edu/rt/NoAuth/Helpers/CustomLogo/dd63008602de45a7b45597a4d43a7aad"
            request.session["scopes"] = ["View your profile", "Manage tickets on your behalf"]
            request.session["callback_uri"] = "support:link-account"
            request.session["inverted"] = True
            return HttpResponseRedirect(reverse("accounts:scope-request"))

        form = forms.AuthTokenForm()
    context['form'] = form
    return render(request, 'form_semanticui.html', context)
