import logging
import zoneinfo
from django.urls import reverse
from django.contrib.auth.models import Permission, Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from django.conf import settings
from django.http import QueryDict
from django.test import TestCase
from django.test.client import RequestFactory
from data.tests.util import ViewTestCase
from django.utils import timezone

from .generators import CCReportFactory, EventFactory, Event2019Factory, UserFactory, OrgFactory, CCInstanceFactory, \
    ServiceFactory, LocationFactory
from .. import models, lookups, cal
from ..templatetags import append_get, at_event_linking, gpa_scale_emoji


logging.disable(logging.WARNING)


class EventBasicViewTest(ViewTestCase):
    def setup(self):
        self.e = EventFactory.create(event_name="Test Event")
        self.e2 = EventFactory.create(event_name="Other Test Event")
        self.e3 = Event2019Factory.create(event_name="2019 Test Event")
        self.report = CCReportFactory.create(event=self.e)
        self.org = OrgFactory.create(name="Test Org")

    def test_detail(self):
        self.setup()

        self.e2.sensitive = True
        self.e2.save()

        # By default, user should not have permission to view event details
        self.assertOk(self.client.get(reverse('events:detail', args=[self.e.pk])), 403)

        permission = Permission.objects.get(codename="view_events")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("events:detail", args=[self.e.pk])))

        # Check that you need permission to view a sensitive event
        self.assertOk(self.client.get(reverse("events:detail", args=[self.e2.pk])), 403)

        permission = Permission.objects.get(codename="view_hidden_event")
        self.user.user_permissions.add(permission)

        # Check that we get no errors when including survey results (will need permission)
        permission = Permission.objects.get(codename="view_posteventsurveyresults")
        self.user.user_permissions.add(permission)

        models.PostEventSurvey.objects.create(event=self.e, person=self.user, services_quality=1, lighting_quality=2,
                                              sound_quality=3, work_order_method=1, work_order_experience=4,
                                              work_order_ease=1, communication_responsiveness=0, pricelist_ux=1,
                                              setup_on_time=2, crew_respectfulness=3, price_appropriate=4,
                                              customer_would_return=4, comments="Things were alright")
        models.PostEventSurvey.objects.create(event=self.e2, person=self.user, services_quality=-1,
                                              lighting_quality=-1, sound_quality=-1, work_order_method=2,
                                              work_order_experience=-1, work_order_ease=-1, pricelist_ux=-1,
                                              communication_responsiveness=-1, setup_on_time=-1, crew_respectfulness=-1,
                                              price_appropriate=-1, customer_would_return=-1)

        self.assertOk(self.client.get(reverse("events:detail", args=[self.e.pk])))
        self.assertOk(self.client.get(reverse("events:detail", args=[self.e2.pk])))

    def test_new_event(self):
        self.setup()
        self.assertOk(self.client.get(reverse("events:new")), 403)

        permission = Permission.objects.get(codename="add_raw_event")
        self.user.user_permissions.add(permission)

        # Will also need the following for adjusting required fields
        permission = Permission.objects.get(codename="edit_event_times")
        self.user.user_permissions.add(permission)

        permission = Permission.objects.get(codename="edit_event_text")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("events:new")))

        building = models.Building.objects.create(name="Fuller Laboratories", shortname="FL")
        booth = models.Location.objects.create(name="Booth", building=building)
        category = models.Category.objects.create(name="Lighting")
        service = ServiceFactory.create(category=category)
        valid_data = {
            "event_name": "New Event",
            "location": str(booth.pk),
            "description": "A new test event for stuff",
            "internal_notes": "",
            "max_crew": 1,
            "billed_in_bulk": False,
            "sensitive": False,
            "test_event": True,
            "entered_into_workday": False,
            "send_survey": True,
            "org": "|",
            "reference_code": "",
            "datetime_setup_complete_0": timezone.now().date(),
            "datetime_setup_complete_1": timezone.now().time(),
            "datetime_start_0": timezone.now().date(),
            "datetime_start_1": timezone.now().time(),
            "datetime_end_0": timezone.now().date(),
            "datetime_end_1": timezone.now().time(),
            "serviceinstance_set-TOTAL_FORMS": 1,
            "serviceinstance_set-INITIAL_FORMS": 0,
            "serviceinstance_set-MIN_NUM_FORMS": 0,
            "serviceinstance_set-MAX_NUM_FORMS": 1000,
            "serviceinstance_set-0-id": '',
            "serviceinstance_set-0-service": str(service.pk),
            "serviceinstance_set-0-detail": "Services for things and stuff",
            "save": "Save Changes"
        }

        self.assertRedirects(self.client.post(reverse("events:new"), valid_data), reverse("events:detail", args=[4]))

        self.assertTrue(models.Event2019.objects.filter(event_name="New Event").exists())

    def test_edit(self):
        self.setup()

        category = models.Category.objects.create(name="Projection")
        proj = models.Projection.objects.create(longname="Digital Projection", shortname="DP", base_cost=100.00,
                                                addtl_cost=5.00, category=category)
        self.e.projection = proj
        self.e.reviewed = True
        self.e.save()

        self.assertOk(self.client.get(reverse('events:edit', args=[self.e.pk])), 403)

        permission = Permission.objects.get(codename="view_events")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse('events:edit', args=[self.e.pk])))

        CCInstanceFactory.create(crew_chief=self.user, event=self.e)

        # Bad input
        self.assertOk(self.client.post(reverse('events:edit', args=[self.e.pk])), status_code=400)

        building = models.Building.objects.create(name="Fuller Laboratories", shortname="FL")
        booth = models.Location.objects.create(name="Booth", building=building)
        valid_data = {
            "event_name": "Edited event",
            "location": str(booth.pk),
            "description": "A new test event for stuff",
            "internal_notes": "",
            "billed_in_bulk": False,
            "sensitive": False,
            "test_event": False,
            "org": "|",
            "datetime_setup_complete_0": timezone.now().date(),
            "datetime_setup_complete_1": timezone.now().time(),
            "datetime_start_0": timezone.now().date(),
            "datetime_start_1": timezone.now().time(),
            "datetime_end_0": timezone.now().date(),
            "datetime_end_1": timezone.now().time(),
            "save": "Save Changes"
        }

        self.assertRedirects(self.client.post(reverse('events:edit', args=[self.e.pk]), valid_data),
                             reverse('events:detail', args=[self.e.pk]))

        self.e.refresh_from_db()
        self.assertEqual(self.e.event_name, "Edited event")

    def test_cancel(self):
        self.setup()

        # Only POST should be permitted
        self.assertOk(self.client.get(reverse("events:cancel", args=[self.e.pk])), 405)

        # By default user should not have permission to cancel events
        self.assertOk(self.client.post(reverse("events:cancel", args=[self.e.pk])), 403)

        permission = Permission.objects.get(codename="cancel_event")
        self.user.user_permissions.add(permission)

        # Will also need view_event permissions for redirect
        permission = Permission.objects.get(codename="view_events")
        self.user.user_permissions.add(permission)

        self.assertRedirects(self.client.post(reverse("events:cancel", args=[self.e.pk])),
                             reverse("events:detail", args=[self.e.pk]))

        self.e.refresh_from_db()
        self.assertTrue(self.e.cancelled)

        # Test with event contact
        self.e.contact = self.user
        self.e.save()
        self.assertRedirects(self.client.post(reverse("events:cancel", args=[self.e.pk])),
                             reverse("events:detail", args=[self.e.pk]))

        # Redirects to detail page if already closed
        self.e.closed = True
        self.e.save()
        self.assertRedirects(self.client.post(reverse("events:cancel", args=[self.e.pk])),
                             reverse("events:detail", args=[self.e.pk]))

    def test_deny(self):
        self.setup()

        # By default should not have permission to deny events
        self.assertOk(self.client.get(reverse("events:deny", args=[self.e.pk])), 403)

        permission = Permission.objects.get(codename="decline_event")
        self.user.user_permissions.add(permission)

        # Will need view_event for redirects
        permission = Permission.objects.get(codename="view_events")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("events:deny", args=[self.e.pk])))

        # If event has been closed or cancelled, redirect to detail page
        self.e.closed = True
        self.e.save()
        self.assertRedirects(self.client.get(reverse("events:deny", args=[self.e.pk])),
                             reverse("events:detail", args=[self.e.pk]))

        self.e.closed = False
        self.e.cancelled = True
        self.e.save()
        self.assertRedirects(self.client.get(reverse("events:deny", args=[self.e.pk])),
                             reverse("events:detail", args=[self.e.pk]))

        self.e.cancelled = False
        self.e.save()

        # Test POST
        self.assertRedirects(self.client.post(reverse("events:deny", args=[self.e.pk])),
                             reverse("events:detail", args=[self.e.pk]))

        self.e.refresh_from_db()
        self.assertTrue(self.e.closed)
        self.assertTrue(self.e.cancelled)

        # Check with email
        self.e.cancelled = False
        self.e.closed = False
        self.e.contact = self.user
        self.e.save()
        self.assertRedirects(self.client.post(reverse("events:deny", args=[self.e.pk])),
                             reverse("events:detail", args=[self.e.pk]))

    def test_close(self):
        self.setup()

        # Only POST should be permitted
        self.assertOk(self.client.get(reverse("events:close", args=[self.e.pk])), 405)

        # User should not have permission to close an event by default
        self.assertOk(self.client.post(reverse("events:close", args=[self.e.pk])), 403)

        permission = Permission.objects.get(codename="close_event")
        self.user.user_permissions.add(permission)

        # Will also need view_event permissions for redirect
        permission = Permission.objects.get(codename="view_events")
        self.user.user_permissions.add(permission)

        self.assertRedirects(self.client.post(reverse("events:close", args=[self.e.pk])),
                             reverse("events:detail", args=[self.e.pk]))

        self.e.refresh_from_db()
        self.assertTrue(self.e.closed)

    def test_reopen(self):
        self.setup()

        self.e.closed = True

        # Only POST should be permitted
        self.assertOk(self.client.get(reverse("events:reopen", args=[self.e.pk])), 405)

        # By default, user should not have permission to reopen events
        self.assertOk(self.client.post(reverse("events:reopen", args=[self.e.pk])), 403)

        permission = Permission.objects.get(codename="reopen_event")
        self.user.user_permissions.add(permission)

        # Will also need view_event permission for redirect
        permission = Permission.objects.get(codename="view_events")
        self.user.user_permissions.add(permission)

        self.assertRedirects(self.client.post(reverse("events:reopen", args=[self.e.pk])),
                             reverse("events:detail", args=[self.e.pk]))

        self.e.refresh_from_db()
        self.assertFalse(self.e.closed)

    def test_approve(self):
        self.setup()
        # By default, should not have permission to approve events
        self.assertOk(self.client.get(reverse("events:approve", args=[self.e3.pk])), 403)

        permission = Permission.objects.get(codename="approve_event")
        self.user.user_permissions.add(permission)

        # You'll also need view_event for redirects
        permission = Permission.objects.get(codename="view_events")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("events:approve", args=[self.e3.pk])))

        # If event is closed or has already been approved, redirect to event detail page
        self.e3.closed = True
        self.e3.save()
        self.assertRedirects(self.client.get(reverse("events:approve", args=[self.e3.pk])),
                             reverse("events:detail", args=[self.e3.pk]))

        self.e3.closed = False
        self.e3.approved = True
        self.e3.save()
        self.assertRedirects(self.client.get(reverse("events:approve", args=[self.e3.pk])),
                             reverse("events:detail", args=[self.e3.pk]))

        self.e3.approved = False
        self.e3.save()

        # Bad input
        invalid_data = {
            "serviceinstance_set-TOTAL_FORMS": 1,
            "serviceinstance_set-INITIAL_FORMS": 0,
            "serviceinstance_set-MIN_NUM_FORMS": 0,
            "serviceinstance_set-MAX_NUM_FORMS": 1000,
            "serviceinstance_set-0-service": 1,
            "serviceinstance_set-0-detail": 1,
        }
        self.assertOk(self.client.post(reverse("events:approve", args=[self.e3.pk]), invalid_data))

        # Valid data
        category = models.Category.objects.create(name="Lighting")
        models.Service.objects.create(shortname="L1", longname="Lighting", base_cost=10.00, addtl_cost=5.00,
                                      category=category)

        valid_data = {
            "description": "An event for testing stuff",
            "internal_notes": "",
            "datetime_start_0": timezone.now().date(),
            "datetime_start_1": timezone.now().time(),
            "datetime_end_0": timezone.now().date(),
            "datetime_end_1": timezone.now().time(),
            "org": "",
            "billing_org": "",
            "billed_in_bulk": False,
            "datetime_setup_complete_0": timezone.now().date(),
            "datetime_setup_complete_1": timezone.now().time(),
            "serviceinstance_set-TOTAL_FORMS": 1,
            "serviceinstance_set-INITIAL_FORMS": 0,
            "serviceinstance_set-MIN_NUM_FORMS": 0,
            "serviceinstance_set-MAX_NUM_FORMS": 1000,
            "serviceinstance_set-0-service": 1,
            "serviceinstance_set-0-detail": "I need some speakers",
            "save": "Approve Event"
        }
        self.assertRedirects(self.client.post(reverse("events:approve", args=[self.e3.pk]), valid_data),
                             reverse("events:detail", args=[self.e3.pk]))

        self.e3.refresh_from_db()
        self.assertTrue(self.e3.approved)

        self.e3.approved = False
        self.e3.contact = self.user
        org = OrgFactory.create(name="LNL")
        org.delinquent = True
        valid_data['org'] = str(org.pk)
        self.e3.save()

        models.Billing(date_billed=timezone.now().date(), event=self.e2, amount=100000.00)
        self.e2.org.add(org)

        # Check for unbilled events or delinquency
        self.assertOk(self.client.get(reverse("events:approve", args=[self.e2.pk])))

        # If applicable, add the event contact to the org
        self.assertRedirects(self.client.post(reverse("events:approve", args=[self.e3.pk]), valid_data),
                             reverse("events:detail", args=[self.e3.pk]))

        self.e3.refresh_from_db()
        self.assertIn(self.user, self.e3.org.get().associated_users.all())

    def test_review(self):
        self.setup()

        # By default, user should not have permission to review events
        self.assertOk(self.client.get(reverse("events:review", args=[self.e.pk])), 403)

        permission = Permission.objects.get(codename="review_event")
        self.user.user_permissions.add(permission)

        # Will need view_event for redirects
        permission = Permission.objects.get(codename="view_events")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("events:review", args=[self.e.pk])))

        # If event has already been closed or reviewed, redirect to detail page
        self.e.closed = True
        self.e.save()
        self.assertRedirects(self.client.get(reverse("events:review", args=[self.e.pk])),
                             reverse("events:detail", args=[self.e.pk]))

        self.e.closed = False
        self.e.reviewed = True
        self.e.save()
        self.assertRedirects(self.client.get(reverse("events:review", args=[self.e.pk])),
                             reverse("events:detail", args=[self.e.pk]))

        self.e.reviewed = False
        self.e.save()

        # Check that we get form back on invalid data
        self.assertOk(self.client.post(reverse("events:review", args=[self.e.pk])))

        # Check with valid data
        valid_data = {
            "internal_notes": "",
            "org": str(OrgFactory.create(name="LNL").pk),
            "billing_org": "",
            "save": "Yes!"
        }
        self.assertRedirects(self.client.post(reverse("events:review", args=[self.e.pk]), valid_data),
                             reverse("events:detail", args=[self.e.pk]) + "#billing")

        self.e.refresh_from_db()
        self.assertTrue(self.e.reviewed)

        # Check with 2019 Event
        self.assertRedirects(self.client.post(reverse("events:review", args=[self.e3.pk]), valid_data),
                             reverse("events:detail", args=[self.e3.pk]) + "#billing")

    def test_reviewremind(self):
        self.setup()

        # By default, user should not have this power
        self.assertOk(self.client.get(reverse("events:remind", args=[self.e.pk, self.user.pk])), 403)

        permission = Permission.objects.get(codename="review_event")
        self.user.user_permissions.add(permission)

        # This user will also need view_event permissions for redirects
        permission = Permission.objects.get(codename="view_events")
        self.user.user_permissions.add(permission)

        # Should now redirect as event has not yet been approved
        self.assertRedirects(self.client.get(reverse("events:remind", args=[self.e.pk, self.user.pk])),
                             reverse("events:detail", args=[self.e.pk]))

        # If event has been closed or reviewed already, redirect to detail page
        self.e.closed = True
        self.e.save()
        self.assertRedirects(self.client.get(reverse("events:remind", args=[self.e.pk, self.user.pk])),
                             reverse("events:detail", args=[self.e.pk]))

        self.e.reviewed = True
        self.e.closed = False
        self.e.save()
        self.assertRedirects(self.client.get(reverse("events:remind", args=[self.e.pk, self.user.pk])),
                             reverse("events:detail", args=[self.e.pk]))

        self.e.approved = True
        self.e.reviewed = False
        self.e.save()

        # If for some reason no CC instance is found, result should have a status of 200, but display "Bad Call" message
        self.assertOk(self.client.get(reverse("events:remind", args=[self.e.pk, self.user.pk])))

        # Add CC
        CCInstanceFactory.create(crew_chief=self.user, event=self.e)

        self.assertRedirects(self.client.get(reverse("events:remind", args=[self.e.pk, self.user.pk])),
                             reverse("events:review", args=[self.e.pk]))

    def test_remindall(self):
        self.setup()

        # By default, user should not have this power
        self.assertOk(self.client.get(reverse("events:remindall", args=[self.e.pk])), 403)

        permission = Permission.objects.get(codename="review_event")
        self.user.user_permissions.add(permission)

        # This user will also need view_event permissions for redirects
        permission = Permission.objects.get(codename="view_events")
        self.user.user_permissions.add(permission)

        # Should now redirect as event has not yet been approved
        self.assertRedirects(self.client.get(reverse("events:remindall", args=[self.e.pk])),
                             reverse("events:detail", args=[self.e.pk]))

        # If event has been closed or reviewed already, redirect to detail page
        self.e.closed = True
        self.e.save()
        self.assertRedirects(self.client.get(reverse("events:remindall", args=[self.e.pk])),
                             reverse("events:detail", args=[self.e.pk]))

        self.e.closed = False
        self.e.reviewed = True
        self.e.save()
        self.assertRedirects(self.client.get(reverse("events:remindall", args=[self.e.pk])),
                             reverse("events:detail", args=[self.e.pk]))

        self.e.reviewed = False
        self.e.approved = True
        self.e.save()

        # All crew chiefs have already submitted reports
        self.assertRedirects(self.client.get(reverse("events:remindall", args=[self.e.pk])),
                             reverse("events:review", args=[self.e.pk]))

        # Add CC
        building = models.Building.objects.create(name="New Academic Building Next to the Library", shortname="NABNTTL")
        location = models.Location.objects.create(name="NABNTTL", building=building)

        CCInstanceFactory.create(crew_chief=self.user, event=self.e, setup_location=location)

        self.assertRedirects(self.client.get(reverse("events:remindall", args=[self.e.pk])),
                             reverse("events:detail", args=[self.e.pk]))

        # Supply next URL
        self.assertRedirects(self.client.get(reverse("events:remindall", args=[self.e.pk]), {'next': reverse("home")}),
                             reverse("home"))

    def test_rmcrew(self):
        self.setup()

        self.e.crew.add(self.user)

        # By default user should not have permission to do this
        self.assertOk(self.client.get(reverse("events:remove-crew", args=[self.e.pk, self.user.pk])), 403)

        permission = Permission.objects.get(codename="edit_event_hours")
        self.user.user_permissions.add(permission)

        self.assertRedirects(self.client.get(reverse("events:remove-crew", args=[self.e.pk, self.user.pk])),
                             reverse("events:add-crew", args=[self.e.pk]))

        # Check that crew member has been removed
        self.assertNotIn(self.user, self.e.crew.all())

        # If event is closed, redirect to detail page (will need view_event permission)
        permission = Permission.objects.get(codename="view_events")
        self.user.user_permissions.add(permission)

        self.e.closed = True
        self.e.save()
        self.assertRedirects(self.client.get(reverse("events:remove-crew", args=[self.e.pk, self.user.pk])),
                             reverse("events:detail", args=[self.e.pk]))

    def test_assigncrew(self):
        self.setup()

        # By default user should not have permission to do this
        self.assertOk(self.client.get(reverse("events:add-crew", args=[self.e.pk])), 403)

        permission = Permission.objects.get(codename="edit_event_hours")
        self.user.user_permissions.add(permission)

        # Will also need view_event permission for redirect
        permission = Permission.objects.get(codename="view_events")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("events:add-crew", args=[self.e.pk])))

        # Check that page redirects if event is already closed
        self.e.closed = True
        self.e.save()
        self.assertRedirects(self.client.get(reverse("events:add-crew", args=[self.e.pk])),
                             reverse("events:detail", args=[self.e.pk]))

        self.e.closed = False
        self.e.save()

        # Check that new (2019) events display the crew detail page instead
        self.assertRedirects(self.client.get(reverse("events:add-crew", args=[self.e3.pk])),
                             reverse("events:detail", args=[self.e3.pk]) + "#crew")

        # Check valid data
        valid_data = {
            "crew": [str(self.user.pk)],
            "save": "Save Changes"
        }

        self.assertRedirects(self.client.post(reverse("events:add-crew", args=[self.e.pk]), valid_data),
                             reverse("events:detail", args=[self.e.pk]))

        self.assertIn(self.user, self.e.crew.all())

    def test_hours_bulk(self):
        self.setup()

        # By default, user should not have permission to access this page
        self.assertOk(self.client.get(reverse("events:add-bulk-crew", args=[self.e.pk])), 403)

        self.e.datetime_end = timezone.now() + timezone.timedelta(days=-15)
        self.e.save()
        building = models.Building.objects.create(name="Waste of Space", shortname="Foisie")
        location = models.Location.objects.create(name="Propaganda Wall", building=building)
        # Adding a user as a crew chief should give them the permissions they need
        CCInstanceFactory.create(crew_chief=self.user, event=self.e, setup_location=location)

        # Should display the Too Late error
        self.assertOk(self.client.get(reverse("events:add-bulk-crew", args=[self.e.pk])))

        # Should redirect to detail page if event is closed
        self.e.datetime_end = timezone.now()
        self.e.closed = True
        self.e.save()

        # Would be best to have view_event permissions for redirect
        permission = Permission.objects.get(codename="view_events")
        self.user.user_permissions.add(permission)

        self.assertRedirects(self.client.get(reverse("events:add-bulk-crew", args=[self.e.pk])),
                             reverse("events:detail", args=[self.e.pk]))

        self.e.closed = False
        self.e.save()

        # Otherwise check that everything loads ok
        self.assertOk(self.client.get(reverse("events:add-bulk-crew", args=[self.e.pk])))

        # Check that we can submit valid data
        valid_data = {
            "hours-TOTAL_FORMS": 1,
            "hours-INITIAL_FORMS": 0,
            "hours-MIN_NUM_FORMS": 0,
            "hours-MAX_NUM_FORMS": 1000,
            "hours-0-user": str(self.user.pk),
            "hours-0-hours": 5.00,
            "hours-0-category": "",
            "hours-0-service": "",
            "save": "Save Changes"
        }

        self.assertRedirects(self.client.post(reverse("events:add-bulk-crew", args=[self.e.pk]), valid_data),
                             reverse("events:detail", args=[self.e.pk]))

    def test_hours_prefill(self):
        self.setup()

        # Should not be allowed to POST data
        self.assertOk(self.client.post(reverse("events:selfcrew", args=[self.e.pk])), 405)

        # No ccs means not allowed
        self.assertOk(self.client.get(reverse("events:selfcrew", args=[self.e.pk])), 403)

        building = models.Building.objects.create(name="Morgan Hall", shortname="Morgan")
        location = models.Location.objects.create(name="Best Dorm", building=building)
        cc = CCInstanceFactory.create(crew_chief=self.user, setup_location=location, event=self.e,
                                      setup_start=timezone.now() + timezone.timedelta(hours=1))

        # Will need view_event permissions to redirect
        permission = Permission.objects.get(codename="view_events")
        self.user.user_permissions.add(permission)

        # Should redirect with message indicating that event has not started yet
        self.assertRedirects(self.client.get(reverse("events:selfcrew", args=[self.e.pk])),
                             reverse("events:detail", args=[self.e.pk]))

        cc.setup_start = timezone.now()
        cc.save()
        self.e.datetime_end = timezone.now() + timezone.timedelta(days=-1)
        self.e.save()

        # Should redirect with message indicating that event has ended
        self.assertRedirects(self.client.get(reverse("events:selfcrew", args=[self.e.pk])),
                             reverse("events:detail", args=[self.e.pk]))

        self.e.datetime_end = timezone.now()
        self.e.save()

        # Check that hour object created successfully
        self.assertFalse(self.e.hours.filter(user=self.user).exists())

        self.assertRedirects(self.client.get(reverse("events:selfcrew", args=[self.e.pk])),
                             reverse("events:detail", args=[self.e.pk]))

        self.assertTrue(self.e.hours.filter(user=self.user).exists())

        # Should redirect right away as hours have already been recorded for this user
        self.assertRedirects(self.client.get(reverse("events:selfcrew", args=[self.e.pk])),
                             reverse("events:detail", args=[self.e.pk]))

        self.assertEqual(self.e.hours.filter(user=self.user).count(), 1)

    def test_crew_tracker(self):
        self.assertOk(self.client.get(reverse("events:crew-tracker")))

        # Ensure POST is not permitted
        self.assertOk(self.client.post(reverse("events:crew-tracker")), 405)

    def test_checkin(self):
        self.setup()

        # Only LNL members should be permitted to check-in
        self.assertOk(self.client.get(reverse("events:crew-checkin")), 403)

        Group.objects.create(name="Active").user_set.add(self.user)

        self.assertContains(self.client.get(reverse("events:crew-checkin")), "There are currently no events available "
                                                                             "for checkin")

        # Only Event 2019 events support checkin
        CCInstanceFactory.create(crew_chief=self.user, event=self.e3, setup_start=timezone.now())
        self.e3.datetime_end = timezone.now() + timezone.timedelta(hours=2)
        self.e3.approved = True
        self.e3.max_crew = 2
        self.e3.save()

        self.assertOk(self.client.get(reverse("events:crew-checkin")))

        invalid_data = {
            "event": "",
            "save": "Submit"
        }

        self.assertOk(self.client.post(reverse("events:crew-checkin"), invalid_data))

        # Check with valid data
        valid_data = {
            "event": self.e3.pk,
            "save": "Submit"
        }

        # Will need view_events permission on redirect
        permission = Permission.objects.get(codename="view_events")
        self.user.user_permissions.add(permission)

        self.assertRedirects(self.client.post(reverse("events:crew-checkin"), valid_data),
                             reverse("events:detail", args=[self.e3.pk]))
        self.assertTrue(self.e3.hours.filter(user=self.user).exists())
        self.assertEqual(models.CrewAttendanceRecord.objects.filter(active=True, user=self.user).count(), 1)

        # Check that we cannot checkin again until we have checked out
        self.assertContains(self.client.post(reverse("events:crew-checkin"), valid_data), "You are already checked "
                                                                                          "into an event")

        record = models.CrewAttendanceRecord.objects.get(active=True, user=self.user)
        record.active = False
        record.save()

        user2 = UserFactory.create(password="123")
        models.CrewAttendanceRecord.objects.create(event=self.e3, user=user2, active=True)

        self.e3.max_crew = 1
        self.e3.save()

        # Check that once max_crew limit has been reached, user can no longer check in (if all events full, show this)
        self.assertContains(self.client.get(reverse("events:crew-checkin")), "There are currently no events available "
                                                                             "for checkin")

    def test_checkout(self):
        self.setup()

        # Only LNL members should be permitted to check-out
        self.assertOk(self.client.get(reverse("events:crew-checkout")), 403)

        Group.objects.create(name="Active").user_set.add(self.user)

        # Return error if there is no checkin record
        self.assertContains(self.client.get(reverse("events:crew-checkout")), "Whoops!")

        # Check with EST because datepicker will localize
        tz = zoneinfo.ZoneInfo('US/Eastern')
        past_time = timezone.datetime.strptime('2020-01-01T00:00:00', '%Y-%m-%dT%H:%M:%S').replace(tzinfo=tz)
        setup_start = timezone.datetime.strptime('2020-01-01T01:00:00', '%Y-%m-%dT%H:%M:%S').replace(tzinfo=tz)
        checkin_time = timezone.datetime.strptime('2020-01-01T02:00:00', '%Y-%m-%dT%H:%M:%S').replace(tzinfo=tz)

        CCInstanceFactory.create(crew_chief=self.user, event=self.e3, setup_start=setup_start)
        category = models.Category.objects.create(name="Lighting")
        service = ServiceFactory.create(category=category)
        models.ServiceInstance.objects.create(service=service, event=self.e3)
        record = models.CrewAttendanceRecord.objects.create(user=self.user, event=self.e3, checkin=checkin_time,
                                                            active=True)
        self.e3.hours.create(user=self.user)
        self.e3.save()

        # Display checkin / checkout review summary
        self.assertOk(self.client.get(reverse("events:crew-checkout")))

        # Check for basic funny business when checking out (i.e. checkout time should never be in the future)
        future_date = timezone.now() + timezone.timedelta(minutes=1)
        invalid_data = {
            "checkin_0": checkin_time.strftime('%Y-%m-%d'),
            "checkin_1": checkin_time.strftime('%I:%M %p'),
            "checkout_0": future_date.strftime('%Y-%m-%d'),
            "checkout_1": future_date.strftime('%I:%M %p'),
            "save": "Confirm"
        }
        self.assertContains(self.client.post(reverse("events:crew-checkout"), invalid_data), "Does this look correct?")

        checkout_time = timezone.datetime.strptime('2020-01-01T12:00:00', '%Y-%m-%dT%H:%M:%S').replace(tzinfo=tz)
        valid_data = {
            "checkin_0": past_time.strftime('%Y-%m-%d'),
            "checkin_1": past_time.strftime('%I:%M %p'),
            "checkout_0": checkout_time.strftime('%Y-%m-%d'),
            "checkout_1": checkout_time.strftime('%I:%M %p'),
            "save": "Confirm"
        }
        self.assertContains(self.client.post(reverse("events:crew-checkout"), valid_data), "Hours")
        record.refresh_from_db()
        self.assertIsNotNone(record.checkout)

        # The hour summary should be the new state of the page
        self.assertContains(self.client.get(reverse("events:crew-checkout")), "Hours")

        # Submitting hours should be optional, but check that when included, information is accurate
        # When someone tries to change the checkin time to before the setup start, the date is set to the setup start
        invalid_hours = {
            "hours_Lighting": 2,
            "total": 11,
            "save": "Submit"
        }
        self.assertOk(self.client.post(reverse("events:crew-checkout"), invalid_hours))

        # If hours are all set to 0 or missing, do not update hours
        no_hours = {
            "hours_Lighting": 0,
            "total": 11,
            "save": "Submit"
        }

        # Will need view_events permission for redirects
        permission = Permission.objects.get(codename="view_events")
        self.user.user_permissions.add(permission)

        self.assertRedirects(self.client.post(reverse("events:crew-checkout"), no_hours),
                             reverse("events:detail", args=[self.e3.pk]))
        self.assertFalse(self.e3.hours.filter(user=self.user, hours=11).exists())

        record.active = True
        record.save()

        valid_hours = {
            "hours_Lighting": 11,
            "total": 11,
            "save": "Submit"
        }
        self.assertRedirects(self.client.post(reverse("events:crew-checkout"), valid_hours),
                             reverse("events:detail", args=[self.e3.pk]))
        self.assertTrue(self.e3.hours.filter(user=self.user, hours=11).exists())

        # Check that we cannot checkout again without checking in first
        self.assertContains(self.client.get(reverse("events:crew-checkout")), "Whoops!")

        record.active = True
        record.save()

        # Check that we add to the hours instead of creating a new record the next time
        self.assertRedirects(self.client.post(reverse("events:crew-checkout"), valid_hours),
                             reverse("events:detail", args=[self.e3.pk]))
        self.assertTrue(self.e3.hours.filter(user=self.user, hours=22).exists())

    def test_bulk_checkin(self):
        self.setup()

        # Only LNL members should be permitted to use this tool
        self.assertOk(self.client.get(reverse("events:crew-bulk")), 403)

        Group.objects.create(name="Active").user_set.add(self.user)

        # Display message when there are no events the user is a CC for (and is not an officer)
        self.assertContains(self.client.get(reverse("events:crew-bulk")), "Hmm")

        # Only 2019 Events support this feature
        CCInstanceFactory.create(crew_chief=self.user, event=self.e3, setup_start=timezone.now())
        self.e3.datetime_end = timezone.now() + timezone.timedelta(hours=2)
        self.e3.max_crew = 1
        self.e3.approved = True
        self.e3.save()

        self.assertContains(self.client.get(reverse("events:crew-bulk")), "Select Event")

        # Select an event and reload the page with its id
        data = {
            "event": self.e3.pk,
            "save": "Submit"
        }

        self.assertRedirects(self.client.post(reverse("events:crew-bulk"), data),
                             reverse("events:crew-bulk") + "?id=" + str(self.e3.pk))

        self.user.student_id = 123456789
        self.user.save()

        url = reverse("events:crew-bulk") + "?id=" + str(self.e3.pk)

        # Check that when Student ID does not match a user we get an "invalid" message
        invalid_scan = {
            "id": 987654321,
            "save": "Enter"
        }
        self.assertContains(self.client.post(url, invalid_scan), "Invalid")

        valid_scan = {
            "id": 123456789,
            "save": "Enter"
        }
        # Check that we are checked in ok
        self.assertIn(b"Welcome", self.client.post(url, valid_scan).content)
        self.assertTrue(self.e3.crew_attendance.filter(active=True, user=self.user).exists())

        # Check that checkout works ok next
        self.assertIn(b"Bye", self.client.post(url, valid_scan).content)
        self.assertFalse(self.e3.crew_attendance.filter(active=True, user=self.user).exists())

        second_event = Event2019Factory.create(event_name="Some other test event")
        second_record = models.CrewAttendanceRecord.objects.create(event=second_event, user=self.user, active=True)

        # Check that if user is checked in elsewhere that they cannot check in here
        self.assertIn(b"Checkin Failed", self.client.post(url, valid_scan).content)

        second_record.event = self.e3
        second_record.user = UserFactory.create(password="456")
        second_record.save()

        # Check that if crew limit is reached we cannot checkin
        self.assertIn(b"limit", self.client.post(url, valid_scan).content)

        # TODO: Valid swipe
        # TODO: Invalid swipe

    def test_rmcc(self):
        self.setup()

        # By default, user should not have permission to remove CC
        self.assertOk(self.client.get(reverse("events:remove-chief", args=[self.e.pk, self.user.pk])), 403)

        permission = Permission.objects.get(codename="edit_event_hours")
        self.user.user_permissions.add(permission)

        # Will need view_events permission on redirects
        permission = Permission.objects.get(codename="view_events")
        self.user.user_permissions.add(permission)

        CCInstanceFactory(event=self.e, crew_chief=self.user)
        self.e.closed = True
        self.e.save()

        # If event is closed, return to detail page
        self.assertRedirects(self.client.get(reverse("events:remove-chief", args=[self.e.pk, self.user.pk])),
                             reverse("events:detail", args=[self.e.pk]))

        self.e.closed = False
        self.e.save()

        self.assertRedirects(self.client.get(reverse("events:remove-chief", args=[self.e.pk, self.user.pk])),
                             reverse("events:chiefs", args=[self.e.pk]))
        self.assertNotIn(self.user, self.e.crew_chief.all())

    def test_assigncc(self):
        self.setup()

        category = models.Category.objects.create(name="Lighting")
        l1 = models.Lighting.objects.create(shortname="L1", longname="Lighting", base_cost=1000.00, addtl_cost=1.00,
                                            category=category)
        l2 = ServiceFactory(shortname="L2", longname="More Lighting", category=category)
        models.ServiceInstance.objects.create(event=self.e3, service=l2)
        self.e.lighting = l1
        self.e.save()
        location = LocationFactory(name="Office", setup_only=True)

        # By default, user should not have permission to assign a CC
        self.assertOk(self.client.get(reverse("events:chiefs", args=[self.e.pk])), 403)

        permission = Permission.objects.get(codename="edit_event_hours")
        self.user.user_permissions.add(permission)

        # Will need view event permissions for redirect
        permission = Permission.objects.get(codename="view_events")
        self.user.user_permissions.add(permission)

        self.e.closed = True
        self.e.save()

        # If event is closed return to detail page
        self.assertRedirects(self.client.get(reverse("events:chiefs", args=[self.e.pk])),
                             reverse("events:detail", args=[self.e.pk]))

        self.e.closed = False
        self.e.save()

        # Check that page loads ok
        self.assertOk(self.client.get(reverse("events:chiefs", args=[self.e.pk])))

        # Check that we can add new crew chief
        event_data = {
            "ccinstances-TOTAL_FORMS": 1,
            "ccinstances-INITIAL_FORMS": 0,
            "ccinstances-MIN_NUM_FORMS": 0,
            "ccinstances-MAX_NUM_FORMS": 1000,
            "ccinstances-0-crew_chief": str(self.user.pk),
            "ccinstances-0-service": str(l1.pk),
            "ccinstances-0-setup_location": str(location.pk),
            "ccinstances-0-setup_start_0": timezone.now().date(),
            "ccinstances-0-setup_start_1": timezone.now().time()
        }
        self.assertRedirects(self.client.post(reverse("events:chiefs", args=[self.e.pk]), event_data),
                             reverse("events:detail", args=[self.e.pk]))
        self.assertTrue(models.EventCCInstance.objects.filter(crew_chief=self.user, event=self.e).exists())

        event2019_data = {
            "ccinstances-TOTAL_FORMS": 1,
            "ccinstances-INITIAL_FORMS": 0,
            "ccinstances-MIN_NUM_FORMS": 0,
            "ccinstances-MAX_NUM_FORMS": 1000,
            "ccinstances-0-crew_chief": str(self.user.pk),
            "ccinstances-0-category": str(category.pk),
            "ccinstances-0-setup_location": str(location.pk),
            "ccinstances-0-setup_start_0": timezone.now().date(),
            "ccinstances-0-setup_start_1": timezone.now().time()
        }
        self.assertRedirects(self.client.post(reverse("events:chiefs", args=[self.e3.pk]), event2019_data),
                             reverse("events:detail", args=[self.e3.pk]))
        self.assertTrue(models.EventCCInstance.objects.filter(crew_chief=self.user, event=self.e3).exists())

    def test_assignattach(self):
        self.setup()

        # By default, should not have permission to modify attachments
        self.assertOk(self.client.get(reverse("events:files", args=[self.e.pk])), 403)

        permission = Permission.objects.get(codename="event_attachments")
        self.user.user_permissions.add(permission)

        # Will need view_event permission for redirect
        permission = Permission.objects.get(codename="view_events")
        self.user.user_permissions.add(permission)

        # Check that we redirect to detail page if event is closed
        self.e.closed = True
        self.e.save()

        self.assertRedirects(self.client.get(reverse("events:files", args=[self.e.pk])),
                             reverse("events:detail", args=[self.e.pk]))

        self.e.closed = False
        self.e.save()

        # Everything should load ok
        self.assertOk(self.client.get(reverse("events:files", args=[self.e.pk])))

        proj = models.Category.objects.create(name="Projection")
        dp = models.Projection.objects.create(category=proj, shortname="DP", longname="Digital Projection",
                                              base_cost=1.00, addtl_cost=1.00)
        self.e.projection = dp
        self.e.save()
        CCInstanceFactory(crew_chief=self.user, event=self.e, service=dp)

        valid_data = {
            "attachments-TOTAL_FORMS": 1,
            "attachments-INITIAL_FORMS": 0,
            "attachments-MIN_NUM_FORMS": 0,
            "attachments-MAX_NUM_FORMS": 1000,
            "attachments-0-for_service": str(dp.pk),
            "attachments-0-attachment": SimpleUploadedFile('test.txt', b"some content"),
            "attachments-0-note": ""
        }

        # Check that we can add attachment ok
        self.assertRedirects(self.client.post(reverse("events:files", args=[self.e.pk]), valid_data),
                             reverse("events:detail", args=[self.e.pk]))

    def test_ics_download(self):
        self.setup()

        resp = self.client.get(reverse('events:ics', args=[self.e.pk]))
        self.assertEqual(resp.get('Content-Disposition'), "attachment; filename=event.ics")

    def test_extras(self):
        self.setup()

        category = models.Category.objects.create(name="Lighting")
        extra = models.Extra.objects.create(name="Mirror Ball", cost=4500.99, desc="A very nice mirror ball.",
                                            category=category)

        # By default, should not have permission to modify extras
        self.assertOk(self.client.get(reverse("events:extras", args=[self.e.pk])), 403)

        permission = Permission.objects.get(codename="adjust_event_charges")
        self.user.user_permissions.add(permission)

        # Will need view_event permissions for redirect
        permission = Permission.objects.get(codename="view_events")
        self.user.user_permissions.add(permission)

        self.e.closed = True
        self.e.save()

        # Check that we redirect to event detail if event is already closed
        self.assertRedirects(self.client.get(reverse("events:extras", args=[self.e.pk])),
                             reverse("events:detail", args=[self.e.pk]))

        self.e.closed = False
        self.e.save()

        # Check that page loads ok
        self.assertOk(self.client.get(reverse("events:extras", args=[self.e.pk])))

        # Check that we can submit form ok
        valid_data = {
            "extrainstance_set-TOTAL_FORMS": 1,
            "extrainstance_set-INITIAL_FORMS": 0,
            "extrainstance_set-MIN_NUM_FORMS": 0,
            "extrainstance_set-MAX_NUM_FORMS": 1000,
            "extrainstance_set-0-extra": str(extra.pk),
            "extrainstance_set-0-quant": 1
        }
        self.assertRedirects(self.client.post(reverse("events:extras", args=[self.e.pk]), valid_data),
                             reverse("events:detail", args=[self.e.pk]) + "#billing")
        self.assertTrue(models.ExtraInstance.objects.filter(event=self.e, extra=extra).exists())

        # Check disappear warning
        extra.disappear = True
        extra.save()

        self.assertOk(self.client.get(reverse("events:extras", args=[self.e.pk])))

    def test_oneoff(self):
        self.setup()

        # By default, user should not have permission to adjust one-offs
        self.assertOk(self.client.get(reverse("events:oneoffs", args=[self.e.pk])), 403)

        # Will need view_event permission for redirects
        permission = Permission.objects.get(codename="view_events")
        self.user.user_permissions.add(permission)

        permission = Permission.objects.get(codename="adjust_event_charges")
        self.user.user_permissions.add(permission)

        # Check that we redirect to detail page when event is closed
        self.e.closed = True
        self.e.save()

        self.assertRedirects(self.client.get(reverse("events:oneoffs", args=[self.e.pk])),
                             reverse("events:detail", args=[self.e.pk]))

        self.e.closed = False
        self.e.save()

        # Check that page loads ok
        self.assertOk(self.client.get(reverse("events:oneoffs", args=[self.e.pk])))

        # Check that form can be submitted ok
        valid_data = {
            "arbitraryfees-TOTAL_FORMS": 1,
            "arbitraryfees-INITIAL_FORMS": 0,
            "arbitraryfees-MIN_NUM_FORMS": 0,
            "arbitraryfees-MAX_NUM_FORMS": 1000,
            "arbitraryfees-0-key_name": "Labor",
            "arbitraryfees-0-key_value": 50.00,
            "arbitraryfees-0-key_quantity": 100
        }

        self.assertRedirects(self.client.post(reverse("events:oneoffs", args=[self.e.pk]), valid_data),
                             reverse("events:detail", args=[self.e.pk]) + "#billing")

    def test_ccr_add(self):
        self.setup()

        # By default user should not have permission to create a CC report
        self.assertOk(self.client.get(reverse("events:reports:new", args=[self.e.pk])), 403)

        permission = Permission.objects.get(codename="add_event_report")
        self.user.user_permissions.add(permission)

        # Will need view_event permission for redirect
        permission = Permission.objects.get(codename="view_events")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("events:reports:new", args=[self.e.pk])))

        # Test valid data
        valid_data = {
            "crew_chief": str(self.user.pk),
            "report": "There was food at this event!",
            "save": "Save Changes"
        }
        self.assertRedirects(self.client.post(reverse("events:reports:new", args=[self.e.pk]), valid_data),
                             reverse("events:detail", args=[self.e.pk]))

    def test_ccr_edit(self):
        self.setup()

        # By default user should not have permission to edit a cc report
        self.assertOk(self.client.get(reverse("events:reports:edit", args=[self.e.pk, self.report.pk])), 403)

        permission = Permission.objects.get(codename="change_ccreport")
        self.user.user_permissions.add(permission)

        # Will need permission for redirect
        permission = Permission.objects.get(codename="view_events")
        self.user.user_permissions.add(permission)

        self.report.crew_chief = self.user
        self.report.report = "There was no food"
        self.report.save()

        self.assertOk(self.client.get(reverse("events:reports:edit", args=[self.e.pk, self.report.pk])))

        # Test valid input
        valid_data = {
            "crew_chief": str(self.user.pk),
            "report": "Ok...there was some food. But it wasn't very good.",
            "save": "Save Changes"
        }
        self.assertRedirects(self.client.post(reverse("events:reports:edit", args=[self.e.pk, self.report.pk]),
                                              valid_data), reverse("events:detail", args=[self.e.pk]))

    def test_ccr_delete(self):
        self.setup()

        # By default, user should not have permission to delete a cc report
        self.assertOk(self.client.get(reverse("events:reports:remove", args=[self.e.pk, self.report.pk])), 403)

        permission = Permission.objects.get(codename="delete_ccreport")
        self.user.user_permissions.add(permission)

        # Will need the following permission for redirect
        permission = Permission.objects.get(codename="view_events")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("events:reports:remove", args=[self.e.pk, self.report.pk])))

        # Check that we get error if event is closed
        self.e.closed = True
        self.e.save()

        with self.assertRaises(ValidationError):
            logging.disable(logging.ERROR)
            self.client.get(reverse("events:reports:remove", args=[self.e.pk, self.report.pk]))

        self.e.closed = False
        self.e.save()

        # Check that report is deleted successfully
        self.assertRedirects(self.client.post(reverse("events:reports:remove", args=[self.e.pk, self.report.pk])),
                             reverse("events:detail", args=[self.e.pk]))
        self.assertFalse(models.CCReport.objects.filter(event=self.e.pk, crew_chief=self.user).exists())

    def test_bill_add(self):
        self.setup()

        # By default, user should not have permission to create bills
        self.assertOk(self.client.get(reverse("events:bills:new", args=[self.e.pk])), 403)

        permission = Permission.objects.get(codename="bill_event")
        self.user.user_permissions.add(permission)

        # Will need permission for redirect
        permission = Permission.objects.get(codename="view_events")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("events:bills:new", args=[self.e.pk])))

        # If event is closed redirect to detail page
        self.e.closed = True
        self.e.save()

        self.assertRedirects(self.client.get(reverse("events:bills:new", args=[self.e.pk])),
                             reverse("events:detail", args=[self.e.pk]))

        self.e.closed = False
        self.e.save()

        # Check with valid input
        data_email = {
            "date_billed": timezone.now().date(),
            "amount": 20.00,
            "save-and-make-email": "Save and Make Email"
        }

        data_no_email = {
            "date_billed": timezone.now().date(),
            "amount": 30.00,
            "save-and-return": "Save and Return"
        }

        self.assertRedirects(self.client.post(reverse("events:bills:new", args=[self.e.pk]), data_email),
                             reverse("events:bills:email", args=[self.e.pk, 1]))

        self.assertRedirects(self.client.post(reverse("events:bills:new", args=[self.e.pk]), data_no_email),
                             reverse("events:detail", args=[self.e.pk]) + "#billing")

        self.assertTrue(models.Billing.objects.filter(amount=20.00).exists())
        self.assertTrue(models.Billing.objects.filter(amount=30.00).exists())

    def test_bill_edit(self):
        self.setup()

        self.e2.closed = True
        self.e2.save()

        bill = models.Billing.objects.create(date_billed=timezone.now().date(), event=self.e, amount=200.00)
        another_bill = models.Billing.objects.create(date_billed=timezone.now().date(), event=self.e2, amount=50.00)

        # By default, user should not have permission to modify bills
        self.assertOk(self.client.get(reverse("events:bills:edit", args=[self.e.pk, bill.pk])), 403)

        permission = Permission.objects.get(codename="bill_event")
        self.user.user_permissions.add(permission)

        # Will need view_event permission for redirects
        permission = Permission.objects.get(codename="view_events")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("events:bills:edit", args=[self.e.pk, bill.pk])))

        # If event is closed, redirect to detail page
        self.assertRedirects(self.client.get(reverse("events:bills:edit", args=[self.e2.pk, another_bill.pk])),
                             reverse("events:detail", args=[self.e2.pk]))

        # Raise permission denied if for some reason event and bill pks do not match
        self.assertOk(self.client.get(reverse("events:bills:edit", args=[self.e.pk, another_bill.pk])), 403)

        # Test valid input
        valid_data = {
            "date_billed": timezone.now().date(),
            "amount": 500.00,
            "save": "Save Changes"
        }
        self.assertRedirects(self.client.post(reverse("events:bills:edit", args=[self.e.pk, bill.pk]), valid_data),
                             reverse("events:detail", args=[self.e.pk]) + "#billing")

        bill.refresh_from_db()
        self.assertEqual(bill.amount, 500.00)

    def test_bill_delete(self):
        self.setup()

        self.e2.closed = True
        self.e2.save()

        bill = models.Billing.objects.create(date_billed=timezone.now().date(), event=self.e, amount=200.00)
        another_bill = models.Billing.objects.create(date_billed=timezone.now().date(), event=self.e2, amount=400.00)

        # By default, user should not have permission to delete bills
        self.assertOk(self.client.get(reverse("events:bills:remove", args=[self.e.pk, bill.pk])), 403)

        permission = Permission.objects.get(codename="bill_event")
        self.user.user_permissions.add(permission)

        # Will need view_event permission for redirects
        permission = Permission.objects.get(codename="view_events")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("events:bills:remove", args=[self.e.pk, bill.pk])))

        # If event is closed, redirect to the detail page
        self.assertRedirects(self.client.get(reverse("events:bills:remove", args=[self.e2.pk, another_bill.pk])),
                             reverse("events:detail", args=[self.e2.pk]))

        # Raise permission denied if event and bill pks do not match and event is either closed or has been paid
        self.assertOk(self.client.get(reverse("events:bills:remove", args=[self.e.pk, another_bill.pk])), 403)

        bill.date_paid = timezone.now().date()
        bill.save()

        self.assertOk(self.client.get(reverse("events:bills:remove", args=[self.e.pk, bill.pk])), 403)

        bill.date_paid = None
        bill.save()

        # Test POST
        self.assertRedirects(self.client.post(reverse("events:bills:remove", args=[self.e.pk, bill.pk])),
                             reverse("events:detail", args=[self.e.pk]) + "#billing")

        self.assertFalse(models.Billing.objects.filter(pk=bill.pk).exists())

    def test_multibill_add(self):
        self.setup()

        self.e.reviewed = True
        self.e.billed_in_bulk = True
        self.e.billing_org = self.org
        self.e.save()

        self.e2.reviewed = True
        self.e2.billed_in_bulk = True
        self.e2.save()

        # By default, user should not have permission to create multibills
        self.assertOk(self.client.get(reverse("events:multibillings:new")), 403)

        permission = Permission.objects.get(codename="bill_event")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("events:multibillings:new")))

        # Test POST
        data_email = {
            "events": [str(self.e.pk), str(self.e2.pk)],
            "date_billed": timezone.now().date(),
            "amount": 500.00,
            "save-and-make-email": "Save and Make Email"
        }

        data_no_email = {
            "events": [str(self.e.pk), str(self.e2.pk)],
            "date_billed": timezone.now().date(),
            "amount": 400.00,
            "save-and-return": "Save and Return"
        }

        # Throw error if events do not have same billing organization
        self.assertOk(self.client.post(reverse("events:multibillings:new"), data_email))

        self.e2.org.add(self.org)
        self.e2.save()

        self.assertRedirects(self.client.post(reverse("events:multibillings:new"), data_email),
                             reverse("events:multibillings:email", args=[1]))

        self.assertRedirects(self.client.post(reverse("events:multibillings:new"), data_no_email),
                             reverse("events:multibillings:list"))

        self.assertTrue(models.MultiBilling.objects.filter(amount=500.00).exists())
        self.assertTrue(models.MultiBilling.objects.filter(amount=400.00).exists())

    def test_multibill_edit(self):
        self.setup()

        multibill = models.MultiBilling.objects.create(date_billed=timezone.now().date(), amount=200.00)
        multibill.events.add(self.e)
        multibill.events.add(self.e2)

        # By default, user should not have permission to edit multibills
        self.assertOk(self.client.get(reverse("events:multibillings:edit", args=[multibill.pk])), 403)

        permission = Permission.objects.get(codename="bill_event")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("events:multibillings:edit", args=[multibill.pk])))

        # Check that if one or more event is closed we get permission denied
        self.e2.closed = True
        self.e2.save()

        self.assertOk(self.client.get(reverse("events:multibillings:edit", args=[multibill.pk])), 403)

        self.e2.closed = False
        self.e2.save()

        # Check with valid input
        valid_data = {
            "date_paid": timezone.now().date(),
            "amount": 400.00,
            "save": "Save Changes"
        }
        self.assertRedirects(self.client.post(reverse("events:multibillings:edit", args=[multibill.pk]), valid_data),
                             reverse("events:multibillings:list"))

        multibill.refresh_from_db()
        self.assertEqual(multibill.amount, 400.00)

    def test_multibill_delete(self):
        self.setup()

        multibill = models.MultiBilling.objects.create(date_billed=timezone.now().date(), amount=1000.00)
        multibill.events.add(self.e)
        multibill.events.add(self.e2)

        # By default, user should not have permission to delete multibills
        self.assertOk(self.client.get(reverse("events:multibillings:remove", args=[multibill.pk])), 403)

        permission = Permission.objects.get(codename="bill_event")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("events:multibillings:remove", args=[multibill.pk])))

        # Check that if one or more events is closed, we get permission denied
        self.e2.closed = True
        self.e2.save()

        self.assertOk(self.client.get(reverse("events:multibillings:remove", args=[multibill.pk])), 403)

        self.e2.closed = False
        self.e2.save()

        # Check that if the bill has been paid we cannot delete it
        multibill.date_paid = timezone.now().date()
        multibill.save()

        self.assertOk(self.client.get(reverse("events:multibillings:remove", args=[multibill.pk])), 403)

        multibill.date_paid = None
        multibill.save()

        # Test POST
        self.assertRedirects(self.client.post(reverse("events:multibillings:remove", args=[multibill.pk])),
                             reverse("events:multibillings:list"))

        self.assertFalse(models.MultiBilling.objects.filter(pk=multibill.pk).exists())

    def test_pay(self):
        self.setup()

        b = self.e.billings.create(date_billed=timezone.now().date(), amount=3.14)

        # random clicks wont work
        self.assertOk(self.client.get(reverse('events:bills:pay', args=[self.e.pk, b.pk])), 405)

        # User needs permission
        self.assertOk(self.client.post(reverse("events:bills:pay", args=[self.e.pk, b.pk])), 403)

        permission = Permission.objects.get(codename="bill_event")
        self.user.user_permissions.add(permission)

        # Will need view_event permission for redirect
        permission = Permission.objects.get(codename="view_events")
        self.user.user_permissions.add(permission)

        # If event is closed, redirect to detail page
        self.e.closed = True
        self.e.save()

        self.assertRedirects(self.client.post(reverse("events:bills:pay", args=[self.e.pk, b.pk])),
                             reverse("events:detail", args=[self.e.pk]))

        self.e.closed = False
        self.e.save()

        # on success, redirects to event page
        self.assertRedirects(self.client.post(reverse('events:bills:pay', args=[self.e.pk, b.pk])),
                             reverse("events:detail", args=[self.e.pk]) + "#billing")

        # check it is actually paid
        b.refresh_from_db()
        self.assertIsNotNone(b.date_paid)
        self.assertTrue(self.e.paid)

        # If bill has already been paid, redirect to next page
        self.assertRedirects(self.client.post(reverse("events:bills:pay", args=[self.e.pk, b.pk]) + "?next=/db/"),
                             reverse("home"))

    def test_billing_email(self):
        self.setup()

        b = self.e.billings.create(date_billed=timezone.now().date(), amount=75.95)

        # User needs permission to create a billing email
        self.assertOk(self.client.get(reverse("events:bills:email", args=[self.e.pk, b.pk])), 403)

        permission = Permission.objects.get(codename="bill_event")
        self.user.user_permissions.add(permission)

        # Will need view_event permission for the redirect
        permission = Permission.objects.get(codename="view_events")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("events:bills:email", args=[self.e.pk, b.pk])))

        # Test valid data
        valid_data = {
            "subject": "Your Bill",
            "message": "Thank you for choosing LNL! Now pay your bill.",
            "email_to_users": str(self.user.pk),
            "email_to_orgs": [],
            "save": "Send Email"
        }

        self.assertRedirects(self.client.post(reverse("events:bills:email", args=[self.e.pk, b.pk]), valid_data),
                             reverse("events:detail", args=[self.e.pk]) + "#billing")

    def test_multibilling_email(self):
        self.setup()

        b = self.e.multibillings.create(date_billed=timezone.now().date(), amount=1.50)

        # User needs permission to create a billing email
        self.assertOk(self.client.get(reverse("events:multibillings:email", args=[b.pk])), 403)

        permission = Permission.objects.get(codename="bill_event")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("events:multibillings:email", args=[b.pk])))

        # Test valid input
        valid_data = {
            "subject": "Your Bill",
            "message": "Welcome back valued customer! Here's your bill.",
            "email_to_users": str(self.user.pk),
            "email_to_orgs": [],
            "save": "Send Email"
        }

        self.assertRedirects(self.client.post(reverse("events:multibillings:email", args=[b.pk]), valid_data),
                             reverse("events:multibillings:list"))

    def test_workday_entry(self):
        self.setup()

        self.e3.billing_org = self.org
        self.e3.save()

        # Will need view_event permission for redirects
        permission = Permission.objects.get(codename="view_events")
        self.user.user_permissions.add(permission)

        # Should redirect to detail page - Event must have been reviewed
        self.assertRedirects(self.client.get(reverse("events:worktag-form", args=[self.e3.pk])),
                             reverse("events:detail", args=[self.e3.pk]))

        self.e3.reviewed = True
        self.e3.save()

        # Should redirect to detail page - Event has not yet been billed
        self.assertRedirects(self.client.get(reverse("events:worktag-form", args=[self.e3.pk])),
                             reverse("events:detail", args=[self.e3.pk]))

        bill = models.Billing.objects.create(event=self.e3, date_billed=timezone.now().date(), amount=5000.00)
        self.e3.closed = True
        self.e3.save()

        # Should redirect to detail page - Event is closed
        self.assertRedirects(self.client.get(reverse("events:worktag-form", args=[self.e3.pk])),
                             reverse("events:detail", args=[self.e3.pk]))

        self.e3.closed = False
        self.e3.save()
        bill.date_paid = timezone.now().date()
        bill.save()

        # Should redirect to detail page - Bill has already been paid
        self.assertRedirects(self.client.get(reverse("events:worktag-form", args=[self.e3.pk])),
                             reverse("events:detail", args=[self.e3.pk]))

        bill.date_paid = None
        bill.save()
        self.e3.entered_into_workday = True
        self.e3.save()

        # Should redirect to detail page - ISD for this event is already in Workday
        self.assertRedirects(self.client.get(reverse("events:worktag-form", args=[self.e3.pk])),
                             reverse("events:detail", args=[self.e3.pk]))

        self.e3.entered_into_workday = False
        self.e3.save()

        # User will need permission (also only works with Event2019 objects)
        self.assertOk(self.client.get(reverse("events:worktag-form", args=[self.e3.pk])), 403)

        permission = Permission.objects.get(codename="edit_org_billing")
        self.user.user_permissions.add(permission)

        # Should load ok
        self.assertOk(self.client.get(reverse("events:worktag-form", args=[self.e3.pk])))

        # Test POST with data
        invalid_tag = {
            "workday_fund": 810,
            "worktag": "Example",
            "workday_form_comments": "",
            "submit": "Pay"
        }

        self.assertOk(self.client.post(reverse("events:worktag-form", args=[self.e3.pk]), invalid_tag))

        valid_data = {
            "workday_fund": 810,
            "worktag": "1234-AB",
            "workday_form_comments": "",
            "submit": "Pay"
        }
        self.assertRedirects(self.client.post(reverse("events:worktag-form", args=[self.e3.pk]), valid_data),
                             reverse("events:detail", args=[self.e3.pk]))

        # Check that organization details were updated with worktag info (were initially blank)
        self.org.refresh_from_db()
        self.assertEqual(self.org.worktag, "1234-AB")
        self.assertEqual(self.org.workday_fund, 810)

        # Check that user is automatically added to the associated users list for the organization if not already on it
        self.assertIn(self.user, self.org.associated_users.all())

        revised_data = {
            "workday_fund": 810,
            "worktag": "5678-CC",
            "workday_form_comments": "I made a few adjustments",
            "submit": "Pay"
        }

        # Check that we can reload and submit the form again to edit details
        self.assertRedirects(self.client.post(reverse("events:worktag-form", args=[self.e3.pk]), revised_data),
                             reverse("events:detail", args=[self.e3.pk]))

    def test_entered_into_workday(self):
        self.setup()

        # GET should not be permitted
        self.assertOk(self.client.get(reverse("events:workday-entered", args=[self.e3.pk])), 405)

        # User will need permission
        self.assertOk(self.client.post(reverse("events:workday-entered", args=[self.e3.pk])), 403)

        permission = Permission.objects.get(codename="bill_event")
        self.user.user_permissions.add(permission)

        # Will need view_event permission for redirect
        permission = Permission.objects.get(codename="view_events")
        self.user.user_permissions.add(permission)

        # Should redirect to event detail page - Event has not yet been reviewed
        self.assertRedirects(self.client.post(reverse("events:workday-entered", args=[self.e3.pk])),
                             reverse("events:detail", args=[self.e3.pk]))

        self.e3.reviewed = True
        self.e3.closed = True
        self.e3.save()

        # Should redirect to event detail page - Event is closed
        self.assertRedirects(self.client.post(reverse("events:workday-entered", args=[self.e3.pk])),
                             reverse("events:detail", args=[self.e3.pk]))

        self.e3.closed = False
        self.e3.save()

        # Should redirect to event detail page - Event has not been billed
        self.assertRedirects(self.client.post(reverse("events:workday-entered", args=[self.e3.pk])),
                             reverse("events:detail", args=[self.e3.pk]))

        models.Billing.objects.create(event=self.e3, date_billed=timezone.now().date(), amount=26.33)

        # Should now be able to mark as entered into workday
        self.assertRedirects(self.client.post(reverse("events:workday-entered", args=[self.e3.pk])),
                             reverse("events:awaitingworkday"))

        # Check that we get no errors when trying to mark an event that has already been marked
        self.assertRedirects(self.client.post(reverse("events:workday-entered", args=[self.e3.pk])),
                             reverse("events:awaitingworkday"))


