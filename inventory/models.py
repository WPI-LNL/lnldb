from django.db import models
from django.contrib.auth.models import User

# Create your models here.

HOME_CHOICES = (
    ('CC','Campus Center'),
    ('AH','Alden Memorial'),
    ('FH','Founders Hall'),
    ('RH','Riley Hall'),
    ('HA','Harrington'),
)

STATUS_CHOICES = (
    ('AV','Available'),
    ('UR','Under Repair'),
    ('RE','Retired'),
)
class Category(models.Model):
    name = models.CharField(max_length=64)
   
    def __unicode__(self):
        return self.name

class SubCategory(models.Model):
    name = models.CharField(max_length=64)
    category = models.ForeignKey('Category')

    def __unicode__(self):
        return self.name

class Status(models.Model):
    name = models.CharField(max_length=32)
    iconclass = models.CharField(max_length=32)
    
    def __unicode__(self):
        return self.name
    
class EquipmentMaintEntry(models.Model):
    ts = models.DateTimeField(auto_now_add=True)
    date = models.DateField(auto_now_add=True)
    
    user = models.ForeignKey(User)
    
    desc = models.CharField(max_length=32)
    entry = models.TextField()
    
    equipment = models.ForeignKey('Equipment')
    status = models.ForeignKey('Status')

    def __unicode__(self):
        return str(self.date)
    
    
    class Meta:
        get_latest_by = "ts"
        ordering = ['-ts']

class Equipment(models.Model):
    name = models.CharField(max_length=256)
    subcategory = models.ForeignKey('SubCategory')
    major = models.BooleanField(default=False)
    description = models.TextField()
    purchase_date = models.DateField()
    purchase_cost = models.DecimalField(max_digits=9, decimal_places=2)
    model_number = models.CharField(max_length=256)
    serial_number = models.CharField(max_length=256)
    road_case = models.CharField(max_length=16)
    manufacturer = models.CharField(max_length=128)
    home = models.CharField(max_length=2,choices=HOME_CHOICES,null=True,blank=True)
    
    def __unicode__(self):
        return self.name
    
    @property
    def status(self):
        latest = self.equipmentmaintentry_set.latest()
        return latest.status
