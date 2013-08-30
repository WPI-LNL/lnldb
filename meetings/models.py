from django.db import models
from django.contrib.auth.models import User

from events.models import Event
# Create your models here.


class Meeting(models.Model):
    datetime = models.DateTimeField()
    attendance = models.ManyToManyField(User)
    meeting_type = models.ForeignKey('MeetingType',default=1)
    
    def __unicode__(self):
        return "Meeting For %s" % self.datetime.date()
    
class MeetingAnnounce(models.Model):
    meeting = models.ForeignKey(Meeting)
    events = models.ManyToManyField(Event,related_name="meetingannouncements")
    message = models.TextField()
    
class TargetEmailList(models.Model):
    name = models.CharField(max_length=16)
    email = models.EmailField()
    
class AnnounceSend(models.Model):
    announce = models.ForeignKey(MeetingAnnounce)
    sent_at = models.DateTimeField(auto_now_add=True)
    send_to = models.ForeignKey(TargetEmailList)
    sent_success = models.BooleanField(default=False)
    

class MeetingType(models.Model):
    name = models.CharField(max_length=32)
    def __unicode__(self):
        return self.name