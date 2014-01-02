from django.db import models
#from events.managers import EventManager
from django.contrib.auth.models import User
# Create your models here.
from django.core.exceptions import ValidationError
from django.core.urlresolvers import reverse
import datetime,pytz

from uuidfield import UUIDField

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
        group = org_fields['group']
        
        #set levels
        lighting = None
        sound = None
        projection = None
        
        #set reqs
        lighting_reqs = None
        sound_reqs = None
        proj_reqs = None
        
        #other
        otherservices_l = []
        otherdescription = None
        
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
            elif emethod == '3': #other
                otherservices_l = details.pop('services')
                otherdescription = details.pop('otherservice_reqs')
        
        #scheduling
        
        #setup_start = event_schedule['setup_start']
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
            
            #datetime_setup_start = setup_start,
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
            
            #otherservices = otherservices_l, 
            #otherservice_reqs = otherdescription
            
            )
        event.org.add(group)
        if otherservices_l:
            event.otherservices.add(*otherservices_l) #* because its a list yo.
            event.otherservice_reqs = otherdescription
        event.save()
        return event
            
### MODELS

class Building(models.Model):
    name = models.CharField(max_length=128)
    shortname = models.CharField(max_length=4)
    
    def __unicode__(self):
        #return "<Building (%s,%s)>" % (self.name, self.shortname)
        return self.name
    
    class Meta:
        ordering = ['name']
    
class Location(models.Model):
    name = models.CharField(max_length=64)
    setup_only = models.BooleanField(default=False)
    show_in_wo_form = models.BooleanField(default=True,verbose_name="Active Location")
    building = models.ForeignKey(Building)
    
    def __unicode__(self):
        return self.name

    class Meta:
        ordering = ['building','name']
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
    
    #for the workorder form. Nice And Pretty Descriptions
    help_desc = models.TextField(null=True,blank=True)
    
    def __unicode__(self):
        return self.longname
    
class Lighting(Service):
    pass
class Sound(Service):
    pass
class Projection(Service):
    pass
    
class Billing(models.Model):
    date_billed = models.DateField()
    date_paid = models.DateField(null=True,blank=True)
    event = models.ForeignKey('Event',related_name="billings")
    amount = models.DecimalField(max_digits=8,decimal_places=2)

    class Meta:
        ordering = ("-date_billed","date_paid")
        
        
class Event(models.Model):
    
    objects = models.Manager()
    event_mg = EventManager()
    
    submitted_by = models.ForeignKey(User,related_name='submitter')
    submitted_ip = models.IPAddressField(max_length=16)
    submitted_on = models.DateTimeField(auto_now_add=True)
    
    event_name = models.CharField(max_length=128)
    #Person
    person_name = models.CharField(max_length=128,null=True,blank=True,verbose_name="Client")
    org = models.ManyToManyField('Organization',null=True,blank=True)
    contact_email = models.CharField(max_length=256,null=True,blank=True)
    contact_addr = models.TextField(null=True,blank=True)
    contact_phone = models.CharField(max_length=32,null=True,blank=True)

    #Dates & Times
    datetime_setup_start = models.DateTimeField(null=True,blank=True)
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
    otherservices = models.ManyToManyField(Service,null=True,blank=True)
    otherservice_reqs = models.TextField(null=True,blank=True)
    setup_location = models.ForeignKey('Location',related_name="setuplocation",null=True,blank=True)
    #Status Indicators
    approved = models.BooleanField(default=False)
    approved_on = models.DateTimeField(null=True,blank=True)
    approved_by = models.ForeignKey(User,related_name="eventapprovals",null=True,blank=True)
    
    closed = models.BooleanField(default=False)
    closed_on = models.DateTimeField(null=True,blank=True)
    closed_by = models.ForeignKey(User,related_name="eventclosings",null=True,blank=True)
    
    cancelled = models.BooleanField(default=False)
    cancelled_on = models.DateTimeField(null=True,blank=True)
    cancelled_by = models.ForeignKey(User,related_name="eventcancellations",null=True,blank=True)
    cancelled_reason = models.TextField(null=True,blank=True)
    
    payment_amount = models.IntegerField(blank=True,null=True,default=None)
    paid = models.BooleanField(default=False)
    
    #reports
    crew_chief = models.ManyToManyField(User,null=True,blank=True,related_name='crewchiefx')
    crew = models.ManyToManyField(User,null=True,blank=True,related_name='crewx')
    
    #def clean(self):
        #if self.datetime_start > self.datetime_end:
            #raise ValidationError('You cannot start after you finish')
        #if self.datetime_setup_complete > self.datetime_start:
            #raise ValidationError('You cannot setup after you finish')
        ##if self.datetime_setup_complete < datetime.datetime.now(pytz.utc):
            ##raise ValidationError('Stop trying to time travel')
    
    def firstorg(self):
        return self.org.all()[0]
    
    def ccreport_url(self):
        return reverse("my-ccreport",args=(self.id,))
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
                elif user in org.associated_users.all():
                    return True
                    
            instances = self.ccinstances.all()
            for i in instances:
                if user == i.crew_chief:
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
    def allservices(self):
        foo = []
        if self.lighting:
            foo.append({"i":"icon-fire","title":"lighting"})
        if self.sound:O
            foo.append({"i":"icon-volume-up","title":"sound"})
        if self.projection:
            foo.append({"i":"icon-film","title":"projection"})
        if self.otherservices:
            foo.append({"i":"icon-tasks","title":"other services"})
        return foo
    
    @property
    def eventservices(self):
        foo = []
        if self.lighting:
            foo.append(self.lighting)
        if self.sound:
            foo.append(self.sound)
        if self.projection:
            foo.append(self.projection)
        if self.otherservices:
            foo.extend([s for s in self.otherservices.all()])
        return foo
    
    @property
    def status(self):
        if self.cancelled:
            return "Cancelled"
        elif self.closed:
            return "Closed"
        elif self.approved and self.datetime_setup_complete > datetime.datetime.now(pytz.utc):
            return "Approved"
        else:
            if self.paid:
                return "Paid"
            elif self.unpaid:
                return "Awaiting Payment"
            else:
                return "Open"
        
    @property
    def unpaid(self):
        return self.billings.filter(date_paid__isnull=True,date_billed__isnull=False)
    @property
    def paid(self):
        return self.billings.filter(date_paid__isnull=False).exists()
    
    @property
    def over(self):
        return self.datetime_end < datetime.datetime.now(pytz.utc)
    
    ### Extras And Money
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
    
    @property
    def cost_total(self):
        return self.cost_projection_total + self.cost_lighting_total + self.cost_sound_total
    
