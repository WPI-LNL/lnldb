import datetime
import decimal
import hashlib

import pytz
from django import forms
# from events.managers import EventManager
# noinspection PyUnresolvedReferences
from django.conf import settings
# Create your models here.
from django.core.validators import MinLengthValidator
from django.db import models
from django.db.models import Count, Sum
from django.urls.base import reverse
from django.utils import timezone
from django.utils.functional import cached_property
from six import python_2_unicode_compatible
from polymorphic.models import PolymorphicManager, PolymorphicModel
import reversion

# if settings unset, have sane defaults
if settings.CCR_DAY_DELTA:
    CCR_DELTA = settings.CCR_DAY_DELTA
else:
    CCR_DELTA = 30

PROJECTIONS = (
    ('16', '16mm'),
    ('35', '35mm'),
    ('70', '70mm'),
)

AGREEMENT_CHOICES = (
    (-1, 'Not applicable'),
    (0, 'Strongly disagree'),
    (1, 'Disagree'),
    (2, 'Neither agree nor disagree'),
    (3, 'Agree'),
    (4, 'Strongly agree'),
)

EXCELLENCE_CHOICES = (
    (-1, 'Not applicable'),
    (0, 'Poor'),
    (1, 'Fair'),
    (2, 'Good'),
    (3, 'Very good'),
    (4, 'Excellent'),
)


def get_host():
    out = ''
    if settings.SECURE_SSL_REDIRECT:
        out += 'https://'
    else:
        out += 'http://'
    out += settings.ALLOWED_HOSTS[0]
    return out


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
            client_contact=wiz.request.user,
            submitted_ip=wiz.request.META['REMOTE_ADDR'],
            event_name=event_name,

            # datetime_setup_start = setup_start,
            datetime_setup_complete=setup_complete,
            datetime_start=event_start,
            datetime_end=event_end,

            location=event_location,
            description=general_description,

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
class OptimizedEventManager(PolymorphicManager):
    def get_queryset(self):
        return super(OptimizedEventManager, self).get_queryset()\
                                                 .select_related('lighting')\
                                                 .select_related('sound')\
                                                 .select_related('projection')


