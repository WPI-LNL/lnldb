from django.db import models
from django.contrib.auth.models import User

from events.models import Event, Location
# Create your models here.

from uuidfield import UUIDField


def get_default_email():
    return TargetEmailList.objects.get(email="lnlnews@wpi.edu")

class Meeting(models.Model):
    datetime = models.DateTimeField()
    attendance = models.ManyToManyField(User,null=True,blank=True)
    meeting_type = models.ForeignKey('MeetingType',default=1)
    location = models.ForeignKey('events.Location',null=True,blank=True)
    
    def __unicode__(self):
        return "Meeting For %s" % self.datetime.date()
    
    class Meta:
        ordering = ('-datetime',)
    
class MeetingAnnounce(models.Model):
    meeting = models.ForeignKey(Meeting)
    events = models.ManyToManyField(Event,related_name="meetingannouncements")
    subject = models.CharField(max_length=128)
    message = models.TextField()
    email_to = models.ForeignKey('TargetEmailList')
    
    added = models.DateTimeField(auto_now_add=True)
    uuid = UUIDField(auto=True,editable=False, null=True,blank=True)
    
    @property
    def reverse_ordered_events(self):
        return self.events.order_by('datetime_start')
    
    
class TargetEmailList(models.Model):
    name = models.CharField(max_length=16)
    email = models.EmailField()
    
    def __unicode__(self):
        return "<EmailList (%s)>" % self.email
    
class AnnounceSend(models.Model):
    announce = models.ForeignKey(MeetingAnnounce)
    sent_at = models.DateTimeField(auto_now_add=True)
    sent_success = models.BooleanField(default=False)
    

class MeetingType(models.Model):
    name = models.CharField(max_length=32)
    def __unicode__(self):
        return self.name
    
class CCNoticeSend(models.Model):
    meeting = models.ForeignKey(Meeting,related_name="meetingccnotices")
    events = models.ManyToManyField(Event,related_name="meetingccnoticeevents")
    sent_at = models.DateTimeField(auto_now_add=True)
    sent_success = models.BooleanField(default=False)
    uuid = UUIDField(auto=True,editable=False, null=True,blank=True)
    
    email_to = models.ForeignKey('TargetEmailList', default=get_default_email)
    
    addtl_message = models.TextField(null=True, blank=True, verbose_name="Additional Message")
    
    @property
    def reverse_ordered_events(self):
        return self.events.order_by('datetime_start')