class CCReport(models.Model):
    crew_chief = models.ForeignKey(User)
    event = models.ForeignKey(Event)
    report = models.TextField()
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)
    for_service_cat = models.ManyToManyField(Category,verbose_name="Services")
    
    @property
    def pretty_cat_list(self):
        return ", ".join([x.name for x in self.for_service_cat.all()])
    
#class OrgFund(models.Model):
    #fund = models.IntegerField()
    #organization = models.IntegerField()
    #account = models.IntegerField(default=71973)
    
class Organization(models.Model):
    name = models.CharField(max_length=128,unique=True)
    shortname = models.CharField(max_length=8,null=True,blank=True)
    email = models.EmailField(null=True,blank=True)
    exec_email = models.EmailField(null=True,blank=True)
    
    email_exec = models.BooleanField(default=True)
    email_normal = models.BooleanField(default=False)
    address = models.TextField(null=True,blank=True)
    phone = models.CharField(max_length=32)

    fund = models.IntegerField()
    organization = models.IntegerField()
    account = models.IntegerField(default=0)
    
    user_in_charge = models.ForeignKey(User,related_name='orgowner')
    associated_users = models.ManyToManyField(User,related_name='orgusers')
    
    associated_orgs = models.ManyToManyField("self",null=True,blank=True)
    
    
    notes = models.TextField(null=True,blank=True)
    personal = models.BooleanField(default=False)
    
    last_updated = models.DateTimeField(auto_now=True)

    @property
    def fopal(self):
        return "%s-%s-%s" % (self.fund, self.organization, self.account)

    def __unicode__(self):
        return self.name
    
    @property
    def eventcount(self):
        return self.event_set.count()
    
    class Meta:
        ordering = ['name']
        
        
class OrganizationTransfer(models.Model):
    new_user_in_charge = models.ForeignKey(User,related_name="xfer_new")
    old_user_in_charge = models.ForeignKey(User,related_name="xfer_old")
    org = models.ForeignKey(Organization)
    uuid = UUIDField(auto=True) #for the link
    created = models.DateTimeField(auto_now_add=True,auto_now=True)
    completed_on = models.DateTimeField(null=True,blank=True)
    expiry = models.DateTimeField(null=True,blank=True)
    completed = models.BooleanField(default=False)
    
    @property
    def is_expired(self):
        if self.completed:
            return True
        elif datetime.datetime.now(pytz.utc) > self.expiry:
            return True
        return False
    
    
# stats and the like
class Hours(models.Model):
    event = models.ForeignKey('Event',related_name="hours")
    user = models.ForeignKey(User,related_name="hours")
    hours = models.DecimalField(null=True, max_digits=7, decimal_places=2, blank=True)
    
    class Meta:
        unique_together = ('event','user')
    
    
# this is the crewchief instance for a particular event
class EventCCInstance(models.Model):
    # the pair
    event = models.ForeignKey('Event', related_name="ccinstances")
    crew_chief = models.ForeignKey(User, related_name="ccinstances")
    
    # the service
    service = models.ForeignKey(Service,related_name = "ccinstances")
    setup_location = models.ForeignKey(Location, related_name="ccinstances")
    setup_start = models.DateTimeField(null=True,blank=True)
