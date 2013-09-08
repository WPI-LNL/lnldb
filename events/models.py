from django.db import models
#from events.managers import EventManager
from django.contrib.auth.models import User
# Create your models here.

PROJECTIONS = (
    ('16','16mm'),
    ('35','35mm'),
    ('70','70mm'),
)

##MANAGERS

def get_level_object(level,etype):
    if etype == 0: #lighting
        lo = Lighting.objects.get(shortname__endswith=str(level))
    elif etype == 1: #sound
        lo = Sound.objects.get(shortname__endswith=str(level))
    elif etype == 2: #projection
        lo = Projection.objects.get(shortname=str(level))
        
    return lo

def consume_event_method(emethod,methodname):
    level = emethod.pop(methodname)
    reqs = emethod.pop('requirements')
    
    return level,reqs

class EventManager(models.Manager):
    
    def consume_workorder_formwiz(self,form_fields,wiz):
        #rip errything out
        form_fields = [form.cleaned_data for form in form_fields]
        contact_fields = form_fields[0]
        org_fields = form_fields[1]
        event_details = form_fields[2]
        event_method_details = form_fields[3:]
        event_schedule = form_fields[-1]
        
        #break things out
        contact_email = contact_fields['email']
        contact_phone = contact_fields['phone']
        person_name = contact_fields['name']
        
        #group stuff
        group = Organization.objects.get(pk=1) #do this later
        
        #set levels
        lighting = None
        sound = None
        projection = None
        
        #set reqs
        lighting_reqs = None
        sound_reqs = None
        proj_reqs = None
        
        #setup buckets for our extras
        lighting_extras = []
        sound_extras = []
        
        event_methods = event_details['eventtypes']
        event_name = event_details['eventname']
        location = event_details['location']
        event_location = location
        
        #event_methods
        for emethod,details in zip(event_methods,event_method_details):
            #this totally makes sense
            if emethod == '0': #lighting
                level,lighting_reqs = consume_event_method(details,'lighting')
                for k in details:
                    lighting_extras.append((k[2:],details[k]))
                lighting = level
                
            elif emethod == '1': #sound
                level,sound_reqs = consume_event_method(details,'sound')
                for k in details:
                    sound_extras.append((k[2:],details[k]))
                sound = level
                    
            elif emethod == '2': #projection
                level,proj_reqs = consume_event_method(details,'projection')
                projection = level
        
        #scheduling
        
        setup_start = event_schedule['setup_start']
        setup_complete = event_schedule['setup_complete']
        event_start = event_schedule['event_start']
        event_end = event_schedule['event_end']
        
        event =  self.create(
            submitted_by = wiz.request.user,
            submitted_ip = wiz.request.META['REMOTE_ADDR'],
            event_name = event_name,
            
            person_name = person_name,
            #org = group, add to another method self.org.add(
            contact_email = contact_email,
            contact_phone = contact_phone,
            
            datetime_setup_start = setup_start,
            datetime_setup_complete = setup_complete,
            datetime_start = event_start,
            datetime_end = event_end,
            
            location = event_location,
            
            lighting = lighting,
            sound = sound,
            projection = projection,
            
            lighting_reqs = lighting_reqs,
            sound_reqs = sound_reqs,
            proj_reqs = proj_reqs,
            
            )
        return event
            
### MODELS

class Location(models.Model):
    name = models.CharField(max_length=64)
    
    def __unicode__(self):
        return self.name

class ExtraInstance(models.Model):
    event = models.ForeignKey('Event')
    extra = models.ForeignKey('Extra')
    quant = models.IntegerField()
    
    @property
    def totalcost(self):
        return self.quant * self.extra.cost
    @property
    def cost(self):
        return self.extra.cost
    
class Extra(models.Model):
    name = models.CharField(max_length=64)
    cost = models.DecimalField(max_digits=8,decimal_places=2)
    desc = models.TextField()
    services = models.ManyToManyField('Service')
    category = models.ForeignKey('Category')    
    def __unicode__(self):
        return self.name
    
class Category(models.Model):
    name = models.CharField(max_length=16)
    
    def __unicode__(self):
        return self.name
class Service(models.Model):
    shortname = models.CharField(max_length=2)
    longname = models.CharField(max_length=64)
    base_cost = models.DecimalField(max_digits=8,decimal_places=2)
    addtl_cost = models.DecimalField(max_digits=8,decimal_places=2)
    category = models.ForeignKey('Category')    
    def __unicode__(self):
        return self.shortname
    
class Lighting(Service):
    pass
class Sound(Service):
    pass
class Projection(Service):
    pass