@python_2_unicode_compatible
@reversion.register(follow=['extrainstance_set', 'arbitraryfees'])
class BaseEvent(PolymorphicModel):
    """
        This parent class is inherited by both Event and Event2019.
        It contains the parts of the old Event model that were kept in Event2019.
        The parts of the old Event model that were _not_ kept in Event2019 remain in the Event model.
    """
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='submitter')
    submitted_ip = models.GenericIPAddressField(max_length=16)
    submitted_on = models.DateTimeField(auto_now_add=True, db_index=True)

    event_name = models.CharField(max_length=128, db_index=True)
    description = models.TextField(null=True, blank=True)
    location = models.ForeignKey('Location', on_delete=models.PROTECT)
    client_contact = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, verbose_name="Client Contact", related_name="client_contact")
    org = models.ManyToManyField('Organization', blank=True, verbose_name="Client", related_name='events')
    billing_org = models.ForeignKey('Organization', on_delete=models.PROTECT, null=True, blank=True, related_name="billedevents")

    datetime_setup_complete = models.DateTimeField()
    datetime_start = models.DateTimeField(db_index=True)
    datetime_end = models.DateTimeField()

    internal_notes = models.TextField(null=True, blank=True, help_text="Notes that the client and general body should never see.")
    billed_in_bulk = models.BooleanField(default=False, db_index=True, help_text="Check if billing of this event will be deferred so that it can be combined with other events in a single invoice")
    sensitive = models.BooleanField(default=False, help_text="Nobody besides those directly involved should know about this event")
    test_event = models.BooleanField(default=False, help_text="Check to lower the VP's blood pressure after they see the short-notice S4/L4")
    
    # Status Indicators
    approved = models.BooleanField(default=False)
    approved_on = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="eventapprovals", null=True, blank=True)

    reviewed = models.BooleanField(default=False)
    reviewed_on = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="eventbillingreview", null=True, blank=True)

    closed = models.BooleanField(default=False)
    closed_on = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="eventclosings", null=True, blank=True)

    cancelled = models.BooleanField(default=False)
    cancelled_on = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="eventcancellations", null=True, blank=True)
    cancelled_reason = models.TextField(null=True, blank=True)

    def __str__(self):
        return self.event_name

    def cal_name(self):
        """ Title to display on calendars """
        return self.event_name
    
    def cal_desc(self):
        """ Event description used by calendars """
        desc = ""
        desc += "Requested by "
        orgs = self.org.all()
        if len(orgs) > 0:
            for org in orgs:
                desc += org.name + ", "
            desc = desc[:-2] + ".\n"  # removes trailing comma
        ccs = self.ccinstances.all()
        if len(ccs) > 0:
            desc += "Crew Chiefs: "
            for cc in ccs:
                desc += cc.crew_chief.get_full_name() + " [" + (cc.service.shortname if cc.service else cc.category.name) + "], "
            desc = desc[:-2] + ".\n"  # removes trailing comma
        if self.description:
            desc += self.description + "\n"
        return desc

    def cal_location(self):
        """ Location data to display on calendars """
        return self.location.name

    def cal_start(self):
        """ Start time used by calendars """
        return self.datetime_start

    def cal_end(self):
        """ End time used by calendars """
        return self.datetime_end

    def cal_link(self):
        """ Link to display on calendars """
        return get_host() + reverse('events:detail', args=[self.id])

    def cal_guid(self):
        """ Unique event id for use by calendars """
        return "event" + str(self.id) + "@lnldb"

    @property
    def crew_needing_reports(self):
        """ List of crew chiefs who have not yet submitted a CC report """
        reports = self.ccreport_set.all().values_list('crew_chief', flat=True)
        return self.ccinstances.exclude(crew_chief__in=reports)

    @property
    def num_crew_needing_reports(self):
        return len(self.crew_needing_reports)

    @property
    def reports_editable(self):
        """ Returns false if too much time has elapsed since the end of the event """
        end_plus_time = self.datetime_end + datetime.timedelta(days=CCR_DELTA)
        return timezone.now() < end_plus_time
    
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
        return self.billings.filter(date_paid__isnull=True, date_billed__isnull=False).exists() \
            or self.multibillings.filter(date_paid__isnull=True, date_billed__isnull=False).exists()

    @property
    def paid(self):
        return self.billings.filter(date_paid__isnull=False).exists() \
            or self.multibillings.filter(date_paid__isnull=False).exists()

    @property
    def over(self):
        return self.datetime_end < datetime.datetime.now(pytz.utc)

    @property
    def late(self):
        return self.datetime_setup_complete - self.submitted_on < datetime.timedelta(weeks=2)
    
    @property
    def oneoffs(self):
        return self.arbitraryfees.all()

    @property
    def oneoff_total(self):
        return sum([x.totalcost for x in self.oneoffs])
    
    @property
    def org_to_be_billed(self):
        if not self.billing_org:
            return self.org.all()[0] if self.org.exists() else None
        else:
            return self.billing_org

    @property
    def last_billed(self):
        if self.billings.exists():
            return self.billings.order_by('-date_billed').first().date_billed
        elif self.multibillings.exists():
            return self.multibillings.order_by('-date_billed').first().date_billed

    @property
    def last_bill(self):
        return self.billings.order_by('-date_billed').first()

    @property
    def times_billed(self):
        return self.billings.count() + self.multibillings.count()

    @property
    def last_paid(self):
        paid_bills = self.billings.filter(date_paid__isnull=False)
        if paid_bills.exists():
            return paid_bills.order_by('-date_paid').first().date_paid
        paid_multibills = self.multibillings.filter(date_paid__isnull=False)
        if paid_multibills.exists():
            return paid_multibills.order_by('-date_paid').first().date_paid

    @property
    def datetime_nice(self):
        out_str = ""
        out_str += self.datetime_start.strftime("%a %m/%d/%Y %I:%M %p - ")
        if self.datetime_start.date() == self.datetime_end.date():
            out_str += self.datetime_end.strftime("%I:%M %p")
        else:
            out_str += self.datetime_end.strftime("%a %m/%d/%Y %I:%M %p")
        return out_str

    @property
    def has_projection(self):
        assert False, 'You did not implement has_projection in your subclass!'

    @property
    def eventservices(self):
        assert False, 'You did not implement eventservices in your subclass!'

    @property
    def short_services(self):
        assert False, 'You did not implement short_services in your subclass!'

    @property
    def eventcount(self):
        assert False, 'You did not implement eventcount in your subclass!'

    class Meta:
        verbose_name = 'Event'
        permissions = (
            ("view_events", "Show an event that isn't hidden"),
            ("add_raw_event", "Use the editor to create an event"),
            ("event_images", "Upload images to an event"),
            ("view_hidden_event", "Show hidden events"),
            ("cancel_event", "Declare an event to be cancelled"),
            ("event_attachments", "Upload attachments to an event"),
            ("edit_event_times", "Modify the dates for an event"),
            ("add_event_report", "Add reports about the event"),
            ("edit_event_fund", "Change where money for an event comes from"),
            ("view_event_billing", "See financial info for event"),
            ("view_event_reports", "See reports for event"),
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


# do not use ignore_duplicates=True because it does not follow relations
@reversion.register(follow=['baseevent_ptr'])
class Event(BaseEvent):
    """
        An Event, What everything ends up pointing to

        This model is full of old garbage that was not kept in Event2019. Let it rest in peace.
    """
    glyphicon = 'bullhorn'
    objects = OptimizedEventManager()
    event_mg = EventManager()

    person_name = models.CharField(max_length=128, null=True, blank=True, verbose_name="Contact_name")  # DEPRECATED
    contact_email = models.CharField(max_length=180, null=True, blank=True)  # DEPRECATED
    contact_addr = models.TextField(null=True, blank=True)  # DEPRECATED
    contact_phone = models.CharField(max_length=32, null=True, blank=True)  # DEPRECATED

    # Dates & Times
    datetime_setup_start = models.DateTimeField(null=True, blank=True, db_index=True)  # DEPRECATED
    
    # service levels
    lighting = models.ForeignKey('Lighting', on_delete=models.PROTECT, null=True, blank=True, related_name='lighting')
    sound = models.ForeignKey('Sound', on_delete=models.PROTECT, null=True, blank=True, related_name='sound')
    projection = models.ForeignKey('Projection', on_delete=models.PROTECT, null=True, blank=True, related_name='projection')

    lighting_reqs = models.TextField(null=True, blank=True)
    sound_reqs = models.TextField(null=True, blank=True)
    proj_reqs = models.TextField(null=True, blank=True)

    # NOT SHOWN
    otherservices = models.ManyToManyField('Service', blank=True)
    otherservice_reqs = models.TextField(null=True, blank=True)
    setup_location = models.ForeignKey('Location', on_delete=models.PROTECT, related_name="setuplocation", null=True, blank=True)  # DEPRECATED

    payment_amount = models.IntegerField(blank=True, null=True, default=None)

    # reports
    crew_chief = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name='crewchiefx')
    crew = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name='crewx')
    ccs_needed = models.PositiveIntegerField(default=0, db_index=True)
    # ^^^ used as a cache to get around the awkward event type fields and allow for sql filtering

    # nice breakout for workorder

    @property
    def person_name(self):
        return self.contact_name

    @property
    def contact_name(self):
        if self.client_contact:
            return str(self.client_contact)

    @property
    def contact_phone(self):
        if self.client_contact:
            return self.client_contact.phone

    @property
    def contact_email(self):
        if self.client_contact:
            return self.client_contact.email

    @property
    def contact_addr(self):
        if self.client_contact:
            return self.client_contact.addr

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

    def firstorg(self):
        return self.org.first()

    def ccreport_url(self):
        return reverse("my:report", args=(self.id,))

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
    def short_services(self):
        return ", ".join(map(lambda m: m.shortname, self.eventservices))

    @property
    def has_projection(self):
        return self.projection is not None

    class Meta:
        verbose_name = '2012 Event'