class EventListBasicViewTest(ViewTestCase):
    def setUp(self):
        super(EventListBasicViewTest, self).setUp()
        self.e = EventFactory.create(event_name="Test Event", sensitive=True,
                                     datetime_start=timezone.make_aware(timezone.datetime(2019, 12, 31, 11, 59)),
                                     datetime_end=timezone.make_aware(timezone.datetime(2020, 1, 1)))
        self.e2 = EventFactory.create(event_name="Other Event", test_event=True,
                                      datetime_start=timezone.make_aware(timezone.datetime(2020, 1, 1)),
                                      datetime_end=timezone.make_aware(timezone.datetime(2020, 2, 1)))

        self.e2019 = Event2019Factory.create(event_name="2019 Event", approved=True,
                                             datetime_start=timezone.make_aware(timezone.datetime(2020, 1, 1)),
                                             datetime_end=timezone.make_aware(timezone.datetime(2020, 1, 2)))
        proj = models.Category.objects.create(name="Projection")
        models.Category.objects.create(name="Lighting")
        models.Category.objects.create(name="Sound")
        service = ServiceFactory.create(category=proj, base_cost=100.00)
        models.ServiceInstance.objects.create(service=service, event=self.e2019)

    def generic_list(self, url):
        # Check that page loads ok (should not include either event)
        resp = self.client.get(reverse(url))
        self.assertOk(resp)
        self.assertNotContains(resp, "Test Event")
        self.assertNotContains(resp, "Other Event")

        # Check that even with proper date range we don't see sensitive or test events unless we have permission
        self.assertNotContains(self.client.get(reverse(url, args=['2019-12-30', '2020-02-02'])), "Test Event")

        self.e.sensitive = False
        self.e.save()

        self.assertContains(self.client.get(reverse(url, args=['2019-12-30', '2020-02-02'])), "Test Event")

        self.e.sensitive = True
        self.e.save()

        # Add view_hidden_event permission
        permission = Permission.objects.get(codename="view_hidden_event")
        self.user.user_permissions.add(permission)

        self.assertContains(self.client.get(reverse(url, args=['2019-12-30', '2020-02-02'])), "Test Event")

        self.assertNotContains(self.client.get(reverse(url, args=['2019-12-30', '2020-02-02'])), "Other Event")

        self.e2.test_event = False
        self.e2.save()

        self.assertContains(self.client.get(reverse(url, args=['2019-12-30', '2020-02-02'])), "Other Event")

        self.e2.test_event = True
        self.e2.save()

        # Add view_test_event permission
        permission = Permission.objects.get(codename="view_test_event")
        self.user.user_permissions.add(permission)

        self.assertContains(self.client.get(reverse(url, args=['2019-12-30', '2020-02-02'])), "Other Event")

        # Test projection cookies
        resp = self.client.get(reverse(url, args=['2019-12-30', '2020-02-02']) + "?projection=hide")
        self.assertOk(resp)
        self.assertNotContains(resp, "2019 Event")

        resp = self.client.get(reverse(url, args=['2019-12-30', '2020-02-02']) + "?projection=only")
        self.assertOk(resp)
        self.assertContains(resp, "2019 Event")
        self.assertNotContains(resp, "Test Event")

        resp = self.client.get(reverse(url, args=['2019-12-30', '2020-02-02']))
        self.assertRedirects(resp, reverse(url, args=['2019-12-30', '2020-02-02']) + "?projection=only")

    def base_cal_json(self, url):
        # Reset permissions
        permission = Permission.objects.get(codename="view_test_event")
        self.user.user_permissions.remove(permission)

        # Check that page loads ok (should not include either event)
        resp = self.client.get(reverse(url))
        self.assertOk(resp)
        self.assertNotContains(resp, "Test Event")
        self.assertNotContains(resp, "Other Event")

        # Check that even with proper date range we don't see sensitive or test events unless we have permission
        # Note we use Epoch timestamps here
        self.assertNotContains(self.client.get(reverse(url) + '?from=1577664000&to=1580601600&projection=show'),
                               "Test Event")

        self.e.sensitive = False
        self.e.save()

        self.assertContains(self.client.get(reverse(url) + '?from=1577664000&to=1580601600'), "Test Event")

        self.e.sensitive = True
        self.e.save()

        # Add view_hidden_event permission
        permission = Permission.objects.get(codename="event_view_sensitive")
        self.user.user_permissions.add(permission)

        self.assertContains(self.client.get(reverse(url) + '?from=1577664000&to=1580601600'), "Test Event")

        self.assertNotContains(self.client.get(reverse(url) + '?from=1577664000&to=1580601600'), "Other Event")

        self.e2.test_event = False
        self.e2.save()

        self.assertContains(self.client.get(reverse(url) + '?from=1577664000&to=1580601600'), "Other Event")

        self.e2.test_event = True
        self.e2.save()

        # Add view_test_event permission
        permission = Permission.objects.get(codename="view_test_event")
        self.user.user_permissions.add(permission)

        self.assertContains(self.client.get(reverse(url) + '?from=1577664000&to=1580601600'), "Other Event")

        # Test projection cookies
        resp = self.client.get(reverse(url) + '?from=1577664000&to=1580601600&projection=hide')
        self.assertOk(resp)
        self.assertNotContains(resp, "2019 Event")

        resp = self.client.get(reverse(url) + '?from=1577664000&to=1580601600&projection=only')
        self.assertOk(resp)
        self.assertContains(resp, "2019 Event")
        self.assertNotContains(resp, "Test Event")

    def test_public(self):
        response = self.client.get(reverse('cal:list'))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse('cal:api-public'))
        self.assertEqual(response.status_code, 200)

    def test_cal(self):
        response = self.client.get(reverse('cal:feed'))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse('cal:feed-full'))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse('cal:feed-light'))
        self.assertEqual(response.status_code, 200)

    def test_prospective(self):
        # By default, user should not have permission to view this page
        self.assertOk(self.client.get(reverse('events:prospective')), 403)

        permission = Permission.objects.get(codename="approve_event")
        self.user.user_permissions.add(permission)

        self.e2019.approved = False
        self.e2019.save()

        # Run generic tests
        self.generic_list('events:prospective')
        self.base_cal_json('cal:api-prospective')

    def test_prospective_cal(self):
        # By default, should not have permission to view
        self.assertOk(self.client.get(reverse("events:prospective-cal")), 403)

        permission = Permission.objects.get(codename="approve_event")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("events:prospective-cal")))

    # def test_incoming(self):
    #     # By default, user should not have permission to view events
    #     self.assertOk(self.client.get(reverse('events:incoming')), 403)

    #     permission = Permission.objects.get(codename="view_events")
    #     self.user.user_permissions.add(permission)

    #     self.e.event_status = "Incoming"
    #     self.e2.event_status = "Incoming"
    #     self.e.save()
    #     self.e2.save()

    #     # Run generic tests
    #     self.generic_list('events:incoming')

    # def test_findchief(self):
    #     # By default, user should not have permission to view events
    #     self.assertOk(self.client.get(reverse('events:findchief')), 403)

    #     permission = Permission.objects.get(codename="view_events")
    #     self.user.user_permissions.add(permission)

    #     self.e.event_status = "Incoming"
    #     self.e2.event_status = "Confirmed"
    #     self.e.save()
    #     self.e2.save()

    #     light = models.Category.objects.create(name="Lighting")
    #     lighting = models.Lighting.objects.create(category=light, shortname="L1", longname="Lighting", base_cost=20.00,
    #                                               addtl_cost=1.00)
    #     self.e.lighting = lighting
    #     self.e2.lighting = lighting
    #     self.e.save()
    #     self.e2.save()

    #     # Run generic tests
    #     self.generic_list('events:findchief')
    #     self.base_cal_json('cal:api-findchief')

    def test_chief_cal(self):
        # By default, should not have permission to view
        self.assertOk(self.client.get(reverse("events:findchief-cal")), 403)

        permission = Permission.objects.get(codename="view_events")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("events:findchief-cal")))

    def test_open(self):
        # By default, user should not have permission to view events
        self.assertOk(self.client.get(reverse('events:open')), 403)

        permission = Permission.objects.get(codename="view_events")
        self.user.user_permissions.add(permission)

        self.e.approved = True
        self.e2.approved = True
        self.e.save()
        self.e2.save()

        # Run generic tests
        self.generic_list('events:open')
        self.base_cal_json('cal:api-open')

    def test_open_cal(self):
        # By default, should not have permission to view
        self.assertOk(self.client.get(reverse("events:open-cal")), 403)

        permission = Permission.objects.get(codename="view_events")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("events:open-cal")))

    def test_unreviewed(self):
        # By default, user should not have permission to view events
        self.assertOk(self.client.get(reverse('events:unreviewed')), 403)

        permission = Permission.objects.get(codename="review_event")
        self.user.user_permissions.add(permission)

        self.e.approved = True
        self.e2.approved = True
        self.e.save()
        self.e2.save()

        # Run generic tests
        self.generic_list('events:unreviewed')
        self.base_cal_json('cal:api-unreviewed')

    def test_unreviewed_cal(self):
        # By default, should not have permission to view
        self.assertOk(self.client.get(reverse("events:unreviewed-cal")), 403)

        permission = Permission.objects.get(codename="review_event")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("events:unreviewed-cal")))

    def test_unbilled(self):
        # By default, user should not have permission to view events
        self.assertOk(self.client.get(reverse('events:unbilled')), 403)

        permission = Permission.objects.get(codename="bill_event")
        self.user.user_permissions.add(permission)

        self.e.reviewed = True
        self.e2.reviewed = True
        self.e2019.reviewed = True
        self.e.save()
        self.e2.save()
        self.e2019.save()

        # Run generic tests
        self.generic_list('events:unbilled')
        self.base_cal_json('cal:api-unbilled')

    def test_unbilled_cal(self):
        # By default, should not have permission to view
        self.assertOk(self.client.get(reverse("events:unbilled-cal")), 403)

        permission = Permission.objects.get(codename="bill_event")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("events:unbilled-cal")))

    def test_unbilled_semester(self):
        # By default, user should not have permission to view events
        self.assertOk(self.client.get(reverse('events:unbilled-semester')), 403)

        permission = Permission.objects.get(codename="bill_event")
        self.user.user_permissions.add(permission)

        self.e.reviewed = True
        self.e.billed_in_bulk = True
        self.e2.reviewed = True
        self.e2.billed_in_bulk = True
        self.e2019.reviewed = True
        self.e2019.billed_in_bulk = True
        self.e.save()
        self.e2.save()
        self.e2019.save()

        # Run generic tests
        self.generic_list('events:unbilled-semester')
        self.base_cal_json('cal:api-unbilled-semester')

    def test_unbilled_semester_cal(self):
        # By default, should not have permission to view
        self.assertOk(self.client.get(reverse("events:unbilled-semester-cal")), 403)

        permission = Permission.objects.get(codename="bill_event")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("events:unbilled-semester-cal")))

    def test_paid(self):
        # By default, user should not have permission to view events
        self.assertOk(self.client.get(reverse('events:paid')), 403)

        permission = Permission.objects.get(codename="close_event")
        self.user.user_permissions.add(permission)

        models.Billing.objects.create(date_billed=timezone.now().date(), date_paid=timezone.now().date(), event=self.e,
                                      amount=25.00)
        models.Billing.objects.create(date_billed=timezone.now().date(), date_paid=timezone.now().date(), event=self.e2,
                                      amount=300.00)
        models.Billing.objects.create(date_billed=timezone.now().date(), date_paid=timezone.now().date(),
                                      event=self.e2019, amount=0.00)

        # Run generic tests
        self.generic_list('events:paid')
        self.base_cal_json('cal:api-paid')

    def test_paid_cal(self):
        # By default, should not have permission to view
        self.assertOk(self.client.get(reverse("events:paid-cal")), 403)

        permission = Permission.objects.get(codename="close_event")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("events:paid-cal")))

    def test_unpaid(self):
        # By default, user should not have permission to view events
        self.assertOk(self.client.get(reverse('events:unpaid')), 403)

        permission = Permission.objects.get(codename="bill_event")
        self.user.user_permissions.add(permission)

        models.Billing.objects.create(date_billed=timezone.now().date(), event=self.e, amount=25.00)
        models.Billing.objects.create(date_billed=timezone.now().date(), event=self.e2, amount=300.00)
        models.Billing.objects.create(date_billed=timezone.now().date(), event=self.e2019, amount=0.00)
        self.e.reviewed = True
        self.e2.reviewed = True
        self.e2019.reviewed = True
        self.e.save()
        self.e2.save()
        self.e2019.save()

        # Run generic tests
        self.generic_list('events:unpaid')
        self.base_cal_json('cal:api-unpaid')

    def test_unpaid_cal(self):
        # By default, should not have permission to view
        self.assertOk(self.client.get(reverse("events:unpaid-cal")), 403)

        permission = Permission.objects.get(codename="bill_event")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("events:unpaid-cal")))

    def test_awaitingworkday(self):
        # By default, user should not have permission to view events
        self.assertOk(self.client.get(reverse('events:awaitingworkday')), 403)

        permission = Permission.objects.get(codename="bill_event")
        self.user.user_permissions.add(permission)

        # Only works with 2019 events
        e1 = Event2019Factory.create(event_name="Test Event", sensitive=True, reviewed=True, workday_fund=900,
                                     datetime_start=timezone.make_aware(timezone.datetime(2019, 12, 31, 11, 59)),
                                     datetime_end=timezone.make_aware(timezone.datetime(2020, 1, 1)), worktag="1234")
        e2 = Event2019Factory.create(event_name="Other Event", test_event=True, reviewed=True, workday_fund=900,
                                     datetime_start=timezone.make_aware(timezone.datetime(2020, 1, 1)),
                                     datetime_end=timezone.make_aware(timezone.datetime(2020, 2, 1)), worktag="1234")

        models.Billing.objects.create(date_billed=timezone.now().date(), event=e1, amount=0.00)
        models.Billing.objects.create(date_billed=timezone.now().date(), event=e2, amount=0.00)
        models.Billing.objects.create(date_billed=timezone.now().date(), event=self.e2019, amount=0.00)

        self.e2019.reviewed = True
        self.e2019.workday_fund = 900
        self.e2019.worktag = "1234"
        self.e2019.save()

        # Run generic tests
        # Check that page loads ok (should not include either event)
        resp = self.client.get(reverse("events:awaitingworkday"))
        self.assertOk(resp)
        self.assertNotContains(resp, "Test Event")
        self.assertNotContains(resp, "Other Event")

        # Check that even with proper date range we don't see sensitive or test events unless we have permission
        self.assertNotContains(self.client.get(reverse("events:awaitingworkday", args=['2019-12-30', '2020-02-02'])),
                               "Test Event")

        e1.sensitive = False
        e1.save()

        self.assertContains(self.client.get(reverse("events:awaitingworkday", args=['2019-12-30', '2020-02-02'])),
                            "Test Event")

        e1.sensitive = True
        e1.save()

        # Add view_hidden_event permission
        permission = Permission.objects.get(codename="view_hidden_event")
        self.user.user_permissions.add(permission)

        self.assertContains(self.client.get(reverse("events:awaitingworkday", args=['2019-12-30', '2020-02-02'])),
                            "Test Event")

        self.assertNotContains(self.client.get(reverse("events:awaitingworkday", args=['2019-12-30', '2020-02-02'])),
                               "Other Event")

        e2.test_event = False
        e2.save()

        self.assertContains(self.client.get(reverse("events:awaitingworkday", args=['2019-12-30', '2020-02-02'])),
                            "Other Event")

        e2.test_event = True
        e2.save()

        # Add view_test_event permission
        permission = Permission.objects.get(codename="view_test_event")
        self.user.user_permissions.add(permission)

        self.assertContains(self.client.get(reverse("events:awaitingworkday", args=['2019-12-30', '2020-02-02'])),
                            "Other Event")

        # Test projection cookies
        resp = self.client.get(reverse("events:awaitingworkday", args=['2019-12-30', '2020-02-02']) +
                               "?projection=hide")
        self.assertOk(resp)
        self.assertNotContains(resp, "2019 Event")

        resp = self.client.get(reverse("events:awaitingworkday", args=['2019-12-30', '2020-02-02']) +
                               "?projection=only")
        self.assertOk(resp)
        self.assertContains(resp, "2019 Event")
        self.assertNotContains(resp, "Test Event")

        resp = self.client.get(reverse("events:awaitingworkday", args=['2019-12-30', '2020-02-02']))
        self.assertRedirects(resp, reverse("events:awaitingworkday", args=['2019-12-30', '2020-02-02']) +
                             "?projection=only")

    def test_unpaid_workday(self):
        # By default, user should not have permission to view events
        self.assertOk(self.client.get(reverse('events:unpaid-workday')), 403)

        permission = Permission.objects.get(codename="bill_event")
        self.user.user_permissions.add(permission)

        # Only works with 2019 events
        e1 = Event2019Factory.create(event_name="Test Event", sensitive=True, reviewed=True, entered_into_workday=True,
                                     datetime_start=timezone.make_aware(timezone.datetime(2019, 12, 31, 11, 59)),
                                     datetime_end=timezone.make_aware(timezone.datetime(2020, 1, 1)))
        e2 = Event2019Factory.create(event_name="Other Event", reviewed=True, entered_into_workday=True,
                                     datetime_start=timezone.make_aware(timezone.datetime(2020, 1, 1)),
                                     datetime_end=timezone.make_aware(timezone.datetime(2020, 2, 1)), test_event=True)

        models.Billing.objects.create(date_billed=timezone.now().date(), event=e1, amount=0.00)
        models.Billing.objects.create(date_billed=timezone.now().date(), event=e2, amount=0.00)
        models.Billing.objects.create(date_billed=timezone.now().date(), event=self.e2019, amount=0.00)

        self.e2019.reviewed = True
        self.e2019.entered_into_workday = True
        self.e2019.save()

        # Run generic tests
        # Check that page loads ok (should not include either event)
        resp = self.client.get(reverse("events:unpaid-workday"))
        self.assertOk(resp)
        self.assertNotContains(resp, "Test Event")
        self.assertNotContains(resp, "Other Event")

        # Check that even with proper date range we don't see sensitive or test events unless we have permission
        self.assertNotContains(self.client.get(reverse("events:unpaid-workday", args=['2019-12-30', '2020-02-02'])),
                               "Test Event")

        e1.sensitive = False
        e1.save()

        self.assertContains(self.client.get(reverse("events:unpaid-workday", args=['2019-12-30', '2020-02-02'])),
                            "Test Event")

        e1.sensitive = True
        e1.save()

        # Add view_hidden_event permission
        permission = Permission.objects.get(codename="view_hidden_event")
        self.user.user_permissions.add(permission)

        self.assertContains(self.client.get(reverse("events:unpaid-workday", args=['2019-12-30', '2020-02-02'])),
                            "Test Event")

        self.assertNotContains(self.client.get(reverse("events:unpaid-workday", args=['2019-12-30', '2020-02-02'])),
                               "Other Event")

        e2.test_event = False
        e2.save()

        self.assertContains(self.client.get(reverse("events:unpaid-workday", args=['2019-12-30', '2020-02-02'])),
                            "Other Event")

        e2.test_event = True
        e2.save()

        # Add view_test_event permission
        permission = Permission.objects.get(codename="view_test_event")
        self.user.user_permissions.add(permission)

        self.assertContains(self.client.get(reverse("events:unpaid-workday", args=['2019-12-30', '2020-02-02'])),
                            "Other Event")

        # Test projection cookies
        resp = self.client.get(reverse("events:unpaid-workday", args=['2019-12-30', '2020-02-02']) +
                               "?projection=hide")
        self.assertOk(resp)
        self.assertNotContains(resp, "2019 Event")

        resp = self.client.get(reverse("events:unpaid-workday", args=['2019-12-30', '2020-02-02']) +
                               "?projection=only")
        self.assertOk(resp)
        self.assertContains(resp, "2019 Event")
        self.assertNotContains(resp, "Test Event")

        resp = self.client.get(reverse("events:unpaid-workday", args=['2019-12-30', '2020-02-02']))
        self.assertRedirects(resp, reverse("events:unpaid-workday", args=['2019-12-30', '2020-02-02']) +
                             "?projection=only")

    def test_closed(self):
        # By default, user should not have permission to view events
        self.assertOk(self.client.get(reverse('events:closed')), 403)

        permission = Permission.objects.get(codename="view_events")
        self.user.user_permissions.add(permission)

        self.e.closed = True
        self.e2.closed = True
        self.e2019.closed = True
        self.e.save()
        self.e2.save()
        self.e2019.save()

        # Run generic tests
        self.generic_list('events:closed')
        self.base_cal_json('cal:api-closed')

    def test_closed_cal(self):
        # By default, should not have permission to view
        self.assertOk(self.client.get(reverse("events:closed-cal")), 403)

        permission = Permission.objects.get(codename="view_events")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("events:closed-cal")))

    def test_all(self):
        # By default, user should not have permission to view events
        self.assertOk(self.client.get(reverse('events:all')), 403)

        permission = Permission.objects.get(codename="view_events")
        self.user.user_permissions.add(permission)

        # Without approve permission, non-approved events won't appear
        self.e.approved = True
        self.e2.approved = True
        self.e2019.approved = True
        self.e.save()
        self.e2.save()
        self.e2019.save()

        # Run generic tests
        self.generic_list('events:all')
        self.base_cal_json('cal:api-all')

    def test_all_cal(self):
        # By default, should not have permission to view
        self.assertOk(self.client.get(reverse("events:all-cal")), 403)

        permission = Permission.objects.get(codename="view_events")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("events:all-cal")))

    def test_ical_generation(self):
        # Check timezone
        if settings.TIME_ZONE == "UTC":
            tz = b''
            start = timezone.make_aware(timezone.datetime(2019, 12, 31, 11, 59)).strftime('%Y%m%dT%H%M%SZ')\
                .encode('utf-8')
            end = timezone.make_aware(timezone.datetime(2020, 1, 1)).strftime('%Y%m%dT%H%M%SZ').encode('utf-8')
        else:
            tz = b'TZID=' + settings.TIME_ZONE.encode('utf-8')
            start = timezone.make_aware(timezone.datetime(2019, 12, 31, 11, 59)).strftime('%Y%m%dT%H%M%S')\
                .encode('utf-8')
            end = timezone.make_aware(timezone.datetime(2020, 1, 1)).strftime('%Y%m%dT%H%M%S').encode('utf-8')
        
        # Test with no attendees
        now = timezone.now().strftime('%Y%m%dT%H%M%SZ').encode('utf-8')
        expected = b'BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//WPI Lens and Lights//LNLDB//EN\r\n' \
                   b'METHOD:PUBLISH\r\nBEGIN:VEVENT\r\nSUMMARY:Test Event\r\nDTSTART;' + tz + b':' + \
                   start + b'\r\nDTEND;' + tz + b':' + end + b'\r\nDTSTAMP:' + now + \
                   b'\r\nUID:event1@lnldb\r\nDESCRIPTION:Requested by \r\nLOCATION:\r\n' \
                   b'URL:http://lnl.wpi.edu/db/events/view/1/\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n'
        output = cal.generate_ics([self.e], None)
        self.assertEqual(output, expected)

        # Test response when set to generate a request
        now = timezone.now().strftime('%Y%m%dT%H%M%SZ').encode('utf-8')
        expected = b'BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//WPI Lens and Lights//LNLDB//EN\r\n' \
                   b'METHOD:REQUEST\r\nBEGIN:VEVENT\r\nSUMMARY:Test Event\r\nDTSTART;' + tz + b':' + \
                   start + b'\r\nDTEND;' + tz + b':' + end + b'\r\nDTSTAMP:' + now + \
                   b'\r\nUID:event1@lnldb\r\nDESCRIPTION:Requested by \r\nLOCATION:\r\n' \
                   b'URL:http://lnl.wpi.edu/db/events/view/1/\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n'
        output = cal.generate_ics([self.e], None, True)
        self.assertEqual(output, expected)

        # Test with multiple attendees for multiple events (should only add two attendees)
        self.user.first_name = "Test"
        self.user.last_name = "User"
        self.user.save()
        attendee1 = cal.EventAttendee(self.e, self.user)
        attendee2 = cal.EventAttendee(self.e, self.user, False)
        attendee3 = cal.EventAttendee(self.e2, self.user)
        now = timezone.now().strftime('%Y%m%dT%H%M%SZ').encode('utf-8')
        expected = b'BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//WPI Lens and Lights//LNLDB//EN\r\n' \
                   b'METHOD:PUBLISH\r\nBEGIN:VEVENT\r\nSUMMARY:Test Event\r\nDTSTART;' + tz + b':' + \
                   start + b'\r\nDTEND;' + tz + b':' + end + b'\r\nDTSTAMP:' + now + \
                   b'\r\nUID:event1@lnldb\r\nATTENDEE;CN="Test User";ROLE=REQ-PARTICIPANT;' \
                   b'RSVP=FALSE:MAILTO:abc@foo.com\r\nATTENDEE;CN="Test User";ROLE=OPT-PARTICIPANT;' \
                   b'RSVP=FALSE:MAILTO:abc@foo.com\r\nDESCRIPTION:Requested by \r\nLOCATION:\r\n' \
                   b'URL:http://lnl.wpi.edu/db/events/view/1/\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n'
        output = cal.generate_ics([self.e], [attendee1, attendee2, attendee3])
        self.assertEqual(output, expected)


