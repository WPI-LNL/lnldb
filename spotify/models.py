from django.db import models
from django.conf import settings
from django.utils.crypto import get_random_string

from events.models import Event2019
from helpers.util import unique_slug_generator


# Create your models here.
class SpotifyUser(models.Model):
    """ Represents a user's Spotify Account. Authentication tokens will be saved here. """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="spotify_accounts")
    display_name = models.CharField(max_length=150, blank=True, null=True)
    spotify_id = models.CharField(max_length=150, blank=True, null=True)
    token_info = models.TextField(blank=True, null=True)

    personal = models.BooleanField(default=True, help_text="Uncheck this for shared club accounts")

    def __str__(self):
        if self.display_name:
            return self.display_name
        return self.user.name + " (No profile data)"


class Session(models.Model):
    """ Spotify song request session for a specific event """
    event = models.ForeignKey(Event2019, on_delete=models.CASCADE)
    accepting_requests = models.BooleanField(default=True)
    allow_explicit = models.BooleanField(default=True)
    auto_approve = models.BooleanField(default=False)
    require_payment = models.BooleanField(default=False)
    allow_silence = models.BooleanField(default=False)
    private = models.BooleanField(default=False)

    user = models.ForeignKey(SpotifyUser, on_delete=models.CASCADE)
    slug = models.SlugField(max_length=128, unique=True)

    # Payment methods
    paypal = models.URLField(help_text="PayPal.Me Link", blank=True, null=True)
    venmo = models.CharField(max_length=16, help_text="Venmo username", blank=True, null=True)
    venmo_verification = models.CharField(max_length=4, blank=True, null=True)

    def __str__(self):
        return self.event.event_name

    def save(self, *args, **kwargs):
        if self.private:
            self.slug = unique_slug_generator(self, self.event.event_name, get_random_string(12))
        else:
            self.slug = unique_slug_generator(self, self.event.event_name)
        super(Session, self).save(*args, **kwargs)


class SongRequest(models.Model):
    """ Used in keeping track of a song request """
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