# do not use ignore_duplicates=True because it does not follow relations (and is slow)
@reversion.register(follow=['baseevent_ptr'])
class Event2019(BaseEvent):
    """
        New events under the 2019 pricelist
    """

    # Workday billing
    workday_fund = models.IntegerField(null=True, blank=True, choices=(
        (810, 'Student Organization (810-FD)'),
        (110, 'Operating (110-FD)'),
        (220, 'Gift (220-FD)'),
        (250, 'Gift (250-FD)'),
        (500, 'Gift (500-FD)'),
        (210, 'Grant (210-FD)'),
        (900, 'Project (900-FD)'),
        (120, 'Designated (120-FD)'),
    ))
    worktag = models.CharField(max_length=10, null=True, blank=True)
    workday_form_comments = models.TextField(null=True, blank=True)
    workday_entered_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                           related_name="workdayentries", null=True, blank=True)
    entered_into_workday = models.BooleanField(
        default=False,
        help_text='Checked when the Treasurer has created an Internal Service Delivery in Workday for this event'
    )

    # Post-event survey
    send_survey = models.BooleanField(
        default=True, help_text='Check if the event contact should be emailed the post-event survey after the event'
    )
    survey_sent = models.BooleanField(default=False, help_text='The post-event survey has been sent to the client')

    # Added during COVID pandemic
    max_crew = models.PositiveIntegerField(null=True, blank=True)

    # 25live integration
    reference_code = models.CharField(max_length=12, null=True, blank=True,
            help_text="The 25Live reference code, found on the event page")
    event_id = models.IntegerField(null=True, blank=True, 
        help_text="The 25Live event ID. If not provided, it will be generated from the reference code.")

    @property
    def has_projection(self):
        return self.serviceinstance_set.filter(service__category__name='Projection').exists()

    @property
    def eventservices(self):
        return Service.objects.filter(serviceinstance__in=self.serviceinstance_set.all())

    @property
    def short_services(self):
        return ", ".join(self.eventservices.values_list('shortname', flat=True))

    @property
    def eventcount(self):
        """ Number of different `types` of services provided (based on category) """
        return self.serviceinstance_set.aggregate(Count('service__category', distinct=True))['service__category__count']

    @property
    def services_total(self):
        services_cost = self.serviceinstance_set.aggregate(Sum('service__base_cost'))['service__base_cost__sum']
        return services_cost if services_cost is not None else 0

    @property
    def extras_total(self):
        total = 0
        for extra_instance in self.extrainstance_set.all():
            total += extra_instance.totalcost
        return total

    @property
    def cost_total_pre_discount(self):
        return self.services_total + self.extras_total + self.oneoff_total

    @property
    def discount_applied(self):
        categories = ['Lighting', 'Sound']
        categories = [Category.objects.get(name=name) for name in categories]
        for category in categories:
            if not self.serviceinstance_set.filter(service__category=category).exists():
                return False
        return True

    @property
    def discount_value(self):
        if self.discount_applied:
            categories = ['Lighting', 'Sound']
            categories = [Category.objects.get(name=name) for name in categories]
            discountable_total = decimal.Decimal(
                self.serviceinstance_set.filter(service__category__in=categories).aggregate(Sum('service__base_cost'))[
                    'service__base_cost__sum']) + self.extras_total
            return discountable_total * decimal.Decimal(".15")
        else:
            return decimal.Decimal("0.0")

    @property
    def cost_total(self):
        return self.cost_total_pre_discount - self.discount_value

    @property
    def workday_form_hash(self):
        return hashlib.sha1((
            settings.SECRET_KEY +
            type(self).__name__ +
            'workday_form' +
            str(self.pk) +
            str(self.org_to_be_billed.pk if self.org_to_be_billed is not None else None) +
            str(self.workday_fund) +
            str(self.worktag)
            ).encode('utf-8')).hexdigest()

    # Service glyphicon for templates
    @property
    def allservices(self):
        foo = []
        if self.serviceinstance_set.filter(service__category=Category.objects.get(name="Lighting")).exists():
            foo.append({"i": "glyphicon glyphicon-fire", "title": "lighting"})
        if self.serviceinstance_set.filter(service__category=Category.objects.get(name="Sound")).exists():
            foo.append({"i": "glyphicon glyphicon-volume-up", "title": "sound"})
        if self.serviceinstance_set.filter(service__category=Category.objects.get(name="Projection")).exists():
            foo.append({"i": "glyphicon glyphicon-film", "title": "projection"})
        if self.serviceinstance_set.filter(service__category=Category.objects.get(name="Misc")).exists():
            foo.append({"i": "glyphicon glyphicon-tasks", "title": "misc services"})
        return foo

    class Meta:
        verbose_name = '2019 Event'

    