class WorkshopTests(ViewTestCase):
    def test_workshops_list(self):
        self.assertEqual(self.client.get(reverse("events:workshops:list")).status_code, 403)

        permission = Permission.objects.get(codename="edit_workshops")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("events:workshops:list")))

    def test_edit_workshop(self):
        workshop = models.Workshop.objects.create(name="Test Workshop", instructors="John, Peter, Janice",
                                                  location="Alden Hall",
                                                  description="Human Resources wants us to go over the Acceptable Use "
                                                              "Policy again.", notes="This sounds boring")
        workshop.save()

        self.assertEqual(self.client.get(reverse("events:workshops:edit", args=[workshop.pk])).status_code, 403)

        permission = Permission.objects.get(codename="edit_workshops")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("events:workshops:edit", args=[workshop.pk])))

        valid_data = {
            'name': 'Test Event',
            'description': 'A test event',
            'instructors': 'John Doe',
            'location': 'Alden',
            'notes': 'None'
        }
        self.assertRedirects(self.client.post(reverse("events:workshops:edit", args=[1]), valid_data),
                             reverse("events:workshops:list"))

    def test_new_workshop(self):
        self.assertEqual(self.client.get(reverse("events:workshops:add")).status_code, 403)

        permission = Permission.objects.get(codename="edit_workshops")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("events:workshops:add")))

        valid_data = {
            'name': 'Test Event',
            'description': 'A test event',
            'instructors': 'John Doe',
            'location': 'Alden',
            'notes': 'None'
        }
        self.assertRedirects(self.client.post(reverse("events:workshops:add"), valid_data),
                             reverse("events:workshops:list"))
        workshop = models.Workshop.objects.get(name="Test Event")
        self.assertEqual(workshop.description, "A test event")

    def test_workshop_dates(self):
        workshop = models.Workshop.objects.create(name="Test Workshop", instructors="John, Peter, Janice",
                                                  location="Alden Hall",
                                                  description="Human Resources wants us to go over the Acceptable Use "
                                                              "Policy again.", notes="This sounds boring")
        workshop.save()

        self.assertEqual(self.client.get(reverse("events:workshops:dates", args=[workshop.pk])).status_code, 403)

        permission = Permission.objects.get(codename="edit_workshops")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("events:workshops:dates", args=[workshop.pk])))

        valid_data = {
            "form-TOTAL_FORMS": 1,
            "form-INITIAL_FORMS": 0,
            "form-MIN_NUM_FORMS": 0,
            "form-MAX_NUM_FORMS": 1000,
            "form-0-day": 1,
            "form-0-hour_start": timezone.now().time(),
            "form-0-hour_end": timezone.now().time(),
            "form-0-DELETE": False,
            "save": "Save Changes"
        }

        self.assertRedirects(self.client.post(reverse("events:workshops:dates", args=[workshop.pk]), valid_data),
                             reverse("events:workshops:list"))

    def test_delete_workshop(self):
        workshop = models.Workshop.objects.create(name="Test Workshop", instructors="John, Peter, Janice",
                                                  location="Alden Hall",
                                                  description="Human Resources wants us to go over the Acceptable Use "
                                                              "Policy again.", notes="This sounds boring")
        workshop.save()

        self.assertOk(self.client.get(reverse("events:workshops:delete", args=[workshop.pk])), 403)

        permission = Permission.objects.get(codename="edit_workshops")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("events:workshops:delete", args=[workshop.pk])))

        self.assertRedirects(self.client.post(reverse("events:workshops:delete", args=[workshop.pk])),
                             reverse("events:workshops:list"))

        self.assertFalse(models.Workshop.objects.all().filter(name="Test Workshop").exists())


