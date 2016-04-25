from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives

import pytz
import datetime

from events.models import Event

from django.conf import settings

EMAIL_KEY_START_END = settings.EMAIL_KEY_START_END
EMAIL_TARGET_START_END = settings.EMAIL_TARGET_START_END
DEFAULT_TO_ADDR = settings.DEFAULT_TO_ADDR


def generate_notice_email(notice):
    subject = notice.subject
    from_email = settings.DEFAULT_FROM_ADDR
    to_email = notice.email_to.email

    context = {'object': notice}

    cont_html = render_to_string('emails/email_notice.html', context)
    cont_text = render_to_string('emails/email_notice.txt', context)

    email = EmailMultiAlternatives(subject, cont_text, from_email, [to_email])
    email.attach_alternative(cont_html, "text/html")

    return email


def generate_notice_cc_email(notice):
    subject = notice.subject
    from_email = settings.DEFAULT_FROM_ADDR
    to_email = notice.email_to.email

    context = {'object': notice}

    cont_html = render_to_string('emails/email_notice_cc.html', context)
    cont_text = render_to_string('emails/email_notice_cc.txt', context)

    email = EmailMultiAlternatives(subject, cont_text, from_email, [to_email])
    email.attach_alternative(cont_html, "text/html")

    return email


def generate_transfer_email(orgtransfer):
    subject = "LNL Organization Control Transfer for %s" % orgtransfer.org.name
    from_email = settings.DEFAULT_FROM_ADDR
    to_email = "%s@wpi.edu" % orgtransfer.old_user_in_charge.username

    context = {'object': orgtransfer}

    cont_html = render_to_string('emails/email_transfer.html', context)
    cont_text = render_to_string('emails/email_transfer.txt', context)

    email = EmailMultiAlternatives(subject, cont_text, from_email, [to_email])
    email.attach_alternative(cont_html, "text/html")

    return email


def generate_event_start_end_emails():
    subj_start = "Events Starting Now"
    subj_end = "Events Ending Now"
    # get the time
    unstripped = datetime.datetime.now(pytz.utc)
    # get rids of the zeroes
    now = unstripped.replace(second=0, microsecond=0)

    # set the headers for majordomo, may need a : after the Approved
    if EMAIL_KEY_START_END:
        headers = {'Approved': EMAIL_KEY_START_END}
    else:
        headers = None

    # for the start
    starting = Event.objects.filter(approved=True, datetime_start=now)
    ending = Event.objects.filter(approved=True, datetime_end=now)
    # print now
    # print starting.count()
    # print ending.count()

    from_email = settings.DEFAULT_FROM_ADDR

    if starting:
        context_start = {
            'events': starting,
            'string': "Events Starting Now",
            'stringtwo': ""}

        content_start_txt = render_to_string(
            'emails/email_start_end.txt', context_start)
        content_start_html = render_to_string(
            'emails/email_start_end.html', context_start)

        email = EmailMultiAlternatives(
            subj_start,
            content_start_txt,
            from_email,
            [EMAIL_TARGET_START_END],
            headers=headers)
        email.attach_alternative(content_start_html, "text/html")
        email.send()
        # print "sent start email with %s events" % starting.count()

    elif ending:
        context_end = {
            'events': ending,
            'string': "Events Ending Now",
            'stringtwo': "Please help Strike!"}

        content_end_txt = render_to_string(
            'emails/email_start_end.txt', context_end)
        content_end_html = render_to_string(
            'emails/email_start_end.html', context_end)

        email = EmailMultiAlternatives(subj_end, content_end_txt, from_email, [
                                       EMAIL_TARGET_START_END], headers=headers)
        email.attach_alternative(content_end_html, "text/html")
        email.send()
        # print "sent end email with %s events" % ending.count()

    else:
        # print "no events starting/ending"
        pass


# Cron Example
# * * * * * ~/bin/python ~/lnldb/manage.py send_start_end

# Self Service Emails
# Self service org email
def generate_selfservice_notice_email(context):
    subject = "Self Service Form Submission"
    from_email = settings.DEFAULT_FROM_ADDR
    to_email = settings.EMAIL_TARGET_VP

    cont_html = render_to_string('emails/email_selfservice.html', context)
    cont_text = render_to_string('emails/email_selfservice.txt', context)

    email = EmailMultiAlternatives(subject, cont_text, from_email, [to_email])
    email.attach_alternative(cont_html, "text/html")

    return email


# Self service member email
def generate_selfmember_notice_email(context):
    subject = "Self Service Member Request Submission"
    from_email = settings.DEFAULT_FROM_ADDR
    to_email = settings.EMAIL_TARGET_S

    cont_html = render_to_string('emails/email_selfmember.html', context)
    cont_text = render_to_string('emails/email_selfmember.txt', context)

    email = EmailMultiAlternatives(subject, cont_text, from_email, [to_email])
    email.attach_alternative(cont_html, "text/html")

    return email


class DefaultLNLEmailGenerator(object):  # yay classes

    def __init__(self,
                 subject="LNL Notice",
                 to_emails=settings.DEFAULT_TO_ADDR,
                 from_email=settings.DEFAULT_FROM_ADDR,
                 context=None,
                 template_basename="emails/email_generic",
                 build_html=True,
                 body=None,
                 bcc=None,
                 cc=None,
                 attachments=None):
        if isinstance(to_emails, str):
            to_emails = [to_emails]
        if context is None:
            context = {}
        if attachments is None:
            attachments = []
        context['subject'] = subject
        if body:
            context['body'] = body

        template_txt = "%s.txt" % template_basename
        content_txt = render_to_string(template_txt, context)
        # print bcc
        self.email = EmailMultiAlternatives(
            subject, content_txt, from_email, to_emails, bcc=bcc, cc=bcc)
        for a in attachments:
            self.email.attach(a['name'], a['file_handle'], "application/pdf")

        if build_html:
            template_html = "%s.html" % template_basename
            content_html = render_to_string(template_html, context)
            self.email.attach_alternative(content_html, "text/html")

    def send(self):
        self.email.send()
