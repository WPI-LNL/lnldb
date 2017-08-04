import datetime

from django.conf import settings
from django.db import models
from django.utils.functional import cached_property
from django.utils.encoding import python_2_unicode_compatible

EXPIRY_WARNING_DAYS = 30

# Create your models here.
PIT_CHOICES = (
    ('P1', 'PIT1'),
    ('P2', 'PIT2'),
    ('P3', 'PIT3'),
    ('P4', 'PIT4'),
    ('P5', 'PIT5'),
    ('PP', 'Past Practical'),
    ('L', 'Licensed'),
)


@python_2_unicode_compatible
class Projectionist(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL)
    # pit_level = models.CharField(choices=PIT_CHOICES,max_length=2,null=True,blank=True)

    license_number = models.CharField(max_length=10, null=True, blank=True)
    license_expiry = models.DateField(null=True, blank=True)

    def __str__(self):
        return self.user.get_full_name()

    @property
    def level(self):
        return self.pitinstances.filter(valid=True) \
            .select_related('pit_level').order_by('-pit_level__ordering') \
            .first()

    @property
    def expiring(self):
        if self.license_expiry is None:
            return None

        today = datetime.date.today()
        delta = today + datetime.timedelta(days=EXPIRY_WARNING_DAYS)
        if delta > self.license_expiry > today:
            return True
        else:
            return False

    @property
    def expired(self):
        if self.license_expiry is None:
            return None
        elif datetime.date.today() >= self.license_expiry:
            return True
        else:
            return False

    @cached_property
    def validlevels(self):
        return self.pitinstances.filter(valid=True) \
            .values_list('pit_level__name_short', flat=True)

    @property
    def is_alumni(self):
        return self.user.groups.filter(name="Alumni").exists()

    class Meta:
        permissions = (
            ('view_pits', 'View a projectionist\'s PITs'),
            ('edit_pits', 'Edit a projectionist\'s PITs'),
            ('add_bulk_events', 'Create a semester\'s worth of movies')
        )


@python_2_unicode_compatible
class PITLevel(models.Model):
    name_short = models.CharField(max_length=3)
    name_long = models.CharField(max_length=16)
    ordering = models.IntegerField(default=0)

    def __str__(self):
        return u'%s (%s)' % (self.name_long, self.name_short)


class PitInstance(models.Model):
    projectionist = models.ForeignKey(Projectionist, related_name="pitinstances")
    pit_level = models.ForeignKey(PITLevel, related_name="pitinstances")
    created_on = models.DateTimeField()
    valid = models.BooleanField(default=True)


def create_projectionist(sender, instance, created, **kwargs):
    if created:
        Projectionist.objects.create(user=instance)

# post_save.connect(create_projectionist, sender=User)