@python_2_unicode_compatible
class Building(models.Model):
    """ Used to group locations together in forms """

    name = models.CharField(max_length=128)
    shortname = models.CharField(max_length=4)

    def __str__(self):
        # return "<Building (%s,%s)>" % (self.name, self.shortname)
        return self.name

    class Meta:
        ordering = ['name']


@python_2_unicode_compatible
class Location(models.Model):
    """ A place where an event, event setup or meeting can happen"""
    name = models.CharField(max_length=64)
    # booleans
    setup_only = models.BooleanField(default=False)
    show_in_wo_form = models.BooleanField(default=True, verbose_name="Event Location")
    available_for_meetings = models.BooleanField(default=False)
    holds_equipment = models.BooleanField(default=False)

    #
    building = models.ForeignKey(Building, on_delete=models.CASCADE)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['building', 'name']


@reversion.register()
class ExtraInstance(models.Model):
    """ An instance of a given extra attached to an event """
    event = models.ForeignKey(BaseEvent, on_delete=models.CASCADE)
    extra = models.ForeignKey('Extra', on_delete=models.PROTECT)
    quant = models.PositiveIntegerField()

    @property
    def totalcost(self):
        return self.quant * self.extra.cost

    @property
    def cost(self):
        return self.extra.cost


@python_2_unicode_compatible
class Extra(models.Model):
    """ An additional item or service to be added to an event (i.e. mirror ball) """
    name = models.CharField(max_length=64)
    cost = models.DecimalField(max_digits=8, decimal_places=2)
    desc = models.TextField()
    services = models.ManyToManyField('Service')
    category = models.ForeignKey('Category', on_delete=models.PROTECT)
    disappear = models.BooleanField(default=False, help_text="Disappear this extra instead of disable")
    checkbox = models.BooleanField(default=False, help_text="Use a checkbox instead of an integer entry")

    def __str__(self):
        return "%s ($%s)" % (self.name, self.cost)

    @property
    def formfield(self):
        if self.checkbox:
            return forms.BooleanField(),
        else:
            return forms.IntegerField(min_value=0, ),


