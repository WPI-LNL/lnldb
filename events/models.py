import datetime
import decimal

import pytz
from django import forms
# from events.managers import EventManager
# noinspection PyUnresolvedReferences
from django.conf import settings
# Create your models here.
from django.core.urlresolvers import reverse
from django.core.validators import MinLengthValidator
from django.db import models
from django.db.models import Manager
from django.utils import timezone
from django.utils.functional import cached_property

# if settings unset, have sane defaults
if settings.CCR_DAY_DELTA:
    CCR_DELTA = settings.CCR_DAY_DELTA
else:
    CCR_DELTA = 7

PROJECTIONS = (
    ('16', '16mm'),
    ('35', '35mm'),
    ('70', '70mm'),
)


# MANAGERS


def get_level_object(level, etype):
    lo = None
    if etype == 0:  # lighting
        lo = Lighting.objects.get(shortname__endswith=str(level))
    elif etype == 1:  # sound
        lo = Sound.objects.get(shortname__endswith=str(level))
    elif etype == 2:  # projection
        lo = Projection.objects.get(shortname=str(level))

    return lo


def consume_event_method(emethod, methodname):
    level = emethod.pop(methodname)
    reqs = emethod.pop('requirements')

    return level, reqs


class EventManager(models.Manager):
    """ This object consumes the output of the multi step workorder form """

    def consume_workorder_formwiz(self, form_fields, wiz):
        # rip errything out
        form_fields = [form.cleaned_data for form in form_fields]
        contact_fields = form_fields[0]
        org_fields = form_fields[1]
        event_details = form_fields[2]
        event_method_details = form_fields[3:]
        event_schedule = form_fields[-1]

        # break things out
        contact_email = contact_fields['email']
        contact_phone = contact_fields['phone']
        person_name = contact_fields['name']
        person_name_first, person_name_last = person_name.split(' ', 1)

        # group stuff
        group = org_fields['group']

        # set levels
        lighting = None
        sound = None
        projection = None

        # set reqs
        lighting_reqs = None
        sound_reqs = None
        proj_reqs = None

        # other
        otherservices_l = []
        otherdescription = None

        # setup buckets for our extras
        lighting_extras = []
        sound_extras = []
        projection_extras = []

        event_methods = event_details['eventtypes']
        event_name = event_details['eventname']
        location = event_details['location']
        general_description = event_details['general_description']
        event_fund = event_details.get('fund', None)
        event_location = location

        # event_methods
        for emethod, details in zip(event_methods, event_method_details):
            # this totally makes sense
            if emethod == '0':  # lighting
                level, lighting_reqs = consume_event_method(details, 'lighting')
                for k in details:
                    lighting_extras.append((k[2:], details[k]))
                lighting = level

            elif emethod == '1':  # sound
                level, sound_reqs = consume_event_method(details, 'sound')
                for k in details:
                    sound_extras.append((k[2:], details[k]))
                sound = level

            elif emethod == '2':  # projection
                level, proj_reqs = consume_event_method(details, 'projection')
                projection = level

                for k in details:
                    projection_extras.append((k[2:], details[k]))

            elif emethod == '3':  # other
                otherservices_l = details.pop('services')
                otherdescription = details.pop('otherservice_reqs')

        # update contact
        u = wiz.request.user
        u.email = contact_email
        u.first_name = person_name_first
        u.last_name = person_name_last
        u.phone = contact_phone
        u.save()

        # scheduling

        # setup_start = event_schedule['setup_start']
        setup_complete = event_schedule['setup_complete']
        event_start = event_schedule['event_start']
        event_end = event_schedule['event_end']

        event = self.create(
            submitted_by=wiz.request.user,
            contact=wiz.request.user,
            submitted_ip=wiz.request.META['REMOTE_ADDR'],
            event_name=event_name,

            person_name=person_name,
            # org = group, add to another method self.org.add(
            contact_email=contact_email,
            contact_phone=contact_phone,

            # datetime_setup_start = setup_start,
            datetime_setup_complete=setup_complete,
            datetime_start=event_start,
            datetime_end=event_end,

            location=event_location,
            description=general_description,
            billing_fund=event_fund,

            lighting=lighting,
            sound=sound,
            projection=projection,

            lighting_reqs=lighting_reqs,
            sound_reqs=sound_reqs,
            proj_reqs=proj_reqs,

            # otherservices = otherservices_l,
            # otherservice_reqs = otherdescription

        )
        event.org.add(group)
        if otherservices_l:
            event.otherservices.add(*otherservices_l)  # * because its a list yo.
            event.otherservice_reqs = otherdescription

        # raise
        # int(e[1][1]) is int(True) if its valid, which returns 1
        for e in lighting_extras:
            if hasattr(e[1], "__getitem__") and e[1][1]:  # for checkbox
                event.extrainstance_set.create(extra_id=int(e[0]), quant=1)
            elif hasattr(e[1], "__getitem__") and e[1][0]:
                event.extrainstance_set.create(extra_id=int(e[0]), quant=int(e[1][0]))

        for e in sound_extras:
            if hasattr(e[1], "__getitem__") and e[1][1]:  # for checkbox
                event.extrainstance_set.create(extra_id=int(e[0]), quant=1)
            if hasattr(e[1], "__getitem__") and e[1][0]:
                event.extrainstance_set.create(extra_id=int(e[0]), quant=int(e[1][0]))
        for e in projection_extras:
            if hasattr(e[1], "__getitem__") and e[1][0]:
                event.extrainstance_set.create(extra_id=int(e[0]), quant=int(e[1][0]))
        event.save()
        return event


