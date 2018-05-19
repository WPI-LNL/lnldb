import datetime

from django.conf import settings
from django.db.models.signals import post_save, pre_delete, pre_save
from django.dispatch import receiver
from django.utils import timezone
from django.utils.text import slugify

from emails.generators import CcAddEmailGenerator, DefaultLNLEmailGenerator as DLEG
from events.models import EventCCInstance, Fund
from pdfs.views import generate_pdfs_standalone

__all__ = [
    'email_cc_notification', 'update_fund_time'
]


@receiver(post_save, sender=EventCCInstance)
def email_cc_notification(sender, instance, created, raw=False, **kwargs):
    """ Sends an email to a crew chief to notify them of being made one """
    if created and not raw:
        i = instance

        # generate our pdf
        event = i.event
        pdf_handle = generate_pdfs_standalone([event.id])
        filename = "%s.workorder.pdf" % slugify(event.event_name)
        attachments = [{"file_handle": pdf_handle, "name": filename}]

        if i.setup_start:
            local = timezone.localtime(i.setup_start)
            local_formatted = local.strftime("%A %B %d at %I:%M %p")
        else:
            local_formatted = "a time of your choice "

        e = CcAddEmailGenerator(ccinstance=i, attachments=attachments)
        e.send()


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


@receiver(pre_save, sender=Fund)
def update_fund_time(sender, instance, **kwargs):
    instance.last_updated = datetime.date.today()
