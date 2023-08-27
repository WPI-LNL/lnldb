# noinspection PyProtectedMember
from django.contrib.auth.models import AbstractUser, _user_has_perm
from django.db.models import (Model, BooleanField, CharField, IntegerField, BigIntegerField, PositiveIntegerField, Q,
                              TextField, DateField, DateTimeField, OneToOneField, ManyToManyField, ImageField, CASCADE,
                              SET_NULL, signals)
from django.core.validators import MinValueValidator,MaxValueValidator
from django.utils import timezone
from multiselectfield import MultiSelectField
from django.conf import settings
from six import python_2_unicode_compatible
from django.dispatch import receiver

from data.storage import OverwriteStorage
from events.models import Organization
from meetings.models import MeetingType

import os

# from django_custom_user_migration.models import AbstractUser

carrier_choices = (
    ('', 'Opt-out'),
    ('txt.att.net', 'AT&T'),
    ('myboostmobile.com', 'Boost Mobile'),
    ('mms.cricketwireless.net', 'Cricket'),
    ('msg.fi.google.com', 'Google Fi'),
    ('mymetropcs.com', 'Metro PCS'),
    ('mmst5.tracfone.com', 'Simple Mobile'),
    ('messaging.sprintpcs.com', 'Sprint'),
    ('tmomail.net', 'T-Mobile'),
    ('vtext.com', 'Verizon'),
    ('vmobl.com', 'Virgin Mobile'),
    ('vmobile.ca', 'Virgin Mobile Canada'),
    ('vtext.com', 'Xfinity Mobile')
)


@python_2_unicode_compatible
class User(AbstractUser):
    """Extended User Class"""
    def save(self, *args, **kwargs):
        # gives an email from the username when first created (ie. via CAS)
        if not self.pk and not self.email:
            self.email = "%s@wpi.edu" % self.username
        super(User, self).save(*args, **kwargs)

    wpibox = IntegerField(null=True, blank=True, verbose_name="WPI Box Number")
    phone = CharField(max_length=24, null=True, blank=True, verbose_name="Phone Number")
    carrier = CharField(choices=carrier_choices, max_length=25, verbose_name="Cellular Carrier",
                        help_text="By selecting your cellular carrier you consent to receiving text messages from LNL",
                        null=True, blank=True, default='')
    addr = TextField(null=True, blank=True, verbose_name="Address / Office Location")
    mdc = CharField(max_length=32, null=True, blank=True, verbose_name="MDC")
    nickname = CharField(max_length=32, null=True, blank=True, verbose_name="Nickname")
    student_id = PositiveIntegerField(null=True, blank=True, verbose_name="Student ID")
    class_year = PositiveIntegerField(null=True, blank=True, validators=[MinValueValidator(1962), MaxValueValidator(timezone.now().year + 6)])
    locked = BooleanField(default=False)
    away_exp = DateField(verbose_name="Away Status Expiration", null=True, blank=True)
    onboarded = BooleanField(default=False, verbose_name="Onboarding Complete")

    pronouns = CharField(max_length=32, null=True, blank=True, verbose_name="Pronouns")

    def __str__(self):
        nick = '"%s" ' % self.nickname if self.nickname else ""
        if self.first_name or self.last_name:
            return self.first_name + " " + nick + self.last_name
        return "[%s]" % self.username

    def has_perm(self, perm, obj=None):
        """
        Returns True if the user has the specified permission. This method
        queries all available auth backends, but returns immediately if any
        backend returns True. Thus, a user who has permission from a single
        auth backend is assumed to have permission in general. If an object is
        provided, permissions for this specific object are checked.

        This differs from the default in that superusers, while still having
        every permission, will be allowed after the logic has executed. This
        helps with typos in permission strings.
        """
        has_perm = _user_has_perm(self, perm, obj)
        # Active superusers have all permissions.
        if self.is_active and self.is_superuser:
            return True
        else:
            return has_perm

    @property
    def name(self):
        """User's full name"""
        return self.first_name + " " + self.last_name

    @property
    def is_lnl(self):
        """Is an LNL member"""
        return self.groups.filter(Q(name="Alumni") | Q(name="Active") | Q(name="Officer") | Q(name="Associate") | Q(
            name="Away") | Q(name="Inactive")).exists()

    @property
    def is_complete(self):
        """
        Returns false if the user's profile is incomplete. The user will be constantly reminded to complete their
        profile.
        """
        # if this returns false, the user will be constantly reminded to update their profile
        return self.first_name and self.last_name and self.email and (not self.is_lnl or self.class_year)

    @property
    def group_str(self):
        """Groups the user belongs to"""
        groups = [g.name for g in self.groups.all()]
        out_str = ""
        if "Alumni" in groups:
            out_str += 'Alum '
        if "Officer" in groups:
            out_str += 'Officer'
        elif "Active" in groups:
            out_str += 'Active'
        elif "Associate" in groups:
            out_str += 'Associate'
        elif "Away" in groups:
            out_str += 'Away'
        elif "Inactive" in groups:
            out_str += 'Inactive'
        else:
            out_str += "Unclassified"
        return out_str

    @property
    def owns(self):
        """Organizations the user owns"""
        return ', '.join(map(str, self.orgowner.all()))

    @property
    def orgs(self):
        """Organizations the user belongs to"""
        return ', '.join(map(str, self.orgusers.all()))

    @property
    def all_orgs(self):
        """All organizations the user is associated with"""
        return Organization.objects.complex_filter(
            Q(user_in_charge=self) | Q(associated_users=self)
        ).distinct()

    @property
    def mdc_name(self):
        max_chars = 12
        clean_first, clean_last = "", ""

        # assume that Motorola can handle practically nothing. Yes, ugly, but I don't wanna regex 1000's of times
        for char in self.first_name.upper().strip():
            if ord(char) == ord(' ') or ord(char) == ord('-') \
                    or ord('0') <= ord(char) <= ord('9') or ord('A') <= ord(char) <= ord('Z'):
                clean_first += char
        for char in self.last_name.upper().strip():
            if ord(char) == ord(' ') or ord(char) == ord('-') \
                    or ord('0') <= ord(char) <= ord('9') or ord('A') <= ord(char) <= ord('Z'):
                clean_last += char

        outstr = clean_last[:max_chars - 2] + ","  # leave room for at least an initial
        outstr += clean_first[:max_chars - len(outstr)]  # fill whatever's left with the first name
        return outstr

    class Meta:
        ordering = 'last_name', 'first_name', 'class_year'
        permissions = (
            ('change_membership', 'Change the group membership of a user'),
            ('edit_mdc', 'Change the MDC of a user'),
            ('view_member', 'View LNL members'),
        )