# MODELS

class Building(models.Model):
    """ Used to group locations together in forms """

    name = models.CharField(max_length=128)
    shortname = models.CharField(max_length=4)

    def __unicode__(self):
        # return "<Building (%s,%s)>" % (self.name, self.shortname)
        return self.name

    class Meta:
        ordering = ['name']


class Location(models.Model):
    """ A place where an event, event setup or meeting can happen"""
    name = models.CharField(max_length=64)
    # booleans
    setup_only = models.BooleanField(default=False)
    show_in_wo_form = models.BooleanField(default=True, verbose_name="Event Location")
    available_for_meetings = models.BooleanField(default=False)
    holds_equipment = models.BooleanField(default=False)

    #
    building = models.ForeignKey(Building)

    def __unicode__(self):
        return self.name

    class Meta:
        ordering = ['building', 'name']


class ExtraInstance(models.Model):
    """ An instance of a given extra attached to an event """
    event = models.ForeignKey('Event')
    extra = models.ForeignKey('Extra')
    quant = models.PositiveIntegerField()

    @property
    def totalcost(self):
        return self.quant * self.extra.cost

    @property
    def cost(self):
        return self.extra.cost


class Extra(models.Model):
    """ An additional charge to be added to an event. """
    name = models.CharField(max_length=64)
    cost = models.DecimalField(max_digits=8, decimal_places=2)
    desc = models.TextField()
    services = models.ManyToManyField('Service')
    category = models.ForeignKey('Category')
    disappear = models.BooleanField(default=False, help_text="Disappear this extra instead of disable")
    checkbox = models.BooleanField(default=False, help_text="Use a checkbox instead of an integer entry")

    def __unicode__(self):
        return "%s ($%s)" % (self.name, self.cost)

    @property
    def formfield(self):
        if self.checkbox:
            return forms.BooleanField(),
        else:
            return forms.IntegerField(min_value=0, ),


class Category(models.Model):
    """ A category """
    name = models.CharField(max_length=16)

    def __unicode__(self):
        return self.name