class EventIndices(ViewTestCase):
    def test_index(self):
        self.assertOk(self.client.get(reverse("index")))

    def test_admin(self):
        self.assertOk(self.client.get(reverse("home")))

    def test_event_search(self):
        EventFactory(event_name="Test Event")

        # By default, should not have access to search events
        self.assertOk(self.client.get(reverse("events-search")), 403)

        permission = Permission.objects.get(codename="view_events")
        self.user.user_permissions.add(permission)

        # If query is too short, display message
        self.assertContains(self.client.get(reverse("events-search"), {'q': 'hi'}), "Too Short")

        # Otherwise return events
        self.assertOk(self.client.get(reverse("events-search"), {'q': 'test'}))

    def test_survey_dashboard(self):
        event = EventFactory(event_name="An Event", datetime_start=timezone.now() + timezone.timedelta(days=-2),
                             datetime_end=timezone.now() + timezone.timedelta(minutes=-30), approved=True)
        second_event = Event2019Factory(event_name="Another Event", approved=True,
                                        datetime_end=timezone.now() + timezone.timedelta(minutes=-1),
                                        datetime_start=timezone.now() + timezone.timedelta(days=-1))
        models.PostEventSurvey.objects.create(event=event, person=self.user, services_quality=1, lighting_quality=2,
                                              sound_quality=3, work_order_method=1, work_order_experience=4,
                                              work_order_ease=-1, communication_responsiveness=0, pricelist_ux=1,
                                              setup_on_time=2, crew_respectfulness=3, price_appropriate=4,
                                              customer_would_return=4, comments="Things were alright")
        models.PostEventSurvey.objects.create(event=second_event, person=self.user, services_quality=-1,
                                              lighting_quality=-1, sound_quality=-1, work_order_method=2,
                                              work_order_experience=-1, work_order_ease=-1, pricelist_ux=-1,
                                              communication_responsiveness=-1, setup_on_time=-1, crew_respectfulness=-1,
                                              price_appropriate=-1, customer_would_return=-1)

        # By default, use should not have permission to view the dashboard
        self.assertOk(self.client.get(reverse("survey-dashboard")), 403)

        permission = Permission.objects.get(codename="view_posteventsurveyresults")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("survey-dashboard")))


