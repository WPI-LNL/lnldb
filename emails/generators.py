from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives

DEFAULT_FROM_ADDR = 'LnL <lnl@wpi.edu>'

def generate_notice_email(notice):
    subject = notice.subject
    from_email = DEFAULT_FROM_ADDR
    to_email = notice.email_to.email
    
    context = {}
    context['object'] = notice
    
    cont_html = render_to_string('emails/email_notice.html',context)
    cont_text = notice.message
    
    email = EmailMultiAlternatives(subject,cont_text,from_email,[to_email])
    email.attach_alternative(cont_html, "text/html")
    
    return email


def generate_transfer_email(orgtransfer):
    subject = "LNL Organization Control Transfer for %s" % orgtransfer.org.name
    from_email = DEFAULT_FROM_ADDR
    to_email = "%s@wpi.edu" % orgtransfer.old_user_in_charge.username
    
    context = {}
    context['object']  = orgtransfer
    
    cont_html = render_to_string('emails/email_transfer.html',context)
    cont_text = render_to_string('emails/email_transfer.txt',context)
    
    email = EmailMultiAlternatives(subject,cont_text,from_email,[to_email])
    email.attach_alternative(cont_html, "text/html")
    
    return email