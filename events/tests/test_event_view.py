import logging
import pytz
from django.urls import reverse
from django.contrib.auth.models import Permission, Group
from django.http import QueryDict
from django.test import TestCase
from django.test.client import RequestFactory
from data.tests.util import ViewTestCase
from django.utils import timezone

from .generators import CCReportFactory, EventFactory, Event2019Factory, UserFactory, OrgFactory, CCInstanceFactory, \
    ServiceFactory
from .. import models


logging.disable(logging.WARNING)


class EventBasicViewTest(ViewTestCase):
    def setup(self):
        self.e = EventFactory.create(event_name="Test Event")
        self.e2 = EventFactory.create(event_name="Other Test Event")
        self.e3 = Event2019Factory.create(event_name="2019 Test Event")
        self.report = CCReportFactory.create(event=self.e)

    # def test_pay(self):
    #     self.setup()
    #     b = self.e.billings.create(date_billed=datetime.date(2000, 1, 1), amount=3.14)
    #
    #     # random clicks wont work
    #     self.assertOk(self.client.get(reverse('events:bills:pay', args=[self.e.pk, b.pk])), 405)
    #
    #     # on success, redirects to event page
    #     self.assertRedirects(self.client.post(reverse('events:bills:pay', args=[self.e.pk, b.pk])),
    #                          reverse("events:detail", args=[self.e.pk]))
    #
    #     # check it is actually paid
    #     b.refresh_from_db()
    #     self.assertIsNotNone(b.date_paid)
    #     self.assertTrue(self.e.paid)
    #
    #     # TODO: Test perms
    #
    # def test_detail(self):
    #     self.setup()
    #     self.assertOk(self.client.get(reverse('events:detail', args=[self.e.pk])))
    #
    #     # TODO: Test perms
    #
    # def test_edit(self):
    #     self.setup()
    #     self.assertOk(self.client.get(reverse('events:edit', args=[self.e.pk])))
    #
    #     # Bad input
    #     self.assertOk(self.client.post(reverse('events:edit', args=[self.e.pk])))
    #
    #     # TODO: Test POST and perms

    def test_cancel(self):
        self.setup()

        # Only POST should be permitted
        self.assertOk(self.client.get(reverse("events:cancel", args=[self.e.pk])), 405)

        # By default user should not have permission to cancel events
        self.assertOk(self.client.post(reverse("events:cancel", args=[self.e.pk])), 403)

        permission = Permission.objects.get(codename="cancel_event")
        self.user.user_permissions.add(permission)

        # Will also need view_event permissions for redirect
        permission = Permission.objects.get(codename="view_event")
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
        permission = Permission.objects.get(codename="view_event")
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
        permission = Permission.objects.get(codename="view_event")
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
        permission = Permission.objects.get(codename="view_event")
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
        permission = Permission.objects.get(codename="view_event")
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
        permission = Permission.objects.get(codename="view_event")
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

    def test_reviewremind(self):
        self.setup()

        # By default, user should not have this power
        self.assertOk(self.client.get(reverse("events:remind", args=[self.e.pk, self.user.pk])), 403)

        permission = Permission.objects.get(codename="review_event")
        self.user.user_permissions.add(permission)

        # This user will also need view_event permissions for redirects
        permission = Permission.objects.get(codename="view_event")
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
        permission = Permission.objects.get(codename="view_event")
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
        permission = Permission.objects.get(codename="view_event")
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
        permission = Permission.objects.get(codename="view_event")
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
        permission = Permission.objects.get(codename="view_event")
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
        permission = Permission.objects.get(codename="view_event")
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
        self.e3.max_crew = 1
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

        self.assertRedirects(self.client.post(reverse("events:crew-checkin"), valid_data),
                             reverse("events:detail", args=[self.e3.pk]))
        self.assertTrue(self.e3.hours.filter(user=self.user).exists())
        self.assertEqual(models.CrewAttendanceRecord.objects.filter(active=True, user=self.user).count(), 1)

        # Check that we cannot checkin again until we have checked out
        self.assertOk(self.client.post(reverse("events:crew-checkin"), valid_data))

        record = models.CrewAttendanceRecord.objects.get(active=True, user=self.user)
        record.active = False
        record.save()

        user2 = UserFactory.create(password="123")
        models.CrewAttendanceRecord.objects.create(event=self.e3, user=user2, active=True)

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
        tz = pytz.timezone('US/Eastern')
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
        self.assertIn("Welcome", self.client.post(url, valid_scan).content)
        self.assertTrue(self.e3.crew_attendance.filter(active=True, user=self.user).exists())

        # Check that checkout works ok next
        self.assertIn("Bye", self.client.post(url, valid_scan).content)
        self.assertFalse(self.e3.crew_attendance.filter(active=True, user=self.user).exists())

        second_event = Event2019Factory.create(event_name="Some other test event")
        second_record = models.CrewAttendanceRecord.objects.create(event=second_event, user=self.user, active=True)

        # Check that if user is checked in elsewhere that they cannot check in here
        self.assertIn("Checkin Failed", self.client.post(url, valid_scan).content)

        second_record.event = self.e3
        second_record.user = UserFactory.create(password="456")
        second_record.save()

        # Check that if crew limit is reached we cannot checkin
        self.assertIn("limit", self.client.post(url, valid_scan).content)

        # TODO: Valid swipe
        # TODO: Invalid swipe

    # def test_rmcc(self):
    #
    # def test_assigncc(self):
    #
    # def test_assignattach(self):
    #
    # def test_assignattach_external(self):
    #
    # def test_extras(self):
    #
    # def test_oneoff(self):

    # def test_ccr_add(self):
    #     response = self.client.get(reverse("events:reports:new", args=[self.e.pk]))
    #     self.assertEqual(response.status_code, 200)
    #
    #     # Empty (bad) input
    #     response = self.client.post(reverse("events:reports:new", args=[self.e.pk]))
    #     self.assertEqual(response.status_code, 200)
    #
    #     # later: test post saved
    #
    # def test_ccr_edit(self):
    #     response = self.client.get(reverse("events:reports:edit", args=[self.e.pk, self.report.pk]))
    #     self.assertEqual(response.status_code, 200)
    #
    #     # Empty (bad) input
    #     response = self.client.post(reverse("events:reports:edit", args=[self.e.pk, self.report.pk]))
    #     self.assertEqual(response.status_code, 200)
    #
    #     # later: test post saved
    #
    # def test_myccr_add(self):
    #     response = self.client.get(reverse("my:report", args=[self.e.pk]))
    #     self.assertEqual(response.status_code, 200)
    #
    #     # Bad (empty) input
    #     response = self.client.post(reverse("my:report", args=[self.e.pk]))
    #     self.assertEqual(response.status_code, 200)
    #
    #     # later: test post saved
    #
    # def test_bill_add(self):
    #     response = self.client.get(reverse("events:bills:new", args=[self.e.pk]))
    #     self.assertEqual(response.status_code, 200)
    #
    #     # Bad input
    #     response = self.client.post(reverse("events:bills:new", args=[self.e.pk]))
    #     self.assertEqual(response.status_code, 200)
    #
    #     # later: test post