@python_2_unicode_compatible
class Category(models.Model):
    """ A category """
    name = models.CharField(max_length=16)

    def __str__(self):
        return self.name


@python_2_unicode_compatible
class Service(models.Model):
    """
        Some chargable service that is added to an event;
        lighting, sound, projection are examples
    """
    shortname = models.CharField(max_length=2)
    longname = models.CharField(max_length=64)
    base_cost = models.DecimalField(max_digits=8, decimal_places=2)
    addtl_cost = models.DecimalField(max_digits=8, decimal_places=2)
    category = models.ForeignKey('Category', models.PROTECT)

    # for the workorder form. Nice And Pretty Descriptions
    help_desc = models.TextField(null=True, blank=True)

    # Enable/disable for different types of events
    enabled_event2012 = models.BooleanField(default=False, verbose_name='Enabled for 2012 Events')
    enabled_event2019 = models.BooleanField(default=True, verbose_name='Enabled for 2019 Events')

    def __str__(self):
        return self.longname


# No longer used in Event2019
class Lighting(Service):
    pass


# No longer used in Event2019
class Sound(Service):
    pass


# No longer used in Event2019
class Projection(Service):
    pass


@python_2_unicode_compatible
class ServiceInstance(models.Model):
    """
        An instance of a service associated with a specific event.
        Created with Event2019
    """
    service = models.ForeignKey('Service', on_delete=models.PROTECT)
    event = models.ForeignKey('BaseEvent', on_delete=models.CASCADE)
    detail = models.TextField(blank=True)

    def __str__(self):
        return '{} for {}'.format(str(self.service), str(self.event))
    

@python_2_unicode_compatible
class Billing(models.Model):
    """
        A billing instance that is sent to a client
    """
    date_billed = models.DateField()
    date_paid = models.DateField(null=True, blank=True)
    event = models.ForeignKey(BaseEvent, on_delete=models.CASCADE, related_name="billings")
    amount = models.DecimalField(max_digits=8, decimal_places=2)

    def __str__(self):
        out = "Bill for %s" % self.event.event_name
        if self.date_paid:
            out += " (PAID)"
        return out

    class Meta:
        ordering = ("-date_billed", "date_paid")


@python_2_unicode_compatible
class MultiBilling(models.Model):
    """
        A billing instance for multiple events that is sent to a client
    """
    date_billed = models.DateField()
    date_paid = models.DateField(null=True, blank=True)
    org = models.ForeignKey('Organization', on_delete=models.PROTECT, null=True, related_name='multibillings')
    events = models.ManyToManyField(BaseEvent, related_name='multibillings')
    amount = models.DecimalField(max_digits=8, decimal_places=2)

    def __str__(self):
        out = 'MultiBill for ' + ', '.join(map(lambda event : event.event_name, self.events.all()))
        if self.date_paid:
            out += ' (PAID)'
        return out

    class Meta:
        ordering = ('-date_billed', 'date_paid')