class Service(models.Model):
    """
        Some chargable service that is added to an event,
        lighting, sound, projection are examples
    """
    shortname = models.CharField(max_length=2)
    longname = models.CharField(max_length=64)
    base_cost = models.DecimalField(max_digits=8, decimal_places=2)
    addtl_cost = models.DecimalField(max_digits=8, decimal_places=2)
    category = models.ForeignKey('Category')

    # for the workorder form. Nice And Pretty Descriptions
    help_desc = models.TextField(null=True, blank=True)

    def __unicode__(self):
        return self.longname


class Lighting(Service):
    pass


class Sound(Service):
    pass


class Projection(Service):
    pass


class Billing(models.Model):
    """
        A billing instance that is sent to a client
    """
    date_billed = models.DateField()
    date_paid = models.DateField(null=True, blank=True)
    event = models.ForeignKey('Event', related_name="billings")
    amount = models.DecimalField(max_digits=8, decimal_places=2)

    # bools
    opt_out_initial_email = models.BooleanField(default=False)
    opt_out_update_email = models.BooleanField(default=False)

    def __unicode__(self):
        out = "Bill for %s" % self.event.event_name
        if self.date_paid:
            out += " (PAID)"
        return out

    class Meta:
        ordering = ("-date_billed", "date_paid")


class OptimizedEventManager(Manager):
    def get_queryset(self):
        return super(OptimizedEventManager, self).get_queryset()\
                                                 .select_related('lighting')\
                                                 .select_related('sound')\
                                                 .select_related('projection')


