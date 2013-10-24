from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save

# Create your models here.
PIT_CHOICES = (
    ('P1','PIT1'),
    ('P2','PIT2'),
    ('P3','PIT3'),
    ('P4','PIT4'),
    ('P5','PIT5'),
    ('PP','Past Practical'),
    ('L','Licensed'),        
)

class Projectionist(models.Model):
    user = models.OneToOneField(User)
    pit_level = models.CharField(choices=PIT_CHOICES,max_length=2,null=True,blank=True)
    
    license_number = models.CharField(max_length=10, null=True, blank=True)
    license_expiry = models.DateField(null=True, blank=True)
    
def create_projectionist(sender, instance, created, **kwargs):
    if created:
        Projectionist.objects.create(user=instance)

post_save.connect(create_projectionist, sender=User)
