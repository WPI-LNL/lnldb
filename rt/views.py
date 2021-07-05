import requests
import filetype
from django.shortcuts import render, reverse
from django.http import HttpResponseRedirect
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from base64 import b64encode
from . import forms


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
            resp = create_ticket("Database", request.user.email, subject, description, attachments=attachments)
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
    return render(request, 'helpdesk_form.html', context)


# API Methods
def api_request(method, endpoint, data=None):
    """
    Send an API request to the RT server

    :param method: `GET`, `POST`, `PUT`, or `DELETE`
    :param endpoint: RT endpoint
    :param data: JSON data (if applicable)
    :return: Response
    """
    host = 'https://lnl-rt.wpi.edu/rt/REST/2.0/'
    headers = {"Content-Type": "application/json", "Authorization": "token " + settings.RT_TOKEN}
    if method.lower() == 'get':
        response = requests.get(host + endpoint, headers=headers)
        if response.status_code != 500:
            return response.json()
        return {"message": "An unknown error occurred"}
    elif method.lower() == 'post':
        if data:
            response = requests.post(host + endpoint, json=data, headers=headers)
            if response.status_code != 500:
                return response.json()
            return {"message": "An unknown error occurred"}
        return {"message": "Bad request"}


def create_ticket(queue, reporter, subject, content, html=False, cc=None, attachments=None):
    """
    Create a new ticket in RT

    :param queue: The ticket queue to send the ticket to
    :param reporter: Email address of the user submitting the ticket
    :param subject: Brief subject line for quick reference
    :param content: The contents of the ticket
    :param html: If true, will set ContentType to text/html instead of text/plain
    :param cc: List of additional email addresses to include in the ticket [Optional]
    :param attachments: A list of attachments to include [Optional]
    :return: API response
    """
    endpoint = 'ticket'
    payload = {
        "Subject": subject,
        "Queue": queue,
        "Requestor": reporter,
        "Content": content,
        "ContentType": "text/plain"
    }
    if cc:
        payload["Cc"] = ','.join(cc)
    if html:
        payload["ContentType"] = "text/html"
    if attachments:
        files = []
        for attachment in attachments:
            ft = filetype.guess(attachment)
            if ft:
                mime_type = ft.mime
            else:
                mime_type = "application/octet-stream"
            attachment.seek(0)
            file_contents = b64encode(attachment.read()).decode('utf-8')
            files.append({"FileName": attachment.name, "FileType": mime_type, "FileContent": file_contents})
        payload["Attachments"] = files
    return api_request('POST', endpoint, payload)
