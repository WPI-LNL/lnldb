from django.db import models
from django.db.models import Q
from django.contrib.auth.models import User
from django.db.models.signals import post_save
# Create your models here.

class Profile(models.Model):
    user = models.OneToOneField(User)
    
    wpibox = models.IntegerField(null=True,blank=True,verbose_name="WPI Box Number")
    phone = models.CharField(max_length=24,null=True,blank=True, verbose_name="Phone Number")
    addr = models.TextField(null=True,blank=True, verbose_name="Address / Office Location")
    mdc = models.CharField(max_length=32,null=True,blank=True, verbose_name="MDC")
    
    locked = models.BooleanField(default=False)
    @property
    def fullname(self):
        return self.user.first_name + " " + self.user.last_name
    
    @property
    def is_lnl(self):
        if self.user.groups.filter(Q(name="Alumni")|Q(name="Active")|Q(name="Officer")|Q(name="Associate")|Q(name="Away")|Q(name="Inactive")).exists():
            return True
        else:
            return False
    
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)
        # if not email, this solves issue #138
        if not instance.email:
            instance.email = "%s@wpi.edu" % instance.username 
            instance.save()

post_save.connect(create_user_profile, sender=User)

class Orgsync_OrgCat(models.Model):
    name = models.CharField(max_length=64)
    orgsync_id = models.IntegerField()
    def __unicode__(self):
        return "<OrgSyncOrgCat (%s)>" % self.name
class Orgsync_Org(models.Model):
    orgsync_id = models.IntegerField()
    name = models.CharField(max_length=128)
    category = models.ForeignKey(Orgsync_OrgCat,null=True,blank=True)
    keywords = models.TextField(null=True,blank=True)
    president_email = models.EmailField(null=True,blank=True)
    org_email = models.EmailField(null=True,blank=True)
    def __unicode__(self):
        return "<OrgSyncOrg (%s)>" % self.name
class Orgsync_User(models.Model):
    orgsync_id  = models.IntegerField()
    title = models.CharField(max_length=256,null=True,blank=True)
    account_id = models.IntegerField()
    first_name = models.CharField(max_length=128)
    last_name = models.CharField(max_length=128)
    email_address = models.EmailField()
    memberships = models.ManyToManyField(Orgsync_Org,null=True,blank=True)
    last_login = models.DateField(null=True,blank=True)
    about_me = models.TextField(null=True,blank=True)
    portfolio=models.CharField(max_length=256,null=True,blank=True)
    
    def __unicode__(self):
        return "<OrgSyncUser (%s,%s)>" % (self.first_name,self.last_name)
    
#example {"id":918421,"title":null,"account_id":575310,"first_name":"Aakriti","last_name":"Bhakhri","picture_url_40":"https://d1nrm4vx8nf098.cloudfront.net/eupwtt1qw06izh_40.jpg","picture_url_60":"https://d1nrm4vx8nf098.cloudfront.net/eupwtt1qw06izh_64.jpg","memberships":[{"id":152541,"name":"Members"}],"email_address":"aakriti@wpi.edu","last_login":"April 24, 2012","portfolio":"http://my.orgsync.com/aakritibhakhri"},
#url https://orgsync.com/38382/accounts?per_page=100&num_pages=3&order=first_name+ASC
#paginatd https://orgsync.com/38382/accounts?per_page=100&num_pages=3&order=first_name+ASC&page=46
#profile https://orgsync.com/profile/display_profile?id=636887
#profile2 https://orgsync.com/profile/display_profile?id=575310
#b.open("https://orgsync.com/38382/groups")
#b.open("https://orgsync.com/38382/accounts?per_page=100&num_pages=3&order=first_name+ASC")