class EventTemplateTags(TestCase):
    def test_append_get(self):
        request = RequestFactory()
        get_dict = {'test': 'test-content'}
        request.GET = QueryDict('', mutable=True)
        request.GET.update(get_dict)
        context = {'request': request}

        # Test with that we don't append item if argument is None
        self.assertEqual(append_get.append_to_get(context, True, page=None), "?test=test-content")

        # Test that replace=True overwrites existing items (if applicable)
        self.assertEqual(append_get.append_to_get(context, True, test=None), "")

        # Test that we can append items when everything is normal
        self.assertEqual(append_get.append_to_get(context, True, page=1), "?test=test-content&page=1")

        # Check that replace=False allows duplicate
        self.assertEqual(append_get.append_to_get(context, False, test='something-else'),
                         "?test=test-content&test=something-else")

    def test_eventlink(self):
        event = EventFactory.create(event_name="Test Event")
        test_with_link = "If you would like more information about @1 then you should read my report"
        test_without_link = "You should read some of those reports from previous events"

        self.assertEqual(
            at_event_linking.eventlink(test_with_link),
            "If you would like more information about <a href=\"" + reverse("events:detail", args=[event.pk]) +
            "\">@Test Event</a> then you should read my report"
        )

        self.assertEqual(
            at_event_linking.eventlink(test_with_link, "events:add-crew"),
            "If you would like more information about <a href=\"" + reverse("events:add-crew", args=[event.pk]) +
            "\">@Test Event</a> then you should read my report"
        )

        self.assertEqual(at_event_linking.eventlink(test_without_link), test_without_link)

    def test_mdeventlink(self):
        event = EventFactory.create(event_name="Test Event")
        test_with_link = "If you would like more information about @1 then you should read my report"
        test_without_link = "You should read some of those reports from previous events"

        self.assertEqual(
            at_event_linking.mdeventlink(test_with_link),
            "If you would like more information about [@Test Event](" + reverse("events:detail", args=[event.pk]) +
            ") then you should read my report"
        )

        self.assertEqual(
            at_event_linking.mdeventlink(test_with_link, "events:add-crew"),
            "If you would like more information about [@Test Event](" + reverse("events:add-crew", args=[event.pk]) +
            ") then you should read my report"
        )

        self.assertEqual(at_event_linking.mdeventlink(test_without_link), test_without_link)

    def test_gpa_scale_emoji(self):
        value = None
        self.assertEqual(gpa_scale_emoji.gpa_scale_emoji(value), u'\U00002753')

        value = 0.5
        self.assertEqual(gpa_scale_emoji.gpa_scale_emoji(value), u'\U00002620')

        value = 1.5
        self.assertEqual(gpa_scale_emoji.gpa_scale_emoji(value), u'\U0001f621')

        value = 2.5
        self.assertEqual(gpa_scale_emoji.gpa_scale_emoji(value), u'\U0001f641')

        value = 3.5
        self.assertEqual(gpa_scale_emoji.gpa_scale_emoji(value), u'\U0001f610')

        value = 4.0
        self.assertEqual(gpa_scale_emoji.gpa_scale_emoji(value), u'\U0001f600')

        value = 5.0
        self.assertEqual(gpa_scale_emoji.gpa_scale_emoji(value), 'ERROR')

    def test_gpa_scale_clean(self):
        value = None
        self.assertEqual(gpa_scale_emoji.gpa_scale_clean(value), 'N/A')

        value = -1
        self.assertEqual(gpa_scale_emoji.gpa_scale_clean(value), 'N/A')

        value = 2.56
        self.assertEqual(gpa_scale_emoji.gpa_scale_clean(value), '2.6')

    def test_gpa_scale_color(self):
        value = None
        self.assertEqual(gpa_scale_emoji.gpa_scale_color(value), 'gray')

        value = -1
        self.assertEqual(gpa_scale_emoji.gpa_scale_color(value), 'gray')

        value = 0
        self.assertEqual(gpa_scale_emoji.gpa_scale_color(value), 'red')

        value = 1
        self.assertEqual(gpa_scale_emoji.gpa_scale_color(value), 'red')

        value = 2
        self.assertEqual(gpa_scale_emoji.gpa_scale_color(value), 'orange')

        value = 3
        self.assertEqual(gpa_scale_emoji.gpa_scale_color(value), 'gray')

        value = 4
        self.assertEqual(gpa_scale_emoji.gpa_scale_color(value), 'green')


