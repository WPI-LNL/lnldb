import datetime

import pytz
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from events.models import Event

EMAIL_KEY_START_END = settings.EMAIL_KEY_START_END
EMAIL_TARGET_START_END = settings.EMAIL_TARGET_START_END
DEFAULT_TO_ADDR = settings.DEFAULT_TO_ADDR


def generate_notice_email(notice):
    subject = notice.subject
    from_email = settings.DEFAULT_FROM_ADDR
    reply_to_email = settings.EMAIL_TARGET_S
    to_email = notice.email_to.email

    context = {'object': notice}

    cont_html = render_to_string('emails/email_notice.html', context)
    cont_text = render_to_string('emails/email_notice.txt', context)

    email = EmailMultiAlternatives(subject, cont_text, from_email, [to_email], reply_to=[reply_to_email])
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
    to_emails = [orgtransfer.old_user_in_charge.email, orgtransfer.org.exec_email]
    to_emails = [e for e in to_emails if e is not None]
    bcc = [settings.EMAIL_TARGET_W]

    context = {'object': orgtransfer}

    cont_html = render_to_string('emails/email_transfer.html', context)
    cont_text = render_to_string('emails/email_transfer.txt', context)

    email = EmailMultiAlternatives(subject, cont_text, from_email, to_emails, bcc=bcc)
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

    from_email = settings.DEFAULT_FROM_ADDR

    if starting:
        context_start = {'events': starting, 'string': "Events Starting Now", 'stringtwo': ""}

        content_start_txt = render_to_string('emails/email_start_end.txt', context_start)
        content_start_html = render_to_string('emails/email_start_end.html', context_start)

        email = EmailMultiAlternatives(subj_start, content_start_txt, from_email, [EMAIL_TARGET_START_END],
                                       headers=headers)
        email.attach_alternative(content_start_html, "text/html")
        email.send()

    elif ending:
        context_end = {'events': ending, 'string': "Events Ending Now", 'stringtwo': "Please help Strike!"}

        content_end_txt = render_to_string('emails/email_start_end.txt', context_end)
        content_end_html = render_to_string('emails/email_start_end.html', context_end)

        email = EmailMultiAlternatives(subj_end, content_end_txt, from_email, [EMAIL_TARGET_START_END], headers=headers)
        email.attach_alternative(content_end_html, "text/html")
        email.send()


# Cron Example
# * * * * * ~/bin/python ~/lnldb/manage.py send_start_end

# Self Service Emails
# Self service org email
def generate_selfservice_notice_email(context):
    subject = "Self Service Form Submission"
    from_email = settings.DEFAULT_FROM_ADDR
    to_email = [settings.EMAIL_TARGET_W, settings.EMAIL_TARGET_VP]

    cont_html = render_to_string('emails/email_selfservice.html', context)
    cont_text = render_to_string('emails/email_selfservice.txt', context)

    email = EmailMultiAlternatives(subject, cont_text, from_email, to_email)
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
                 cc=None,
                 bcc=None,
                 from_email=settings.DEFAULT_FROM_ADDR,
                 reply_to=None,
                 context=None,
                 template_basename="emails/email_generic",
                 build_html=True,
                 body=None,
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
        self.email = EmailMultiAlternatives(subject, content_txt, from_email, to_emails, bcc=bcc, cc=cc, reply_to=reply_to)
        for a in attachments:
            self.email.attach(a['name'], a['file_handle'], "application/pdf")

        if build_html:
            template_html = "%s.html" % template_basename
            content_html = render_to_string(template_html, context)
            self.email.attach_alternative(content_html, "text/html")

    def send(self):
        self.email.send()


class EventEmailGenerator(DefaultLNLEmailGenerator):
    def __init__(self,
            event=None,
            subject="LNL Event",
            to_emails=settings.DEFAULT_TO_ADDR,
            cc=None,
            bcc=None,
            from_email=settings.DEFAULT_FROM_ADDR,
            reply_to=None,
            context=None,
            template_basename="emails/email_event",
            build_html=True,
            body=None,
            attachments=None):
        if context is None:
            context = {}
        context['event'] = event
        super(EventEmailGenerator, self).__init__(
                subject=subject,
                to_emails=to_emails,
                cc=cc,
                bcc=bcc,
                from_email=from_email,
                reply_to=reply_to,
                context=context,
                template_basename=template_basename,
                build_html=build_html,
                body=body,
                attachments=attachments)


class CcAddEmailGenerator(DefaultLNLEmailGenerator):
    def __init__(self,
            ccinstance=None,
            subject="Crew Chief Add Notification",
            to_emails=None,
            cc=None,
            bcc=None,
            from_email=settings.DEFAULT_FROM_ADDR,
            reply_to=None,
            context=None,
            template_basename="emails/email_ccadd",
            build_html=True,
            attachments=None):
        if to_emails is None:
            to_emails = [ccinstance.crew_chief.email]
        if context is None:
            context = {}
        context['ccinstance'] = ccinstance
        super(CcAddEmailGenerator, self).__init__(
                subject=subject,
                to_emails=to_emails,
                cc=cc,
                bcc=bcc,
                from_email=from_email,
                reply_to=reply_to,
                context=context,
                template_basename=template_basename,
                build_html=build_html,
                body=None,
                attachments=attachments)


class ReportReminderEmailGenerator(DefaultLNLEmailGenerator):
    def __init__(self,
            reminder=None,
            subject="LNL Crew Chief Report Reminder Email",
            to_emails=None,
            cc=None,
            bcc=None,
            from_email=settings.DEFAULT_FROM_ADDR,
            reply_to=None,
            context=None,
            template_basename="emails/email_reportreminder",
            build_html=True,
            attachments=None):
        if to_emails is None:
            to_emails = [reminder.crew_chief.email]
        if context is None:
            context = {}
        context['reminder'] = reminder
        super(ReportReminderEmailGenerator, self).__init__(
                subject=subject,
                to_emails=to_emails,
                cc=cc,
                bcc=bcc,
                from_email=from_email,
                reply_to=reply_to,
                context=context,
                template_basename=template_basename,
                build_html=build_html,
                body=None,
                attachments=attachments)

class BillingEmailGenerator(DefaultLNLEmailGenerator):
    def __init__(self,
            event=None,
            subject="Invoice for LNL Services",
            to_emails=settings.DEFAULT_TO_ADDR,
            cc=None,
            bcc=[settings.EMAIL_TARGET_T],
            from_email=settings.DEFAULT_FROM_ADDR,
            reply_to=[settings.EMAIL_TARGET_T],
            context=None,
            template_basename="emails/email_billing",
            build_html=True,
            body=None,
            attachments=None):
        if context is None:
            context = {}
        context['event'] = event
        super(BillingEmailGenerator, self).__init__(
                subject=subject,
                to_emails=to_emails,
                cc=cc,
                bcc=bcc,
                from_email=from_email,
                reply_to=reply_to,
                context=context,
                template_basename=template_basename,
                build_html=build_html,
                body=body,
                attachments=attachments)