@python_2_unicode_compatible
class BillingEmail(models.Model):
    """ Billing information used in an email sent to a client """
    billing = models.ForeignKey('Billing', on_delete=models.CASCADE)
    subject = models.CharField(max_length=128)
    message = models.TextField()
    email_to_users = models.ManyToManyField(settings.AUTH_USER_MODEL)
    email_to_orgs = models.ManyToManyField('Organization')
    sent_at = models.DateTimeField(null=True)

    def __str__(self):
        return 'Billing email sent %s for %s' % (self.sent_at if self.sent_at is not None else 'never',
                                                 self.billing.event.event_name)


@python_2_unicode_compatible
class MultiBillingEmail(models.Model):
    """ Billing information used in an email sent to a client (multiple events) """
    multibilling = models.ForeignKey('MultiBilling', on_delete=models.CASCADE)
    subject = models.CharField(max_length=128)
    message = models.TextField()
    email_to_users = models.ManyToManyField(settings.AUTH_USER_MODEL)
    email_to_orgs = models.ManyToManyField('Organization')
    sent_at = models.DateTimeField(null=True)

    def __str__(self):
        return 'MultiBilling email sent %s for %s' % (
            self.sent_at if self.sent_at is not None else 'never',
            ', '.join(map(lambda event : event.event_name, self.multibilling.events.all())))


@python_2_unicode_compatible
class CCReport(models.Model):
    """ Crew Chief post-event report """
    glyphicon = 'comment'
    crew_chief = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    event = models.ForeignKey(BaseEvent, on_delete=models.CASCADE)
    report = models.TextField(validators=[MinLengthValidator(20)])
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)
    for_service_cat = models.ManyToManyField(Category, verbose_name="Services", blank=True)

    def __str__(self):
        return u'%s - %s' % (self.event, self.crew_chief)

    @property
    def pretty_cat_list(self):
        """ Generates a nice list of the respective service categories """
        return ", ".join([x.name for x in self.for_service_cat.all()])


@python_2_unicode_compatible
class Organization(models.Model):
    """ AKA: A Client """
    glyphicon = 'education'
    name = models.CharField(max_length=128, unique=True)
    shortname = models.CharField(max_length=8, null=True, blank=True)
    email = models.EmailField(null=True, blank=True, verbose_name="normal_email_unused")
    exec_email = models.EmailField(null=True, verbose_name="Email")

    email_exec = models.BooleanField(default=True)
    email_normal = models.BooleanField(default=False)
    address = models.TextField(null=True, blank=True)
    phone = models.CharField(max_length=32)

    workday_fund = models.IntegerField(null=True, blank=True, choices=(
        (810, 'Student Organization (810-FD)'),
        (110, 'Operating (110-FD)'),
        (220, 'Gift (220-FD)'),
        (250, 'Gift (250-FD)'),
        (500, 'Gift (500-FD)'),
        (210, 'Grant (210-FD)'),
        (900, 'Project (900-FD)'),
        (120, 'Designated (120-FD)'),
    ))
    worktag = models.CharField(max_length=10, null=True, blank=True)

    user_in_charge = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='orgowner')
    associated_users = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='orgusers')

    associated_orgs = models.ManyToManyField("self", blank=True, verbose_name="Associated Clients")

    notes = models.TextField(null=True, blank=True)
    personal = models.BooleanField(default=False)
    delinquent = models.BooleanField(default=False)

    last_updated = models.DateTimeField(auto_now=True)
    archived = models.BooleanField(default=False)

    locked = models.BooleanField(default=False, blank=True)

    def __str__(self):
        return self.name

    @property
    def eventcount(self):
        return self.events.count()

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
                       ('deprecate_org', 'Mark an Organization as defunct'),
                       ('view_org_notes', 'View internal notes for an org'))


class OrganizationTransfer(models.Model):
    """ Record of a transfer of ownership between two users for a particular organization """
    initiator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="xfer_initiated")
    new_user_in_charge = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="xfer_new")
    old_user_in_charge = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="xfer_old")
    org = models.ForeignKey(Organization, on_delete=models.CASCADE)
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
    org = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="verifications")
    date = models.DateField()
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                    related_name="verification_events")
    note = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ['-date', '-id']
        get_latest_by = 'id'