class Event(models.Model):
    """
        An Event, What everything ends up pointing to
    """
    glyphicon = 'bullhorn'
    objects = OptimizedEventManager()
    event_mg = EventManager()

    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='submitter')
    submitted_ip = models.GenericIPAddressField(max_length=16)
    submitted_on = models.DateTimeField(auto_now_add=True, db_index=True)

    event_name = models.CharField(max_length=128, db_index=True)
    # Person
    person_name = models.CharField(max_length=128, null=True, blank=True, verbose_name="Contact_name")  # DEPRECATED
    contact = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, verbose_name="Contact")
    org = models.ManyToManyField('Organization', blank=True, verbose_name="Client")
    billing_org = models.ForeignKey('Organization', null=True, blank=True, related_name="billedevents")
    billing_fund = models.ForeignKey('Fund', null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name="event_accounts")
    contact_email = models.CharField(max_length=180, null=True, blank=True)  # DEPRECATED
    contact_addr = models.TextField(null=True, blank=True)  # DEPRECATED
    contact_phone = models.CharField(max_length=32, null=True, blank=True)  # DEPRECATED

    # Dates & Times
    datetime_setup_start = models.DateTimeField(null=True, blank=True, db_index=True)  # DEPRECATED
    datetime_setup_complete = models.DateTimeField()

    datetime_start = models.DateTimeField(db_index=True)
    datetime_end = models.DateTimeField()

    # Location
    location = models.ForeignKey('Location')

    # service levels
    lighting = models.ForeignKey('Lighting', null=True, blank=True, related_name='lighting')
    sound = models.ForeignKey('Sound', null=True, blank=True, related_name='sound')
    projection = models.ForeignKey('Projection', null=True, blank=True, related_name='projection')

    lighting_reqs = models.TextField(null=True, blank=True)
    sound_reqs = models.TextField(null=True, blank=True)
    proj_reqs = models.TextField(null=True, blank=True)

    description = models.TextField(null=True, blank=True)

    # NOT SHOWN
    otherservices = models.ManyToManyField(Service, blank=True)
    otherservice_reqs = models.TextField(null=True, blank=True)
    setup_location = models.ForeignKey('Location', related_name="setuplocation", null=True, blank=True)  # DEPRECATED
    # Status Indicators
    approved = models.BooleanField(default=False)
    approved_on = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="eventapprovals", null=True, blank=True)

    # billing reviews
    reviewed = models.BooleanField(default=False)
    reviewed_on = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="eventbillingreview", null=True, blank=True)

    closed = models.BooleanField(default=False)
    closed_on = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="eventclosings", null=True, blank=True)

    cancelled = models.BooleanField(default=False)
    cancelled_on = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="eventcancellations", null=True, blank=True)
    cancelled_reason = models.TextField(null=True, blank=True)

    payment_amount = models.IntegerField(blank=True, null=True, default=None)
    paid = models.BooleanField(default=False, db_index=True)

    # reports
    crew_chief = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name='crewchiefx')
    crew = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name='crewx')
    ccs_needed = models.PositiveIntegerField(default=0, db_index=True)
    # ^^^ used as a cache to get around the awkward event type fields and allow for sql filtering

    # other fields
    internal_notes = models.TextField(null=True, blank=True, help_text="Notes that the client and general body should never see.")
    billed_by_semester = models.BooleanField(default=False, db_index=True, help_text="Check if event will be billed in bulk")
    sensitive = models.BooleanField(default=False, help_text="Nobody besides those directly involved should know about this event")
    test_event = models.BooleanField(default=False, help_text="Check to lower the VP's blood pressure after they see the short-notice S4/L4")
    # nice breakout for workorder

    @property
    def person_name(self):
        return self.contact_name

    @property
    def contact_name(self):
        if self.contact:
            return str(self.contact)

    @property
    def contact_phone(self):
        if self.contact:
            return self.contact.phone

    @property
    def contact_email(self):
        if self.contact:
            return self.contact.email

    @property
    def contact_addr(self):
        if self.contact:
            return self.contact.addr

            # def clean(self):
            # if self.datetime_start > self.datetime_end:
            # raise ValidationError('You cannot start after you finish')
            # if self.datetime_setup_complete > self.datetime_start:
            # raise ValidationError('You cannot setup after you finish')
            # if self.datetime_setup_complete < datetime.datetime.now(pytz.utc):
            # raise ValidationError('Stop trying to time travel')

    # implementing calendars
    def save(self, force_insert=False, force_update=False, using=None,
             update_fields=None):
        self.ccs_needed = self.eventcount
        if update_fields:
            update_fields.append('ccs_needed')
        super(Event, self).save(force_insert, force_update, using, update_fields)

    def cal_name(self):
        return self.event_name

    def cal_desc(self):
        desc = ""
        desc += "Requested by "
        orgs = self.org.all()
        for org in orgs:
            desc += org.name + ", "
        desc = desc[:-2] + ".\n"  # removes trailing comma
        ccs = self.ccinstances.all()
        if len(ccs) > 0:
            desc += "Crew Chiefs: "
            for cc in ccs:
                desc += cc.crew_chief.get_full_name() + " [" + cc.service.shortname + "], "
            desc = desc[:-2] + ".\n"  # removes trailing comma
        if self.description:
            desc += self.description + "\n"
        return desc

    def cal_location(self):
        return self.location.name

    def cal_start(self):
        return self.datetime_start

    def cal_end(self):
        return self.datetime_end

    def cal_link(self):
        return "http://lnl.wpi.edu/db/events/view/" + str(self.id)

    def cal_guid(self):
        return "event" + str(self.id) + "@lnldb"

    def firstorg(self):
        return self.org.first()

    def ccreport_url(self):
        return reverse("my-ccreport", args=(self.id,))

    def usercanseeevent(self, user):

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

    # Report Properties
    @property
    def crew_needing_reports(self):
        # chiefs = self.crew_chief.values_list('id','first_name','last_name')
        # chiefs_with_lists = self.ccreport_set.values_list('crew_chief__id',
        # 'crew_chief__first_name','crew_chief__last_name').distinct()
        reports = self.ccreport_set.all().values_list('crew_chief', flat=True)
        pending = self.ccinstances.exclude(crew_chief__in=reports).all()

        # chiefspending
        # chiefs = self.crew_chief.values_list('id')
        # chiefs_with_lists = self.ccreeport_set.values_list('crew_chief').distinct()

        # k =  [u[0] for u in chiefs if u not in chiefs_with_lists]

        # return self.crew_chief.filter(id__in=k)
        return pending

    @property
    def num_crew_needing_reports(self):
        return len(self.crew_needing_reports)

    @property
    def reports_editable(self):

        # tz = timezone.get_current_timezone()

        end = self.datetime_start

        # end_min = datetime.datetime.combine(end.date(), datetime.time.min)
        # end_min = tz.localize(end_min)

        end_plus_time = end + datetime.timedelta(days=CCR_DELTA)
        now = datetime.datetime.now(timezone.get_current_timezone())

        if now < end_plus_time:
            return True
        else:
            return False

    # Service information for templates
    @property
    def allservices(self):
        foo = []
        if self.lighting:
            foo.append({"i": "glyphicon glyphicon-fire", "title": "lighting"})
        if self.sound:
            foo.append({"i": "glyphicon glyphicon-volume-up", "title": "sound"})
        if self.projection:
            foo.append({"i": "glyphicon glyphicon-film", "title": "projection"})
        if self.otherservices:
            foo.append({"i": "glyphicon glyphicon-tasks", "title": "other services"})
        return foo

    @property
    def eventcount(self):
        return len(self.eventservices)

    @property
    def eventservices(self):
        foo = []
        if self.lighting:
            foo.append(self.lighting)
        if self.sound:
            foo.append(self.sound)
        if self.projection:
            foo.append(self.projection)
        try:
            if self.otherservices:
                foo.extend([s for s in self.otherservices.all()])
        except ValueError:
            pass
        return foo

    # Event Statuses
    @cached_property
    def status(self):
        if self.cancelled:
            return "Cancelled"
        elif self.closed:
            return "Closed"
        elif self.approved and self.datetime_setup_complete > datetime.datetime.now(pytz.utc) and not self.reviewed:
            return "Approved"
        elif not self.approved:
            return "Awaiting Approval"
        elif not self.reviewed:
            return "Awaiting Review"
        else:
            if self.paid:
                return "Paid"
            elif self.unpaid:
                return "Awaiting Payment"
            else:
                return "To Be Billed"  # used to be "Open" git #245

    @property
    def unpaid(self):
        return self.billings.filter(date_paid__isnull=True, date_billed__isnull=False)

    @property
    def paid(self):
        return self.billings.filter(date_paid__isnull=False).exists()

    @property
    def over(self):
        return self.datetime_end < datetime.datetime.now(pytz.utc)

    @property
    def late(self):
        return self.datetime_setup_complete - self.submitted_on < datetime.timedelta(weeks=2)

    # Extras And Billing Calculations
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

        return extras + servicecost

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

        return extras + servicecost

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

        return extras + servicecost

    @property
    def services_other(self):
        return self.otherservices.all()

    @property
    def cost_other_services(self):
        return sum([x.base_cost for x in self.services_other])

    @property
    def extras_other(self):
        return self.extrainstance_set.filter(extra__category__name="Misc")

    @property
    def cost_other_extras(self):
        return sum([x.totalcost for x in self.extras_other])

    @property
    def extras_total(self):
        if self.services_other:
            servicecost = self.cost_other_services
        else:
            servicecost = decimal.Decimal("0.00")
        extrascost = self.cost_other_extras
        return extrascost + servicecost

    @property
    def oneoffs(self):
        return self.arbitraryfees.all()

    @property
    def oneoff_total(self):
        return sum([x.totalcost for x in self.oneoffs])

    @property
    def discount_applied(self):
        services = (self.sound, self.lighting)
        service_count = sum([1 for s in services if s])
        if service_count > 1:
            return True
        else:
            return False

    @property
    def cost_total_pre_discount(self):
        return self.cost_projection_total + self.cost_lighting_total + \
            self.cost_sound_total + self.extras_total + self.oneoff_total

    @property
    def discount_value(self):
        if self.discount_applied:
            return decimal.Decimal(self.sound.base_cost + self.lighting.base_cost) * decimal.Decimal(".15")
        else:
            return decimal.Decimal("0.0")

    @property
    def pretty_title(self):
        name = ""
        if self.lighting:
            name += "[" + self.lighting.shortname + "] "
        if self.projection:
            name += "[" + self.projection.shortname + "] "
        if self.sound:
            name += "[" + self.sound.shortname + "] "
        name += self.event_name
        return name

    @property
    def cost_total(self):
        return self.cost_projection_total + self.cost_lighting_total \
            - self.discount_value + self.cost_sound_total + self.extras_total + self.oneoff_total

    # org to be billed
    @property
    def org_to_be_billed(self):
        if not self.billing_org:
            if self.org:
                return self.org.all()[0]
            else:
                return None
        else:
            return self.billing_org

    # figuring out where to show ATTACHMENT AVAILABLE
    @property
    def attachment_for_lighting(self):
        if self.lighting:
            for a in self.attachments.all():
                if self.lighting.service_ptr in a.for_service.all():
                    return True
        return False

    @property
    def attachment_for_sound(self):
        if self.sound:
            for a in self.attachments.all():
                if self.sound.service_ptr in a.for_service.all():
                    return True
        return False

    @property
    def attachment_for_projection(self):
        if self.projection:
            for a in self.attachments.all():
                if self.projection.service_ptr in a.for_service.all():
                    return True
        return False

    @property
    def last_billed(self):
        if self.billings:
            return self.billings.order_by('-date_billed').first().date_billed

    @property
    def times_billed(self):
        if self.billings:
            return self.billings.count()

    @property
    def last_paid(self):
        if self.billings:
            return self.billings.order_by('-date_paid').first().date_billed

    @property
    def short_services(self):
        return ", ".join(map(lambda m: m.shortname, self.eventservices))

    @property
    def datetime_nice(self):
        out_str = ""
        out_str += self.datetime_start.strftime("%a %m/%d/%Y %I:%M %p - ")
        if self.datetime_start.date() == self.datetime_end.date():
            out_str += self.datetime_end.strftime("%I:%M %p")
        else:
            out_str += self.datetime_end.strftime("%a %m/%d/%Y %I:%M %p")
        return out_str

    class Meta:
        permissions = (
            ("view_event", "Show an event that isn't hidden"),
            ("add_raw_event", "Use the editor to create an event"),
            ("event_images", "Upload images to an event"),
            ("view_hidden_event", "Show hidden events"),
            ("cancel_event", "Declare an event to be cancelled"),
            ("event_attachments", "Upload attachments to an event"),
            ("edit_event_times", "Modify the dates for an event"),
            ("add_event_report", "Add reports about the event"),
            ("edit_event_fund", "Change where money for an event comes from"),
            ("view_event_billing", "See financial info for event"),
            ("edit_event_text", "Update any event descriptions"),
            ("adjust_event_owner", "Change the event contact and organization"),
            ("edit_event_hours", "Modify the time sheets"),
            ('edit_event_flags', 'Add flags to an event'),
            ("event_view_sensitive", "Show internal notes and other metadata marked as not public"),
            ("approve_event", "Accept an event"),
            ("decline_event", "Decline an event"),
            ("can_chief_event", "Can crew chief an event"),
            ("review_event", "Review an event for billing"),
            ("adjust_event_charges", "Add charges and change event type"),
            ("bill_event", "Send bills and mark event paid"),
            ("close_event", "Lock an event after everything is done."),
            ("view_test_event", "Show events for testing"),
            ("event_view_granular", "See debug data like ip addresses"),
            ("event_view_debug", "See debug events"),
            ("reopen_event", "Reopen a closed, declined, or cancelled event"),
        )
        ordering = ['-datetime_start']


