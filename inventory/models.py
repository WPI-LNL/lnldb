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

class EquipmentMaintEntry(models.Model):
    date = models.DateField(auto_now_add=True)
    user = models.ForeignKey(User)
    entry = models.TextField()
    equipment = models.ForeignKey('Equipment')

    def __unicode__(self):
        return self.date

class Equipment(models.Model):
    name = models.CharField(max_length=256)
    subcategory = models.ForeignKey('SubCategory')
    major = models.BooleanField(default=False)
    description = models.TextField()
    purchase_date = models.DateField()
    purchase_price = models.IntegerField()
    model_number = models.CharField(max_length=256)
    serial_number = models.CharField(max_length=256)
    road_case = models.CharField(max_length=16)
    manufacturer = models.CharField(max_length=128)
    home = models.CharField(max_length=2,choices=HOME_CHOICES,null=True,blank=True)
    equip_status = models.CharField(max_length=2,choices=STATUS_CHOICES,default='AV')
    
    def __unicode__(self):
        return self.name
