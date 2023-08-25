import logging
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from model_mommy import mommy

from data.tests.util import ViewTestCase
from ..models import EventCCInstance, OfficeHour, Category, Lighting, Hours, ServiceInstance, OrganizationTransfer
from .generators import UserFactory, EventFactory, OrgFactory, CCInstanceFactory, Event2019Factory, ServiceFactory, \
    LocationFactory

logging.disable(logging.WARNING)


class MyViewTest(ViewTestCase):
    def setUp(self):
        super(MyViewTest, self).setUp()
        self.e = EventFactory.create(event_name="Test Event")
        self.e2 = EventFactory.create(event_name="Other Test Event")
        self.e3 = Event2019Factory.create(event_name="2019 Event")
        self.org = OrgFactory.create(user_in_charge=self.user)
        self.org2 = OrgFactory.create()
        self.org2.associated_users.add(self.user)

    def test_my_wo_blank(self):
        response = self.client.get(reverse("my:workorders"))
        self.assertNotContains(response, self.e.event_name)
        # check that it starts with no events

    def test_my_wo_owner(self):
        self.e.org.add(self.org)
        self.e.save()

        response = self.client.get(reverse("my:workorders"))
        self.assertContains(response, self.e.event_name)
        # I am an org owner. I see my org's events

    def test_my_wo_assoc(self):
        self.e.org.add(self.org2)
        self.e.save()

        response = self.client.get(reverse("my:workorders"))
        self.assertContains(response, self.e.event_name)
        # I am an org associate member. I see my org's events.

    def test_my_wo_submitted(self):
        self.e.submitted_by = self.user
        self.e.save()

        response = self.client.get(reverse("my:workorders"))
        self.assertContains(response, self.e.event_name)
        # I see the events I submitted

    def test_my_events(self):
        self.e.submitted_by = self.user
        self.e.save()

        response = self.client.get(reverse("my:events"))
        self.assertContains(response, self.e.event_name)
        # I can see events I've been involved with

    def test_event_files(self):
        # Will need view_event permission
        permission = Permission.objects.get(codename="view_events")
        self.user.user_permissions.add(permission)

        self.assertRedirects(self.client.get(reverse("my:event-files", args=[self.e.pk])),
                             reverse('events:detail', args=[self.e.pk]) + '#files')

    def test_hours_list(self):
        CCInstanceFactory.create(crew_chief=self.user, event=self.e, setup_start=timezone.now())

        self.assertOk(self.client.get(reverse("my:hours-list", args=[self.e.pk])))

    def test_add_hours(self):
        CCInstanceFactory.create(crew_chief=self.user, event=self.e, setup_start=timezone.now())
        CCInstanceFactory.create(crew_chief=self.user, event=self.e3, setup_start=timezone.now())
        category = Category.objects.create(name="Lighting")
        l1 = Lighting.objects.create(shortname="L1", longname="Lighting", base_cost=1000.00, addtl_cost=1.00,
                                     category=category)

        # Check that lateness doesn't matter
        self.e.lighting = l1
        self.e.datetime_end = timezone.now() - timezone.timedelta(days=30)
        self.e.save()

        self.assertNotContains(self.client.get(reverse("my:hours-new", args=[self.e.pk])), "Cannot Edit Report")

        self.e.datetime_end = timezone.now()
        self.e.save()

        self.assertNotContains(self.client.get(reverse("my:hours-new", args=[self.e.pk])), "Cannot Edit Report")

        # Check valid post
        valid_data = {
            "user": str(self.user.pk),
            "hours": 5.00,
            "service": str(l1.pk),
            "save": "Save Changes"
        }

        self.assertRedirects(self.client.post(reverse("my:hours-new", args=[self.e.pk]), valid_data),
                             reverse("my:hours-list", args=[self.e.pk]))

        # Handle new 2019 events
        self.assertRedirects(self.client.get(reverse("my:hours-new", args=[self.e3.pk])),
                             reverse("my:hours-bulk", args=[self.e3.pk]))

    def test_edit_hours(self):
        CCInstanceFactory.create(crew_chief=self.user, event=self.e, setup_start=timezone.now())
        Hours.objects.create(event=self.e, user=self.user, hours=2.00)
        category = Category.objects.create(name="Lighting")
        l1 = Lighting.objects.create(shortname="L2", longname="More Lighting", base_cost=1000.00, addtl_cost=1.00,
                                     category=category)

        # Check that lateness doesn't matter
        self.e.lighting = l1
        self.e.datetime_end = timezone.now() - timezone.timedelta(days=30)
        self.e.save()

        self.assertNotContains(self.client.get(reverse("my:hours-edit", args=[self.e.pk, self.user.pk])), "Cannot Edit Report")

        self.e.datetime_end = timezone.now()
        self.e.save()

        self.assertNotContains(self.client.get(reverse("my:hours-edit", args=[self.e.pk, self.user.pk])), "Cannot Edit Report")

        # Check valid post
        valid_data = {"hours": 5.00, "save": "Save Changes"}

        self.assertRedirects(self.client.post(reverse("my:hours-edit", args=[self.e.pk, self.user.pk]), valid_data),
                             reverse("my:hours-list", args=[self.e.pk]))

    def test_hours_bulk(self):
        CCInstanceFactory.create(crew_chief=self.user, event=self.e, setup_start=timezone.now())
        CCInstanceFactory.create(crew_chief=self.user, event=self.e3, setup_start=timezone.now())
        category = Category.objects.create(name="Lighting")
        l1 = Lighting.objects.create(shortname="L3", longname="A bit of lighting", base_cost=1000.00, addtl_cost=1.00,
                                     category=category)
        l2 = ServiceFactory.create(category=category)
        ServiceInstance.objects.create(service=l2, event=self.e3)

        # Check if it is too late
        self.e.lighting = l1
        self.e.datetime_end = timezone.now() - timezone.timedelta(days=30)
        self.e.save()

        self.assertNotContains(self.client.get(reverse("my:hours-bulk", args=[self.e.pk])), "Cannot Edit Report")

        self.e.datetime_end = timezone.now()
        self.e.save()

        self.assertNotContains(self.client.get(reverse("my:hours-bulk", args=[self.e.pk])), "Cannot Edit Report")

        # Check valid post
        event_data = {
            "hours-TOTAL_FORMS": 1,
            "hours-INITIAL_FORMS": 0,
            "hours-MIN_NUM_FORMS": 0,
            "hours-MAX_NUM_FORMS": 1000,
            "hours-0-user": str(self.user.pk),
            "hours-0-hours": 5.00,
            "hours-0-category": "",
            "hours-0-service": str(l1.pk),
            "save": "Save Changes"
        }

        event2019_data = {
            "hours-TOTAL_FORMS": 1,
            "hours-INITIAL_FORMS": 0,
            "hours-MIN_NUM_FORMS": 0,
            "hours-MAX_NUM_FORMS": 1000,
            "hours-0-user": str(self.user.pk),
            "hours-0-hours": 5.00,
            "hours-0-category": str(category.pk),
            "hours-0-service": "",
            "save": "Save Changes"
        }

        self.assertRedirects(self.client.post(reverse("my:hours-bulk", args=[self.e.pk]), event_data),
                             reverse("my:hours-list", args=[self.e.pk]))

        self.assertRedirects(self.client.post(reverse("my:hours-bulk", args=[self.e3.pk]), event2019_data),
                             reverse("my:hours-list", args=[self.e3.pk]))

    def test_posteventsurvey(self):
        self.e.approved = True
        self.e.datetime_end = timezone.now() - timezone.timedelta(days=61)
        new_org = OrgFactory.create()
        self.e.org.add(new_org)
        self.e.save()

        # Check that we get message on expired link
        self.assertContains(self.client.get(reverse("my:post-event-survey", args=[self.e.pk])), "expired")

        self.e.datetime_end = timezone.now() - timezone.timedelta(hours=1)
        self.e.save()

        self.assertOk(self.client.get(reverse("my:post-event-survey", args=[self.e.pk])))

        # Check valid survey submission
        valid_data = {
            "services_quality": 0,
            "lighting_quality": 1,
            "sound_quality": 2,
            "work_order_method": 3,
            "work_order_experience": 4,
            "work_order_ease": 3,
            "work_order_comments": "",
            "communication_responsiveness": 2,
            "pricelist_ux": 1,
            "setup_on_time": 0,
            "crew_respectfulness": -1,
            "price_appropriate": 0,
            "customer_would_return": 1,
            "comments": "",
            "save": "Submit"
        }

        self.assertRedirects(self.client.post(reverse("my:post-event-survey", args=[self.e.pk]), valid_data),
                             reverse("my:survey-success"))

        self.assertContains(self.client.get(reverse("my:post-event-survey", args=[self.e.pk])),
                            "You have already taken this survey")

    def test_attach(self):
        # I can get to the attachments page of an event I submitted
        self.e.submitted_by = self.user
        self.e.closed = True
        self.e.save()

        # Will need view_event permission for redirect
        permission = Permission.objects.get(codename="view_events")
        self.user.user_permissions.add(permission)

        # If closed, redirect to detail page
        self.assertRedirects(self.client.get(reverse("my:event-attach", args=[self.e.pk])),
                             reverse("events:detail", args=[self.e.pk]))

        self.e.closed = False
        self.e.save()

        self.assertOk(self.client.get(reverse("my:event-attach", args=[self.e.pk])))

        lighting = Category.objects.create(name="Lighting")
        l1 = Lighting.objects.create(category=lighting, shortname="LY", longname="Big Lighting",
                                     base_cost=1.00, addtl_cost=1.00)
        self.e.lighting = l1
        self.e.save()
        CCInstanceFactory(crew_chief=self.user, event=self.e, service=l1)

        valid_data = {
            "attachments-TOTAL_FORMS": 1,
            "attachments-INITIAL_FORMS": 0,
            "attachments-MIN_NUM_FORMS": 0,
            "attachments-MAX_NUM_FORMS": 1000,
            "attachments-0-for_service": str(l1.pk),
            "attachments-0-attachment": SimpleUploadedFile('test.txt', b"some content"),
            "attachments-0-note": "",
            "save": "Save Changes"
        }

        # Check that we can add attachment ok
        self.assertRedirects(self.client.post(reverse("my:event-attach", args=[self.e.pk]), valid_data),
                             reverse("my:workorders"))

    def test_orgs(self):
        # I see both orgs that I own and orgs I am a member of in My Orgs
        response = self.client.get(reverse("my:orgs"))
        self.assertContains(response, self.org.name)
        self.assertContains(response, self.org2.name)

    def test_org_req_blank(self):
        # check that the request form shows a valid page
        self.assertOk(self.client.get(reverse("my:org-request")))

    def test_org_req_filled(self):
        # check that the request data can be submitted properly
        data = {
            "client_name": "LNL",
            "email": "lnl@wpi.edu",
            "address": "Campus Center 339",
            "phone": "5088675309",
            "save": "Submit Request"
        }

        self.assertContains(self.client.post(reverse("my:org-request"), data), "Request Received")

        # Check that nothing happens on invalid data
        data['client_name'] = ''
        self.assertOk(self.client.post(reverse("my:org-request"), data))

    def test_accept_orgtransfer(self):
        user2 = UserFactory.create(password="123")
        transfer = OrganizationTransfer.objects.create(initiator=self.user, uuid="6ab57f4a278e470b92e428b6a2594269",
                                                       new_user_in_charge=self.user, old_user_in_charge=user2,
                                                       org=self.org)
        transfer.expiry = timezone.now() - timezone.timedelta(days=1)
        transfer.save()

        # If transfer has expired, display message
        self.assertContains(self.client.get(reverse("my:org-accept", args=[transfer.uuid])), "expired")

        transfer.expiry = timezone.now() + timezone.timedelta(days=1)
        transfer.save()

        # If initiator is the one who attempted to complete the transfer, make sure there is a hold in place
        self.org.user_in_charge = user2
        self.org.save()
        self.assertContains(self.client.get(reverse("my:org-accept", args=[transfer.uuid])), "hold")

        transfer.initiator = user2
        transfer.save()

        self.assertContains(self.client.get(reverse("my:org-accept", args=[transfer.uuid])), "Success")

        # Now check that we get message when already completed
        self.assertContains(self.client.get(reverse("my:org-accept", args=[transfer.uuid])), "Already Completed")

    def test_orgedit(self):
        self.org.user_in_charge = self.user

        self.assertOk(self.client.get(reverse("my:org-edit", args=[self.org.pk])))

        invalid_data = {
            "exec_email": "lnl@wpi.edu",
            "address": "142 West Street",
            "phone": "(123) 456 7890",
            "associated_users": [str(self.user.pk)],
            "workday_fund": 810,
            "worktag": "test",
            "save": "Save Changes"
        }

        # Test invalid worktag
        self.assertOk(self.client.post(reverse("my:org-edit", args=[self.org.pk]), invalid_data))

        valid_data = {
            "exec_email": "lnl@wpi.edu",
            "address": "142 West Street",
            "phone": "(123) 456 7890",
            "associated_users": [str(self.user.pk)],
            "workday_fund": 810,
            "worktag": "1234-AB",
            "save": "Save Changes"
        }

        self.assertRedirects(self.client.post(reverse("my:org-edit", args=[self.org.pk]), valid_data),
                             reverse("orgs:detail", args=[self.org.pk]))

    def test_cc_report_blank(self):
        mommy.make(EventCCInstance, event=self.e, crew_chief=self.user)
        self.assertOk(self.client.get(reverse("my:report", args=[self.e.pk])))

    def test_cc_report_error_post(self):
        mommy.make(EventCCInstance, event=self.e, crew_chief=self.user)
        self.assertOk(self.client.post(reverse("my:report", args=[self.e.pk]),))
        self.assertEqual(list(self.e.ccreport_set.filter(crew_chief=self.user)), [])

    def test_cc_report_post(self):
        mommy.make(EventCCInstance, event=self.e, crew_chief=self.user)
        self.assertRedirects(self.client.post(
            reverse("my:report", args=[self.e.pk]),
            data={
                'report': "lorem ipsum something or another",
                'crew_chief': self.user.pk
            }
        ), reverse("my:events"))
        self.assertIsNotNone(self.e.ccreport_set.get(crew_chief=self.user))

    def test_office_hours(self):
        location = LocationFactory.create(name="Test Location", setup_only=True)
        hour = OfficeHour.objects.create(officer=self.user, day=2, location=location, hour_start=timezone.now().time(),
                                         hour_end=timezone.now().time())
        hour.save()
        res = self.client.get(reverse("my:office-hours"))
        self.assertOk(res)

        formset = res.context['formset']
        self.assertIsNotNone(formset.queryset)
        self.assertTrue(formset.queryset.filter(officer=self.user).exists())

        # Test POST
        valid_data = {
            "form-TOTAL_FORMS": 1,
            "form-INITIAL_FORMS": 0,
            "form-MIN_NUM_FORMS": 0,
            "form-MAX_NUM_FORMS": 1000,
            "form-0-day": 1,
            "form-0-location": location.pk,
            "form-0-hour_start": "08:00 AM",
            "form-0-hour_end": "09:00 AM",
            "form-0-DELETE": False,
            "save": "Save Changes"
        }

        self.assertRedirects(self.client.post(reverse("my:office-hours"), valid_data),
                             reverse("accounts:detail", args=[self.user.pk]))

    def test_get_day(self):
        location = LocationFactory.create(setup_only=True)
        hour = OfficeHour.objects.create(officer=self.user, day=3, location=location, hour_start=timezone.now().time(),
                                         hour_end=timezone.now().time())
        hour.save()
        self.assertEqual(hour.get_day, "Wednesday")
