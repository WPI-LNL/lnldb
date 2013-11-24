from django.db import models
from django.contrib.auth.models import User
from django.contrib.auth.models import Group
from django.db.models.signals import post_save

# Create your models here.


class StatusChange(models.Model):
    member = models.ForeignKey(User,related_name="statuschange")
    groups = models.ManyToManyField(Group,related_name="statuschange")
    date = models.DateTimeField(auto_now_add=True)
    
    
#def update_status(sender,instance,created,raw,using,update_fields,**kwargs):
    #if not created:
        #print update_fields
        #adfad
        
#post_save.connect(update_status,sender=User)