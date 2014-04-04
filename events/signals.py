from django.conf import settings
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django.utils import timezone       

from emails.generators import DefaultLNLEmailGenerator as DLEG
from events.models import Billing
from events.models import EventCCInstance

from pdfs.views import generate_pdfs_standalone
@receiver(post_save, sender = EventCCInstance)
def email_cc_notification(sender, instance, created, **kwargs):
    """ Sends an email to a crew cheif to notify them of being made one """
    if created:
        i = instance
        
        # generate our pdf
        event = i.event
        pdf_handle = generate_pdfs_standalone([event.id])
        filename = "%s.workorder.pdf" % event.id
        attachments = [{"file_handle":pdf_handle, "name": filename}]
        
        local = timezone.localtime(i.setup_start)
        local_formatted = local.strftime("%A %B %d at %I:%M %p")
        email_body = """
            You\'ve been added as a crew chief to the event "%s". <br / >
            You have signed up to be crew chief for %s, with your setup starting on %s in the %s
            """ % (i.event.event_name, i.service, local_formatted, i.setup_location, )
        e = DLEG(subject = "Crew Chief Add Notification", to_emails = [instance.crew_chief.email], body=email_body, attachments=attachments)
        e.send()
        

@receiver(post_save, sender = Billing)     
def email_billing_create(sender, instance, created, **kwargs):
    """ Sends an email to the client to notify of a bill being created """
    if created and not instance.opt_out_initial_email:
        i = instance
        email_body = """
            A New LNL bill has been posted for "%s" on %s for the amount of $%s
            """ % (i.event.event_name, i.date_billed, i.amount)
            
        e = DLEG(subject = "LNL Billing Create Notification", to_emails = [i.event.contact.email], body=email_body, bcc=[settings.EMAIL_TARGET_T])
        e.send()
            

@receiver(post_save, sender = Billing)
def email_billing_marked_paid(sender, instance, created, **kwargs):
    """ Sends an email to the client to notify of a bill having been paid """
    if not created:
        if instance.date_paid and not instance.opt_out_update_email: 
            i = instance
            email_body = """
            Thank you for paying the bill for "%s" on %s for the amount of $%s
            """ % (i.event.event_name, i.date_paid, i.amount)
            
            e = DLEG(subject = "LNL Billing Paid Notification", to_emails = [i.event.contact.email], body=email_body, bcc=[settings.EMAIL_TARGET_T])
            e.send()
            
@receiver(pre_delete, sender = Billing)
def email_billing_delete(sender,instance, **kwargs):
    if not instance.opt_out_update_email:
        i = instance
        email_body = """
            The bill for the amount of $%s on "%s" has been deleted
            """ % (i.amount, i.event.event_name,)
                
        e = DLEG(subject = "LNL Billing Deletion Notification", to_emails = [i.event.contact.email], body=email_body, bcc=[settings.EMAIL_TARGET_T])
        e.send()
    
@receiver(post_save, sender = User)
def initial_user_create_notify(sender, instance, created, **kwargs):
    if created:
        i = instance
        email_body = """
        A new user has joined LNLDB:
        %s (%s)
        """ % (i.username, i.email)
            
        e = DLEG(subject = "LNL User Joined", to_emails = [settings.EMAIL_TARGET_S], body=email_body)
        e.send()
        
        