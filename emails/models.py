from django.db import models
from django.conf import settings


class MeetingNoticeMail(models.Model):
    """ Meeting Notice Email """
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


class SMSMessage(models.Model):
    """ SMS Text Message """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    message = models.TextField()

    class Meta:
        permissions = (
            ('send', 'Send SMS Messages'),
        )