class Event(models.Model):
    
    objects = models.Manager()
    event_mg = EventManager()
    
    submitted_by = models.ForeignKey(User,related_name='submitter')
    submitted_ip = models.IPAddressField(max_length=16)
    submitted_on = models.DateTimeField(auto_now_add=True)
    
    event_name = models.CharField(max_length=128)
    #Person
    person_name = models.CharField(max_length=128,null=True,blank=True,verbose_name="Name")
    org = models.ManyToManyField('Organization',null=True,blank=True)
    contact_email = models.CharField(max_length=256,null=True,blank=True)
    contact_addr = models.TextField(null=True,blank=True)
    contact_phone = models.CharField(max_length=32,null=True,blank=True)

    #Dates & Times
    datetime_setup_start = models.DateTimeField()
    datetime_setup_complete = models.DateTimeField()

    datetime_start = models.DateTimeField()
    datetime_end = models.DateTimeField()

    #Location
    location = models.ForeignKey('Location')

    #service levels
    lighting = models.ForeignKey('Lighting',null=True,blank=True,related_name='lighting')
    sound = models.ForeignKey('Sound',null=True,blank=True,related_name='sound')
    projection = models.ForeignKey('Projection',null=True,blank=True,related_name='projection')
    
    lighting_reqs = models.TextField(null=True,blank=True)
    sound_reqs = models.TextField(null=True,blank=True)
    proj_reqs=models.TextField(null=True,blank=True)
    
    description = models.TextField(null=True,blank=True)
    
    #NOT SHOWN
    
    #Status Indicators
    approved = models.BooleanField(default=False)
    closed = models.BooleanField(default=False)
    
    payment_amount = models.IntegerField(blank=True,null=True,default=None)
    paid = models.BooleanField(default=False)
    
    #reports
    crew_chief = models.ManyToManyField(User,null=True,blank=True,related_name='crewchiefx')
    crew = models.ManyToManyField(User,null=True,blank=True,related_name='crewx')
    
    
    
    def usercanseeevent(self,user):
        
        if user in self.crew_chief.all():
            return True
        elif user in self.crew.all():
            return True
        else:
            eventorgs = self.return_orgs_and_associates()
            for org in eventorgs:
                if org.user_in_charge == user:
                    return True
                elif user in org.associated_users:
                    return True
                    
            
        return False
        
    def return_orgs_and_associates(self):
        out = []
        orgs = self.org.all()
        out.extend(orgs)
        for org in orgs:
            out.extend(org.associated_orgs.all())
            
        return out
            
    
    def __unicode__(self):
        return self.event_name
    
    class Meta:
        ordering = ['-datetime_start']
        
    @property
    def crew_needing_reports(self):
        #chiefs = self.crew_chief.values_list('id','first_name','last_name')
        #chiefs_with_lists = self.ccreport_set.values_list('crew_chief__id','crew_chief__first_name','crew_chief__last_name').distinct()
        chiefs = self.crew_chief.values_list('id')
        chiefs_with_lists = self.ccreport_set.values_list('crew_chief').distinct()
        
        k =  [u[0] for u in chiefs if u not in chiefs_with_lists]
        
        return self.crew_chief.filter(id__in=k)
        #return k
        
    @property
    def extras_lighting(self):
        return self.extrainstance_set.filter(extra__category__name="Lighting")
    
    @property
    def cost_lighting_extras(self):
        return sum([x.totalcost for x in self.extras_lighting])
    
    @property
    def cost_lighting_total(self):
        extras = self.cost_lighting_extras
        if self.lighting:
            servicecost = self.lighting.base_cost
        else:
            servicecost = 0
            
        return extras+servicecost
    
    @property
    def extras_sound(self):
        return self.extrainstance_set.filter(extra__category__name="Sound")
    
    @property
    def cost_sound_extras(self):
        return sum([x.totalcost for x in self.extras_sound])
    
    @property
    def cost_sound_total(self):
        extras = self.cost_sound_extras
        if self.sound:
            servicecost = self.sound.base_cost
        else:
            servicecost = 0
            
        return extras+servicecost
    
    @property
    def extras_projection(self):
        return self.extrainstance_set.filter(extra__category__name="Projection")
    
    @property
    def cost_projection_extras(self):
        return sum([x.totalcost for x in self.extras_projection])
    
    @property
    def cost_projection_total(self):
        extras = self.cost_projection_extras
        if self.projection:
            servicecost = self.projection.base_cost
        else:
            servicecost = 0
            
        return extras+servicecost
    
    def cost_total(self):
        return self.cost_projection_total + self.cost_lighting_total + self.cost_projection_total
    
class CCReport(models.Model):
    crew_chief = models.ForeignKey(User)
    event = models.ForeignKey(Event)
    report = models.TextField()
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)
    for_service_cat = models.ManyToManyField(Category)
    
    
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
    address = models.TextField(null=True,blank=True)
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
    
    ordering = ['name']
    
    



