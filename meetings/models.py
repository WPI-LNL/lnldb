from django.db import models
from django.contrib.auth.models import User

# Create your models here.


class Meeting(models.Model):
    datetime = models.DateTimeField()
    attendance = models.ManyToManyField(User)
    meeting_type = models.ForeignKey('MeetingType',default=1)
    
    def __unicode__(self):
        return "Meeting For %s" % self.datetime.date()

class MeetingType(models.Model):
    name = models.CharField(max_length=32)
    def __unicode__(self):
        return self.name