class CCReport(models.Model):
    glyphicon = 'comment'
    crew_chief = models.ForeignKey(settings.AUTH_USER_MODEL)
    event = models.ForeignKey(Event)
    report = models.TextField(validators=[MinLengthValidator(20)])
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)
    for_service_cat = models.ManyToManyField(Category, verbose_name="Services", blank=True)

    def __unicode__(self):
        return u'%s - %s' % (self.event, self.crew_chief)

    @property
    def pretty_cat_list(self):
        return ", ".join([x.name for x in self.for_service_cat.all()])


# class OrgFund(models.Model):
# fund = models.IntegerField()
# organization = models.IntegerField()
# account = models.IntegerField(default=71973)

# class OrgFund(models.Model):
# fund = models.IntegerField()
# organization = models.IntegerField()
# account = models.IntegerField(default=71973)


class Fund(models.Model):
    glyphicon = 'credit-card'
    fund = models.IntegerField()
    organization = models.IntegerField()
    account = models.IntegerField(default=71973)

    name = models.CharField(max_length=128)
    notes = models.TextField(null=True, blank=True)

    # For future use. Dunno what to do with it yet.
    last_used = models.DateField(null=True)

    last_updated = models.DateField(null=True)

    @property
    def fopal(self):
        return "%s-%s-%s" % self.as_tuple()

    def as_tuple(self):
        return (self.fund, self.organization, self.account)

    def get_absolute_url(self):
        return reverse('orgs:fundedit', args=[self.id])

    def __unicode__(self):
        return "%s (%s)" % (self.name, self.fopal)

    class Meta:
        permissions = (
            ('view_fund', 'View a fund'),
        )


