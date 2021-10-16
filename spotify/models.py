from django.db import models

from events.models import Event2019


# Create your models here.
class Session(models.Model):
    event = models.ForeignKey(Event2019, on_delete=models.CASCADE)
    accepting_requests = models.BooleanField(default=True)
    allow_explicit = models.BooleanField(default=True)
    require_payment = models.BooleanField(default=False)

    auth_token = models.CharField(max_length=250, blank=True, null=True)
    refresh_token = models.CharField(max_length=250, blank=True, null=True)


class SongRequest(models.Model):
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name="requests")
    name = models.CharField(max_length=150)
    identifier = models.CharField(max_length=32)
    duration = models.IntegerField(help_text="Duration in ms")
    approved = models.BooleanField(default=False)
    queued = models.DateTimeField(blank=True, null=True)
    paid = models.BooleanField(default=False)

    submitted_by = models.CharField(max_length=150)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=24, blank=True, null=True)

    class Meta:
        permissions = (
            ('submit_song_request', 'Can submit song requests'),
            ('approve_song_request', 'Approve song requests'),
        )
