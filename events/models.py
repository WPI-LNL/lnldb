from django.db import models
from django.contrib.auth.models import User
# Create your models here.

PROJECTIONS = (
    ('16','16mm'),
    ('35','35mm'),
    ('70','70mm'),
)

class Location(models.Model):
    name = models.CharField(max_length=64)
    
    def __unicode__(self):
        return self.name

class Extras(models.Model):
    name = models.CharField(max_length=64)
    cost = models.DecimalField(max_digits=8,decimal_places=2)
    desc = models.TextField()
    
class Services(models.Model):
    shortname = models.CharField(max_length=2)
    longname = models.CharField(max_length=64)
    cost = models.DecimalField(max_digits=8,decimal_places=2)
    extra = models.ManyToManyField('Extras')

class Event(models.Model):
    submitted_by = models.ForeignKey(User,related_name='submitter')
    submitted_ip = models.IPAddressField(max_length=16)
    
    event_name = models.CharField(max_length=128)
    #Person
    person_name = models.CharField(max_length=128,null=True,blank=True,verbose_name="Name")
    group = models.ManyToManyField('Organization',null=True,blank=True)
    contact_email = models.CharField(max_length=256,null=True,blank=True)
    contact_addr = models.TextField(null=True,blank=True)
    contact_phone = models.CharField(max_length=32,null=True,blank=True)

    #Dates & Times
    date_setup_start = models.DateField()
    time_setup_start = models.TimeField()
    time_setup_up = models.TimeField()

    datetime_start = models.DateTimeField()
    datetime_end = models.DateTimeField()

    #Location
    location = models.ForeignKey('Location')

    #Services
    projection = models.CharField(max_length=2,choices=PROJECTIONS,null=True,blank=True)
    
    #service levels
    lighting = models.ForeignKey('Services',null=True,blank=True,related_name='lighting')
    sound = models.ForeignKey('Services',null=True,blank=True,related_name='sound')
    
    extras = models.ManyToManyField('Extras',null=True,blank=True)
    
    description = models.TextField(null=True,blank=True)
    
    #NOT SHOWN
    
    #Status Indicators
    approved = models.BooleanField(default=False)
    closed = models.BooleanField(default=False)
    
    payment_amount = models.IntegerField(blank=True,null=True,default=None)
    paid = models.BooleanField(default=False)
    
    #reports
    crew_chief = models.ManyToManyField(User,null=True,blank=True,related_name='crewchief')
    crew = models.ManyToManyField(User,null=True,blank=True,related_name='crew')
    report = models.TextField(null=True,blank=True)
    
    
    def __unicode__(self):
        return self.event_name
    
#class OrgFund(models.Model):
    #fund = models.IntegerField()
    #organization = models.IntegerField()
    #account = models.IntegerField(default=71973)
    
class Organization(models.Model):
    name = models.CharField(max_length=128,unique=True)
    email = models.EmailField(null=True,blank=True)
    exec_email = models.EmailField(null=True,blank=True)
    
    email_exec = models.BooleanField(default=True)
    email_normal = models.BooleanField(default=False)
    address = models.TextField()
    phone = models.CharField(max_length=32)

    fund = models.IntegerField()
    organization = models.IntegerField()
    account = models.IntegerField(default=71973)
    
    user_in_charge = models.ForeignKey(User,related_name='orgowner')
    associated_users = models.ManyToManyField(User,related_name='orgusers')
    
    associated_orgs = models.ManyToManyField("self",null=True,blank=True)

    def fopal(self):
        return self.fund, self.organization, self.account

    def __unicode__(self):
        return self.name