class Organization(models.Model):  # AKA Client
    glyphicon = 'education'
    name = models.CharField(max_length=128, unique=True)
    shortname = models.CharField(max_length=8, null=True, blank=True)
    email = models.EmailField(null=True, blank=True, verbose_name="normal_email_unused")
    exec_email = models.EmailField(null=True, blank=True, verbose_name="Email")

    email_exec = models.BooleanField(default=True)
    email_normal = models.BooleanField(default=False)
    address = models.TextField(null=True, blank=True)
    phone = models.CharField(max_length=32)

    accounts = models.ManyToManyField(Fund, related_name='orgfunds')

    user_in_charge = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='orgowner')
    associated_users = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='orgusers')

    associated_orgs = models.ManyToManyField("self", blank=True, verbose_name="Associated Clients")

    notes = models.TextField(null=True, blank=True)
    personal = models.BooleanField(default=False)

    last_updated = models.DateTimeField(auto_now=True)
    archived = models.BooleanField(default=False)

    @property
    def fopals(self):
        return ", ".join([f.fopal for f in self.accounts.all()])

    def __unicode__(self):
        return self.name

    @property
    def eventcount(self):
        return self.event_set.count()

    @property
    def retname(self):
        return self.shortname or self.name

    def get_absolute_url(self):
        return reverse('orgs:detail', args=[self.id])

    class Meta:
        ordering = ['name']
        verbose_name = "Client"
        verbose_name_plural = "Clients"
        permissions = (('view_org', 'See an Organization\'s basic properties'),
                       ('list_org_events', 'View an Org\'s non-hidden events'),
                       ('list_org_hidden_events', 'View an Org\'s hidden events'),
                       ('edit_org', 'Edit an Org\'s name and description'),
                       ('show_org_billing', 'See an Org\'s account and billing info'),
                       ('edit_org_billing', 'Modify an Org\'s account and billing info'),
                       ('list_org_members', 'View who is in an Org'),
                       ('edit_org_members', 'Edit who is in an Org'),
                       ('create_org_event', 'Create an event in an Org\'s name'),
                       ('view_verifications', 'Show proofs of Org account ownership'),
                       ('create_verifications', 'Create proofs of Org account ownership'),
                       ('transfer_org_ownership', 'Give an Org a new owner'),
                       ('add_org', 'Create an Organization'),
                       ('deprecate_org', 'Mark an Organization as defunct'))


