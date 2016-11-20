import uuid
from datetime import timedelta

from django.conf import settings
from django.core.urlresolvers import reverse
from django.db import models
from django_extensions.db.models import TimeStampedModel

from events.models import Event


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


class Meeting(models.Model):
    glyphicon = 'briefcase'
    datetime = models.DateTimeField(verbose_name="Start Time")
    duration = models.DurationField(default=timedelta(hours=1), null=False, blank=False)
    attendance = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True)
    meeting_type = models.ForeignKey('MeetingType', default=1)
    location = models.ForeignKey('events.Location', null=True, blank=True)
    agenda = models.TextField(null=True, blank=True)
    minutes = models.TextField(null=True, blank=True)
    minutes_private = models.TextField(verbose_name="Closed Minutes", null=True, blank=True)

    @property
    def name(self):
        return "%s Meeting on %s" % (self.meeting_type.name, self.datetime.date())

    @property
    def endtime(self):
        return self.datetime + self.duration

    def cal_name(self):
        return "Meeting - " + self.meeting_type.name

    def cal_desc(self):
        return ""

    def cal_location(self):
        if self.location:
            return self.location.name
        else:
            return ""

    def cal_start(self):
        return self.datetime

    def cal_end(self):
        return self.datetime + self.duration

    def cal_link(self):
        return reverse('meetings:detail', args=[self.id])

    def cal_guid(self):
        return "mtg" + str(self.id) + "@lnldb"

    def get_absolute_url(self):
        return reverse('meetings:detail', args=[self.id])

    def __unicode__(self):
        return "Meeting For %s" % self.datetime.date()

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
    author = models.ForeignKey(settings.AUTH_USER_MODEL, editable=False, null=False)
    meeting = models.ForeignKey(Meeting, related_name='attachments', null=True)
    private = models.BooleanField(default=False)


class MeetingAnnounce(models.Model):
    meeting = models.ForeignKey(Meeting)
    events = models.ManyToManyField(Event, related_name="meetingannouncements", blank=True)
    subject = models.CharField(max_length=128)
    message = models.TextField()
    email_to = models.ForeignKey('TargetEmailList')

    added = models.DateTimeField(auto_now_add=True)
    uuid = models.UUIDField(editable=False, default=uuid.uuid4, blank=True)

    @property
    def reverse_ordered_events(self):
        return self.events.order_by('datetime_start')


class TargetEmailList(models.Model):
    name = models.CharField(max_length=16)
    email = models.EmailField()

    def __unicode__(self):
        return "%s (%s)" % (self.name, self.email)


class AnnounceSend(models.Model):
    announce = models.ForeignKey(MeetingAnnounce)
    sent_at = models.DateTimeField(auto_now_add=True)
    sent_success = models.BooleanField(default=False)


class MeetingType(models.Model):
    name = models.CharField(max_length=32)

    def __unicode__(self):
        return self.name


class CCNoticeSend(models.Model):
    meeting = models.ForeignKey(Meeting, related_name="meetingccnotices")
    events = models.ManyToManyField(Event, related_name="meetingccnoticeevents", blank=True)
    sent_at = models.DateTimeField(auto_now_add=True)
    sent_success = models.BooleanField(default=False)
    uuid = models.UUIDField(editable=False, default=uuid.uuid4, blank=True)

    email_to = models.ForeignKey('TargetEmailList', default=get_default_email)

    addtl_message = models.TextField(null=True, blank=True, verbose_name="Additional Message")

    @property
    def subject(self):
        return "Lens and Lights Crew List for %s" % self.meeting.datetime.date()

    @property
    def reverse_ordered_events(self):
        return self.events.order_by('datetime_start')