class LookupTests(ViewTestCase):
    def test_org_lookup(self):
        org = OrgFactory.create(name="Lens & Lights", shortname="LNL")

        request_factory = RequestFactory()
        request = request_factory.get("/", {'term': 'test'})
        request.user = self.user
        lookup = lookups.OrgLookup()
        lookup_limited = lookups.UserLimitedOrgLookup()
        self.assertTrue(lookup.check_auth(request))
        self.assertTrue(lookup_limited.check_auth(request))

        # Test get_query with bogus query
        self.assertEqual(list(lookup.get_query('1234', request)), [])
        self.assertEqual(list(lookup_limited.get_query('1234', request)), [])

        # Test that if user is not associated with org, it does not appear in limited lookup
        self.assertEqual(list(lookup_limited.get_query('LNL', request)), [])

        org.user_in_charge = self.user
        org.save()

        # Test get_query with valid query
        self.assertIn(org, list(lookup.get_query('LNL', request)))
        self.assertIn(org, list(lookup_limited.get_query('LNL', request)))

        # Test format_match with default user
        self.assertEqual(lookup.format_match(org), "&nbsp;<strong>Lens &amp; Lights</strong>")
        self.assertEqual(lookup_limited.format_match(org), "&nbsp;<strong>Lens &amp; Lights</strong>")
