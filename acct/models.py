from django.db import models
from django.contrib.auth.models import User
# Create your models here.

class Profile(models.Model):
    user = models.OneToOneField(User)
    
    wpibox = models.IntegerField(null=True,blank=True)
    phone = models.CharField(max_length=24,null=True,blank=True)
    addr = models.TextField(null=True,blank=True)
    
    @property
    def fullname(self):
        return self.user.first_name + " " + self.user.last_name