# stats and the like
@python_2_unicode_compatible
class Hours(models.Model):
    """ Number of hours a particular crew member put in working at a particular event """
    event = models.ForeignKey(BaseEvent, on_delete=models.CASCADE, related_name="hours")
    category = models.ForeignKey(Category, on_delete=models.PROTECT, null=True, blank=True, related_name='hours')
    service = models.ForeignKey('Service', on_delete=models.PROTECT, related_name="hours", null=True, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="hours")
    hours = models.DecimalField(null=True, max_digits=7, decimal_places=2, blank=True)

    def __str__(self):
        return u'%s (%s)' % (self.event, self.user)

    class Meta:
        unique_together = ('event', 'user', 'service')


class EventCCInstance(models.Model):
    """ This is the crew chief instance for a particular event """
    # the pair
    event = models.ForeignKey(BaseEvent, on_delete=models.CASCADE, related_name='ccinstances')
    crew_chief = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ccinstances')

    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='ccinstances')
    service = models.ForeignKey(Service, on_delete=models.PROTECT, null=True, related_name='ccinstances')
    setup_location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name='ccinstances')
    setup_start = models.DateTimeField(null=True, blank=True)

    def cal_name(self):
        """ Title used by calendars """
        return self.event.event_name + ' ' + (self.service.shortname if self.service else self.category.name) + ' Setup'

    def cal_desc(self):
        """ Description used by calendars """
        desc = ''
        desc += 'Requested by '
        orgs = self.event.org.all()
        for org in orgs:
            desc += org.name + ', '
        desc = desc[:-2] + '.\n'  # removes trailing comma
        desc += 'Crew Chief: ' + self.crew_chief.get_full_name() + '\n'
        if self.event.description:
            desc += self.event.description + '\n'
        return desc

    def cal_location(self):
        """ Location used by calendars """
        return self.setup_location.name

    def cal_start(self):
        """ Start time used by calendars (setup) """
        return self.setup_start

    def cal_end(self):
        """ End time used by calendars """
        if self.event.datetime_setup_complete:
            return self.event.datetime_setup_complete
        else:
            return self.event.datetime_start

    def cal_link(self):
        """ Link to display on calendars """
        return get_host() + reverse('events:detail', args=[self.event.id])

    def cal_guid(self):
        """ Unique event id used by calendars """
        return 'setup' + str(self.id) + '@lnldb'

    class Meta:
        ordering = ('-event__datetime_start',)


class ReportReminder(models.Model):
    """ A log of CC Report Reminders sent """
    event = models.ForeignKey(BaseEvent, on_delete=models.CASCADE, related_name="ccreportreminders")
    crew_chief = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ccreportreminders")
    sent = models.DateTimeField(auto_now_add=True)


# for riders, etc
def attachment_file_name(instance, filename):
    return '/'.join(['eventuploads', str(instance.event.id), filename])


class EventAttachment(models.Model):
    event = models.ForeignKey(BaseEvent, on_delete=models.CASCADE, related_name="attachments")
    for_service = models.ManyToManyField(Service, blank=True, related_name="attachments")
    attachment = models.FileField(upload_to=attachment_file_name)
    note = models.TextField(null=True, blank=True, default="")
    externally_uploaded = models.BooleanField(default=False)


@reversion.register()
class EventArbitrary(models.Model):
    """ Additional "OneOff" charges (i.e. rentals, additional fees) """
    event = models.ForeignKey(BaseEvent, on_delete=models.CASCADE, related_name="arbitraryfees")
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