def path_and_rename(instance, filename):
    """
    Determine path for storing officer headshots. Will rename with officer's username.

    :param instance: A ProfilePhoto instance
    :param filename: The original name of the uploaded file
    :returns: New path to save file to
    """
    upload_to = 'officers'
    ext = filename.split('.')[-1]
    if instance.officer.get_username():
        filename = "{}.{}".format(instance.officer.get_username(), ext)
    return os.path.join(upload_to, filename)


@python_2_unicode_compatible
class ProfilePhoto(Model):
    """ Officer profile photo """
    officer = OneToOneField(User, on_delete=CASCADE, related_name="img")
    img = ImageField(upload_to=path_and_rename, storage=OverwriteStorage(), verbose_name="Image")

    def __str__(self):
        return self.officer.name


@receiver(signals.post_delete, sender=ProfilePhoto)
def officer_img_cleanup(sender, instance, **kwargs):
    """
    When an instance of ProfilePhoto is deleted, delete the respective files as well.

    :param instance: A ProfilePhoto instance
    """
    instance.img.delete(False)


class Officer(Model):
    """ Represents an Officer position """
    user = OneToOneField(User, on_delete=SET_NULL, blank=True, null=True, related_name="exec_position")
    title = CharField(max_length=60, verbose_name="Officer Position")
    img = OneToOneField(ProfilePhoto, on_delete=SET_NULL, blank=True, null=True, related_name="officer_img")

    def __str__(self):
        return self.title


class PhoneVerificationCode(Model):
    """Used for temporarily saving the last code sent to a user to verify their phone number"""
    user = OneToOneField(settings.AUTH_USER_MODEL, on_delete=CASCADE, related_name="verification_codes")
    code = BigIntegerField()
    timestamp = DateTimeField(auto_now_add=True)


event_fields = [
    ('event_name', 'Event name'),
    ('description', 'Description'),
    ('location', 'Location'),
    ('contact', 'Contact'),
    ('billing_org', 'Billing org'),
    ('datetime_setup_complete', 'Datetime setup complete'),
    ('datetime_start', 'Datetime start'),
    ('datetime_end', 'Datetime end'),
    ('internal_notes', 'Internal notes'),
    ('billed_in_bulk', 'Billed in bulk'),
    ('org', 'Client')
]


class UserPreferences(Model):
    """ User-specific settings """
    user = OneToOneField(settings.AUTH_USER_MODEL, on_delete=CASCADE, related_name="preferences")
    theme = CharField(choices=(("default", "Default"),), default="default", max_length=12)

    rt_token = CharField(blank=True, null=True, verbose_name="RT Auth Token", max_length=256)

    # Communication Preferences
    cc_add_subscriptions = MultiSelectField(choices=(('email', 'Email'), ('slack', 'Slack Notification')),
                                            default='email', blank=True, null=True)

    cc_report_reminders = CharField(choices=(('email', 'Email'), ('slack', 'Slack Notification'), ('all', 'Both')),
                                    default='email', max_length=12)

    event_edited_notification_methods = CharField(
        choices=(('email', 'Email'), ('slack', 'Slack Notification'), ('all', 'Both')),
        default='email',
        max_length=12
    )

    event_edited_field_subscriptions = MultiSelectField(
        choices=event_fields,
        default=['location', 'datetime_setup_complete', 'datetime_start', 'datetime_end']
    )

    ignore_user_action = BooleanField(
        default=False, help_text="Uncheck this to ignore notifications for actions triggered by the user"
    )

    meeting_invites = BooleanField(
        default=False, help_text="Opt-in to receiving calendar invites for meetings"
    )

    meeting_invite_subscriptions = ManyToManyField(MeetingType, blank=True, related_name="invite_subscriptions")
