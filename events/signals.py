from django.conf import settings
from django.db.models.signals import post_save, pre_save
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django.utils import timezone

import datetime

from emails.generators import DefaultLNLEmailGenerator as DLEG
from events.models import Billing, Fund, Event
from events.models import EventCCInstance
from django.utils.text import slugify

from pdfs.views import generate_pdfs_standalone


@receiver(post_save, sender=EventCCInstance)
def email_cc_notification(sender, instance, created, raw=False, **kwargs):
    """ Sends an email to a crew cheif to notify them of being made one """
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

        email_body = """
            You\'ve been added as a crew chief to the event "%s". \n
            You have signed up to be crew chief for %s, with your setup starting on %s in the %s \n
            \n
            Please note that the attached Workorder PDF contains all services relating to the event,
             not just your assigned service.
            """ % (i.event.event_name, i.service, local_formatted, i.setup_location, )
        e = DLEG(subject="Crew Chief Add Notification", to_emails=[instance.crew_chief.email], body=email_body,
                 attachments=attachments)
        e.send()


@receiver(post_save, sender=Billing)
def email_billing_create(sender, instance, created, raw=False, **kwargs):
    """ Sends an email to the client to notify of a bill being created """
    if created and not instance.opt_out_initial_email and not raw:
        i = instance
        email_body = """
            A New LNL bill has been posted for "%s" on %s for the amount of $%s
            """ % (i.event.event_name, i.date_billed, i.amount)

        e = DLEG(subject="LNL Billing Create Notification", to_emails=[i.event.contact.email], body=email_body,
                 bcc=[settings.EMAIL_TARGET_T])
        e.send()


@receiver(post_save, sender=Billing)
def email_billing_marked_paid(sender, instance, created, raw=False, **kwargs):
    """ Sends an email to the client to notify of a bill having been paid """
    if not created and not raw:
        if instance.date_paid and not instance.opt_out_update_email:
            i = instance
            email_body = """
            Thank you for paying the bill for "%s" on %s for the amount of $%s
            """ % (i.event.event_name, i.date_paid, i.amount)

            e = DLEG(subject="LNL Billing Paid Notification", to_emails=[i.event.contact.email], body=email_body,
                     bcc=[settings.EMAIL_TARGET_T])
            e.send()


@receiver(pre_delete, sender=Billing)
def email_billing_delete(sender, instance, **kwargs):
    if not instance.opt_out_update_email:
        i = instance
        email_body = """
            The bill for the amount of $%s on "%s" has been deleted
            """ % (i.amount, i.event.event_name,)

        e = DLEG(subject="LNL Billing Deletion Notification", to_emails=[i.event.contact.email], body=email_body,
                 bcc=[settings.EMAIL_TARGET_T])
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
