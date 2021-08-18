import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.urls.base import reverse
from django.utils import timezone
from six import python_2_unicode_compatible

from django_extensions.db.models import TimeStampedModel

from events.models import BaseEvent, get_host


def get_default_email():
    qs = TargetEmailList.objects.filter(email="lnlnews@wpi.edu")
    if not qs.exists():
        email = TargetEmailList(name="LNL News", email="lnlnews@wpi.edu")
        email.save()
    else:
        email = qs.first()
    return email.pk


# When Django 1.9 hits with proper M2M migration,
#   use this to override closed viewing per meeting
#   with a 'through' parameter on 'attendance'.
# class MeetingAttendee(models.Model):
#     meeting = models.ForeignKey('Meeting')
#     attendee = models.ForeignKey(User)
#     closed_privy = models.BooleanField(default=False)
#
#     class Meta:
#         unique_together = ('meeting', 'attendee')
#         db_table = 'meetings_meeting_attendance'


@python_2_unicode_compatible
class Meeting(models.Model):
    glyphicon = 'briefcase'
    datetime = models.DateTimeField(verbose_name="Start Time")
    duration = models.DurationField(default=timedelta(hours=1), null=False, blank=False)
    attendance = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True)
    meeting_type = models.ForeignKey('MeetingType', on_delete=models.PROTECT, default=1)
    location = models.ForeignKey('events.Location', on_delete=models.PROTECT, null=True, blank=True)
    agenda = models.TextField(null=True, blank=True)
    minutes = models.TextField(null=True, blank=True)
    minutes_private = models.TextField(verbose_name="Closed Minutes", null=True, blank=True)

    @property
    def name(self):
        return "%s Meeting on %s" % (self.meeting_type.name, self.datetime.astimezone(timezone.get_current_timezone()).date())

    @property
    def endtime(self):
        return self.datetime + self.duration

    def cal_name(self):
        """ Title to display on calendars """
        return "LNL Meeting - " + self.meeting_type.name

    def cal_desc(self):
        """ No description will be provided for meetings displayed on calendars """
        return ""

    def cal_location(self):
        """ The location name used by calendars """
        if self.location:
            return self.location.name
        else:
            return ""

    def cal_start(self):
        """ The meeting start time used by calendars """
        return self.datetime

    def cal_end(self):
        """ The meeting end time used by calendars """
        return self.datetime + self.duration

    def cal_link(self):
        """ Link to be displayed on calendars """
        return get_host() + reverse('meetings:detail', args=[self.id])

    def cal_guid(self):
        """ Unique event id used by calendars """
        return "mtg" + str(self.id) + "@lnldb"

    def get_absolute_url(self):
        return reverse('meetings:detail', args=[self.id])

    def __str__(self):
        return "Meeting For %s" % self.datetime.astimezone(timezone.get_current_timezone()).date()

    class Meta:
        ordering = ('-datetime',)
        permissions = (("view_mtg", "See all meeting info"),
                       ("edit_mtg", "Edit all meeting info"),
                       ("view_mtg_attendance", "See meeting attendance"),
                       ("list_mtgs", "List all meetings"),
                       ("create_mtg", "Create a meeting"),
                       ("send_mtg_notice", "Send meeting notices manually"),
                       ("view_mtg_closed", "See closed meeting info"))


def mtg_attachment_file_name(instance, filename):
    return '/'.join(['meeting_uploads', str(instance.meeting.pk), filename])


class MtgAttachment(TimeStampedModel):
    glyphicon = 'paperclip'
    name = models.CharField(max_length=64, null=False, blank=False)
    file = models.FileField(upload_to=mtg_attachment_file_name, blank=False, null=False)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, editable=False, null=False)
    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name='attachments', null=True)
    private = models.BooleanField(default=False)


class MeetingAnnounce(models.Model):
    """ Contents of an email containing a meeting notice """
    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE)
    events = models.ManyToManyField(BaseEvent, related_name="meetingannouncements", blank=True)
    subject = models.CharField(max_length=128)
    message = models.TextField()
    email_to = models.ForeignKey('TargetEmailList', on_delete=models.PROTECT)

    added = models.DateTimeField(auto_now_add=True)
    uuid = models.UUIDField(editable=False, default=uuid.uuid4, blank=True)

    @property
    def reverse_ordered_events(self):
        return self.events.order_by('datetime_start')


@python_2_unicode_compatible
class TargetEmailList(models.Model):
    """ Represents a target email address (i.e. aliases) """
    name = models.CharField(max_length=16)
    email = models.EmailField()

    def __str__(self):
        return "%s (%s)" % (self.name, self.email)


class AnnounceSend(models.Model):
    """ Log of when a meeting notice has been sent out """
    announce = models.ForeignKey(MeetingAnnounce, on_delete=models.CASCADE)
    sent_at = models.DateTimeField(auto_now_add=True)
    sent_success = models.BooleanField(default=False)


@python_2_unicode_compatible
class MeetingType(models.Model):
    """ Used to specify the type of meeting (i.e. Exec Board, General Body, etc.) """
    name = models.CharField(max_length=32)

    def __str__(self):
        return self.name


class CCNoticeSend(models.Model):
    """ Contents of an email containing a meeting CC notice """
    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name="meetingccnotices")
    events = models.ManyToManyField(BaseEvent, related_name="meetingccnoticeevents", blank=True)
    sent_at = models.DateTimeField(auto_now_add=True)
    sent_success = models.BooleanField(default=False)
    uuid = models.UUIDField(editable=False, default=uuid.uuid4, blank=True)

    email_to = models.ForeignKey('TargetEmailList', on_delete=models.PROTECT, default=get_default_email)

    addtl_message = models.TextField(null=True, blank=True, verbose_name="Additional Message")

    @property
    def subject(self):
        return "Lens and Lights Crew List for %s" % self.meeting.datetime.date()

    @property
    def reverse_ordered_events(self):
        return self.events.order_by('datetime_start')