class OrganizationTransfer(models.Model):
    new_user_in_charge = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="xfer_new")
    old_user_in_charge = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="xfer_old")
    org = models.ForeignKey(Organization)
    uuid = models.UUIDField()  # for the link
    created = models.DateTimeField(auto_now=True)
    completed_on = models.DateTimeField(null=True, blank=True)
    expiry = models.DateTimeField(null=True, blank=True)
    completed = models.BooleanField(default=False)

    @property
    def is_expired(self):
        if self.completed:
            return True
        elif datetime.datetime.now(pytz.utc) > self.expiry:
            return True
        return False


class OrgBillingVerificationEvent(models.Model):
    org = models.ForeignKey(Organization, related_name="verifications")
    date = models.DateField()
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="verification_events")
    note = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ['-date', '-id']
        get_latest_by = 'id'


# stats and the like
class Hours(models.Model):
    event = models.ForeignKey('Event', related_name="hours")
    service = models.ForeignKey('Service', related_name="hours", null=True, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="hours")
    hours = models.DecimalField(null=True, max_digits=7, decimal_places=2, blank=True)

    def __unicode__(self):
        return u'%s (%s)' % (self.event, self.user)

    class Meta:
        unique_together = ('event', 'user', 'service')


# this is the crewchief instance for a particular event
class EventCCInstance(models.Model):
    # the pair
    event = models.ForeignKey('Event', related_name="ccinstances")
    crew_chief = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="ccinstances")

    # the service
    service = models.ForeignKey(Service, related_name="ccinstances")
    setup_location = models.ForeignKey(Location, related_name="ccinstances")
    setup_start = models.DateTimeField(null=True, blank=True)

    def cal_name(self):
        return self.event.event_name + " " + self.service.shortname + " Setup"

    def cal_desc(self):
        desc = ""
        desc += "Requested by "
        orgs = self.event.org.all()
        for org in orgs:
            desc += org.name + ", "
        desc = desc[:-2] + ".\n"  # removes trailing comma
        desc += "Crew Chief: " + self.crew_chief.get_full_name() + "\n"
        if self.event.description:
            desc += self.event.description + "\n"
        return desc

    def cal_location(self):
        return self.setup_location.name

    def cal_start(self):
        return self.setup_start

    def cal_end(self):
        if self.event.datetime_setup_complete:
            return self.event.datetime_setup_complete
        else:
            return self.event.datetime_start

    def cal_link(self):
        return "http://lnl.wpi.edu/db/events/view/" + str(self.event.id)

    def cal_guid(self):
        return "setup" + str(self.id) + "@lnldb"

    class Meta:
        ordering = ("-event__datetime_start",)


# A log of CC Report Reminders Sent
class ReportReminder(models.Model):
    event = models.ForeignKey('Event', related_name="ccreportreminders")
    crew_chief = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="ccreportreminders")
    sent = models.DateTimeField(auto_now_add=True)


# for riders, etc
def attachment_file_name(instance, filename):
    return '/'.join(['eventuploads', str(instance.event.id), filename])


class EventAttachment(models.Model):
    event = models.ForeignKey('Event', related_name="attachments")
    for_service = models.ManyToManyField(Service, blank=True, related_name="attachments")
    attachment = models.FileField(upload_to=attachment_file_name)
    note = models.TextField(null=True, blank=True, default="")
    externally_uploaded = models.BooleanField(default=False)


class EventArbitrary(models.Model):
    event = models.ForeignKey('Event', related_name="arbitraryfees")
    key_name = models.CharField(max_length=64)
    key_value = models.DecimalField(max_digits=8, decimal_places=2)
    key_quantity = models.PositiveSmallIntegerField(default=1)

    @property
    def totalcost(self):
        return self.key_value * self.key_quantity

    @property
    def negative(self):
        if self.totalcost > 0:
            return False
        return True

    @property
    def abs_cost(self):
        return abs(self.totalcost)