class EventListBasicViewTest(TestCase):
    def setUp(self):
        self.e = EventFactory.create(event_name="Test Event")
        self.e2 = EventFactory.create(event_name="Other Test Event")
        self.user = UserFactory.create(password='123')
        self.client.login(username=self.user.username, password='123')

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

    def test_incoming(self):
        response = self.client.get(reverse('events:incoming'))
        self.assertEqual(response.status_code, 200)

    def test_upcoming(self):
        response = self.client.get(reverse('events:upcoming'))
        self.assertEqual(response.status_code, 200)

    def test_findchief(self):
        response = self.client.get(reverse('events:findchief'))
        self.assertEqual(response.status_code, 200)

    def test_open(self):
        response = self.client.get(reverse('events:open'))
        self.assertEqual(response.status_code, 200)

    def test_unreviewed(self):
        response = self.client.get(reverse('events:unreviewed'))
        self.assertEqual(response.status_code, 200)

    def test_unbilled(self):
        response = self.client.get(reverse('events:unbilled'))
        self.assertEqual(response.status_code, 200)

    def test_unbilled_semester(self):
        response = self.client.get(reverse('events:unbilled-semester'))
        self.assertEqual(response.status_code, 200)

    def test_paid(self):
        response = self.client.get(reverse('events:paid'))
        self.assertEqual(response.status_code, 200)

    def unpaid(self):
        response = self.client.get(reverse('events:unpaid'))
        self.assertEqual(response.status_code, 200)

    def closed(self):
        response = self.client.get(reverse('events:closed'))
        self.assertEqual(response.status_code, 200)


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
