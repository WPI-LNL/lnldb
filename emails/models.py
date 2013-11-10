from django.db import models
from events.models import Event

# Create your models here.

class MeetingNoticeMail(models.Model):
    ts = models.DateTimeField(auto_now_add=True)
    
    place = models.CharField(max_length=32,default="AK219")
    time = models.TimeField(default="17:00")
    date = models.DateField()
    
    note = models.TextField()
    
    start_param = models.DateField()
    end_param = models.DateField()
    
    sent=models.BooleanField(default=False)