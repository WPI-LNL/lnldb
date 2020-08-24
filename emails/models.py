from django.db import models
from django.conf import settings
import uuid


class MeetingNoticeMail(models.Model):
    ts = models.DateTimeField(auto_now_add=True)

    place = models.CharField(max_length=32, default="AK219")
    time = models.TimeField(default="17:00")
    date = models.DateField()

    note = models.TextField()

    start_param = models.DateField()
    end_param = models.DateField()

    sent = models.BooleanField(default=False)


aliases = (
    (settings.DEFAULT_TO_ADDR, 'Exec Board'),
    (settings.EMAIL_TARGET_ACTIVE, 'Active Members'),
    (settings.EMAIL_TARGET_NEWS, 'LNL News'),
    (settings.EMAIL_TARGET_W, 'Webmaster')
)


class ServiceAnnounce(models.Model):
    subject = models.CharField(max_length=128)
    message = models.TextField()
    email_to = models.CharField(choices=aliases, max_length=24, default='lnl@wpi.edu')

    uuid = models.UUIDField(editable=False, default=uuid.uuid4, blank=True)


class SMSMessage(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    message = models.TextField()

    class Meta:
        permissions = (
            ('send', 'Send SMS Messages'),
        )
