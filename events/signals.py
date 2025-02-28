from django.db.models.signals import post_save
from email.mime.base import MIMEBase
from email.encoders import encode_base64
from django.dispatch import receiver
from django.utils import timezone
from django.utils.text import slugify

from accounts.models import UserPreferences
from emails.generators import CcAddEmailGenerator
from events.models import EventCCInstance
from events.cal import generate_ics, EventAttendee
from pdfs.views import generate_pdfs_standalone
from slack.views import cc_add_notification
from slack.api import lookup_user, slack_post

__all__ = [
    'email_cc_notification',
]


@receiver(post_save, sender=EventCCInstance)
def email_cc_notification(sender, instance, created, raw=False, **kwargs):
    """ Sends an email or Slack message to a crew chief to notify them of being made one """
    prefs, new_pref = UserPreferences.objects.get_or_create(user=instance.crew_chief)

    if created and not raw:
        if 'Email' in str(prefs.cc_add_subscriptions).split(', '):
            i = instance

            # generate our pdf
            event = i.event
            pdf_handle = generate_pdfs_standalone([event.id])
            filename = "%s.workorder.pdf" % slugify(event.event_name)
            attachments = [{"file_handle": pdf_handle, "name": filename}]

            # generate an Outlook invite
            chief = EventAttendee(event, i.crew_chief)
            invite_filename = '%s.invite.ics' % slugify(event.event_name)
            invite = MIMEBase('text', "calendar", method="PUBLISH", name=invite_filename)
            invite.set_payload(generate_ics([event], [chief]))
            encode_base64(invite)
            invite.add_header('Content-Description', invite_filename)
            invite.add_header('Content-class', "urn:content-classes:calendarmessage")
            invite.add_header('Filename', invite_filename)
            invite.add_header('Path', invite_filename)
            attachments.append(invite)

            if i.setup_start:
                local = timezone.localtime(i.setup_start)
                local_formatted = local.strftime("%A %B %d at %I:%M %p")
            else:
                local_formatted = "a time of your choice "

            context = {
                    "is_new_cc": True if i.crew_chief.ccinstances == 1 else False
                    }

            e = CcAddEmailGenerator(ccinstance=i, attachments=attachments, context=context)
            e.send()
        if 'Slack Notification' in str(prefs.cc_add_subscriptions).split(', '):
            blocks = cc_add_notification(instance)
            slack_user = lookup_user(instance.crew_chief)
            if slack_user:
                message = "You've been added as a crew chief for the event %s." % instance.event.event_name
                slack_post(slack_user, text=message, content=blocks)


# @receiver(post_save, sender=settings.AUTH_USER_MODEL)
# def initial_user_create_notify(sender, instance, created, raw=False, **kwargs):
#     if created and not raw:
#         i = instance
#         email_body = """
#         A new user has joined LNLDB:
#         %s (%s)
#         """ % (i.username, i.email)

#         e = DLEG(subject="LNL User Joined", to_emails=[settings.EMAIL_TARGET_S], body=email_body)
#         e.send()