@python_2_unicode_compatible
class PostEventSurvey(models.Model):
    """ Survey sent to clients after an event to collect their feedback """
    # metadata
    event = models.ForeignKey(BaseEvent, on_delete=models.PROTECT, related_name="surveys")
    person = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='surveys')

    # survey questions
    services_quality = models.IntegerField(
        choices=EXCELLENCE_CHOICES,
        verbose_name='Please rate the overall quality of the services Lens and Lights provided.'
    )
    lighting_quality = models.IntegerField(
        choices=EXCELLENCE_CHOICES, verbose_name='How satisfied were you with the lighting?'
    )
    sound_quality = models.IntegerField(
        choices=EXCELLENCE_CHOICES, verbose_name='How satisfied were you with the sound system?'
    )
    work_order_method = models.IntegerField(choices=(
        (None, 'Please select...'),
        (1, 'Via the website at lnl.wpi.edu/workorder'),
        (2, 'Emailed lnl@wpi.edu'),
        (3, 'Emailed an LNL representative directly'),
        (4, 'By phone'),
        (5, 'In person'),
        (0, 'Other'),
        (-1, 'I don\'t know')
    ), verbose_name='How did you submit the workorder?')
    work_order_experience = models.IntegerField(
        choices=EXCELLENCE_CHOICES, verbose_name='How would you rate your overall experience using the workorder tool?',
        null=True, blank=True, default=-1
    )
    work_order_ease = models.IntegerField(
        choices=EXCELLENCE_CHOICES, verbose_name='How would you rate the workorder tool\'s clarity and ease of use?',
        null=True, blank=True, default=-1
    )
    work_order_comments = models.TextField(
        blank=True,
        verbose_name="Please provide any additional comments you may have regarding your experience with the workorder "
                     "tool. Is there anything you would like to see us improve?"
    )

    # survey agreement questions
    communication_responsiveness = models.IntegerField(
        choices=AGREEMENT_CHOICES, verbose_name='Lens and Lights was responsive to my communications.'
    )
    pricelist_ux = models.IntegerField(
        choices=AGREEMENT_CHOICES,
        verbose_name='It was easy to determine which services to request and I had no problem finding what I needed.'
    )
    setup_on_time = models.IntegerField(
        choices=AGREEMENT_CHOICES, verbose_name='My event was set up and the crew was ready on time.'
    )
    crew_respectfulness = models.IntegerField(
        choices=AGREEMENT_CHOICES, verbose_name='When interacting with the crew, they were helpful and respectful.'
    )
    price_appropriate = models.IntegerField(
        choices=AGREEMENT_CHOICES,
        verbose_name='The price quoted for the event matched my expectations and was appropriate for the services provided.'
    )
    customer_would_return = models.IntegerField(
        choices=AGREEMENT_CHOICES, verbose_name='I would use Lens and Lights in the future.'
    )

    # textarea questions
    comments = models.TextField(blank=True, verbose_name='Please use this area to provide any additional feedback you '
                                                         'may have about your event.')

    def __str__(self):
        return 'Post-event survey for {} by {}'.format(self.event, self.person)

    class Meta:
        permissions = (
            ("view_posteventsurveyresults", "View post-event survey results"),
        )
        ordering = ['event', 'person']


@python_2_unicode_compatible
class Workshop(models.Model):
    """ A Workshop series hosted by LNL """
    name = models.CharField(max_length=128)
    instructors = models.CharField(max_length=100)
    description = models.TextField()
    location = models.CharField(max_length=100)
    notes = models.TextField(null=True, blank=True)

    class Meta:
        permissions = (
            ("edit_workshops", "Modify workshops"),
        )

    def __str__(self):
        return self.name


class WorkshopDate(models.Model):
    workshop = models.ForeignKey(Workshop, on_delete=models.CASCADE, related_name='dates')
    date = models.DateTimeField()


DAYS_OF_WEEK = (
    (0, 'Sunday'),
    (1, 'Monday'),
    (2, 'Tuesday'),
    (3, 'Wednesday'),
    (4, 'Thursday'),
    (5, 'Friday'),
    (6, 'Saturday')
)


@python_2_unicode_compatible
class OfficeHour(models.Model):
    """ A listing for an officer's Office Hours """
    officer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    day = models.IntegerField(choices=DAYS_OF_WEEK)
    hour_start = models.TimeField(auto_now=False, auto_now_add=False, verbose_name="Start Time")
    hour_end = models.TimeField(auto_now=False, auto_now_add=False, verbose_name="End Time")
    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name="office_hours")

    def __str__(self):
        return self.officer.first_name + " " + self.officer.last_name + " - " + self.get_day_display()

    @property
    def get_day(self):
        return self.get_day_display()

    class Meta:
        permissions = (
            ('manage_hours', 'Manage Office Hours'),
        )
        verbose_name = "Office Hour"


class CrewAttendanceRecord(models.Model):
    """ Checkin and checkout times for a crew member attending an event """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="event_records")
    event = models.ForeignKey(Event2019, on_delete=models.SET_NULL, null=True, related_name="crew_attendance")
    checkin = models.DateTimeField(default=timezone.now)
    checkout = models.DateTimeField(blank=True, null=True)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.user.name + " - " + self.event.event_name
