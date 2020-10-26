from django.test import TestCase
from data.tests.util import ViewTestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth.models import Permission
from django.utils import timezone
from . import models
from meetings.models import get_default_email, mtg_attachment_file_name
from events import models as eventmodels
from events.tests.generators import EventFactory, LocationFactory
from django.urls.base import reverse
import logging

logging.disable(logging.WARNING)


class MeetingsModelTest(TestCase):
    def setUp(self):
        self.meeting_type1 = models.MeetingType.objects.create(name='Exec')
        self.meeting = models.Meeting.objects.create(datetime=timezone.now(), meeting_type=self.meeting_type1)

    def test_name(self):
        self.assertEqual(self.meeting.name, "Exec Meeting on %s" % timezone.now().date())

    def test_endtime(self):
        end_time = timezone.now()
        end_time += timezone.timedelta(hours=1)
        self.assertEqual(end_time, self.meeting.endtime)

    def test_cal_name(self):
        self.assertEqual("Meeting - %s" % self.meeting_type1.name, self.meeting.cal_name())

    def test_cal_desc(self):
        self.assertEqual("", self.meeting.cal_desc())

    def test_cal_location(self):
        self.assertEqual("", self.meeting.cal_location())
        test_building = eventmodels.Building(name="Some Building", shortname="SB")
        test_location = eventmodels.Location(name="Test Location", building=test_building)
        self.meeting.location = test_location
        self.assertEqual(test_location.name, self.meeting.cal_location())

    def test_cal_start(self):
        self.assertEqual(timezone.now(), self.meeting.cal_start())

    def test_cal_end(self):
        end_time = timezone.now()
        end_time += timezone.timedelta(hours=1)
        self.assertEqual(end_time, self.meeting.cal_end())

    def test_cal_link(self):
        path = reverse('meetings:detail', args=[self.meeting.pk])
        self.assertEqual(path, self.meeting.cal_link())

    def test_cal_guid(self):
        guid = "mtg" + str(self.meeting.id) + "@lnldb"
        self.assertEqual(guid, self.meeting.cal_guid())

    def test_get_default_email(self):
        # Just returns the primary key of the default email which seems to always be 1...
        self.assertEqual(1, get_default_email())

    def test_mtg_attachment_file_name(self):
        f = "someFileName.png"
        url = '/'.join(['meeting_uploads', str(self.meeting.pk), f])
        self.assertEqual(url, mtg_attachment_file_name(self, f))


class MeetingsViewTest(ViewTestCase):
    def setUp(self):
        super(MeetingsViewTest, self).setUp()
        self.meeting_type1 = models.MeetingType.objects.create(name='Exec')
        self.meeting = models.Meeting.objects.create(datetime=timezone.now(), meeting_type=self.meeting_type1)
        self.meeting2 = models.Meeting.objects.create(datetime=timezone.now(), meeting_type=self.meeting_type1)
        path = models.mtg_attachment_file_name(self, "TotallyAFile.png")
        f = SimpleUploadedFile(path, b"some content")
        self.attachment = models.MtgAttachment.objects.create(name="Attachment1", file=f, author=self.user,
                                                              meeting=self.meeting)

    def test_download_att(self):
        # By default, should not have permission to download attachments
        self.assertOk(self.client.get(reverse("meetings:att-dl", args=[self.meeting.pk, self.attachment.pk])), 403)

        permission = Permission.objects.get(codename="view_mtg")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("meetings:att-dl", args=[self.meeting.pk, self.attachment.pk])))

        # If attachment event id does not match event id, throw permission denied
        self.assertOk(self.client.get(reverse("meetings:att-dl", args=[self.meeting2.pk, self.attachment.pk])), 403)

        self.attachment.private = True
        self.attachment.save()

        # If file is protected, ensure user has permission
        self.assertOk(self.client.get(reverse("meetings:att-dl", args=[self.meeting.pk, self.attachment.pk])), 403)

        permission = Permission.objects.get(codename="view_mtg_closed")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("meetings:att-dl", args=[self.meeting.pk, self.attachment.pk])))

    def test_rm_att(self):
        # By default, should not have permission to delete attachments
        self.assertOk(self.client.get(reverse("meetings:att-rm", args=[self.meeting.pk, self.attachment.pk])), 403)

        permission = Permission.objects.get(codename="edit_mtg")
        self.user.user_permissions.add(permission)

        # Will also need view_mtg permissions for redirect
        permission = Permission.objects.get(codename="view_mtg_attendance")
        self.user.user_permissions.add(permission)

        self.assertRedirects(self.client.get(reverse("meetings:att-rm", args=[self.meeting.pk, self.attachment.pk])),
                             reverse("meetings:detail", args=[self.meeting.pk]))

        # Check that if attachment event id does not match event id we throw permission denied
        self.assertOk(self.client.get(reverse("meetings:att-rm", args=[self.meeting2.pk, self.attachment.pk])), 403)

    def test_modify_att(self):
        # By default, should not have permission to modify attachments
        self.assertOk(self.client.get(reverse("meetings:att-edit", args=[self.meeting.pk, self.attachment.pk])), 403)

        permission = Permission.objects.get(codename="edit_mtg")
        self.user.user_permissions.add(permission)

        # Will also need view_mtg permissions for redirect
        permission = Permission.objects.get(codename="view_mtg_attendance")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("meetings:att-edit", args=[self.meeting.pk, self.attachment.pk])))

        # If attachment event id does not match event id throw permission denied
        self.assertOk(self.client.get(reverse("meetings:att-edit", args=[self.meeting2.pk, self.attachment.pk])), 403)

        path = models.mtg_attachment_file_name(self, "TotallyAFile.png")
        f = SimpleUploadedFile(path, b"some content")
        valid_data = {
            "name": "Test File",
            "file": f,
            "private": True,
            "submit": "Submit"
        }

        self.assertRedirects(
            self.client.post(reverse("meetings:att-edit", args=[self.meeting.pk, self.attachment.pk]), valid_data),
            reverse("meetings:detail", args=[self.meeting.pk]) + "#minutes"
        )

    def test_viewattendace(self):
        # By default, should not have permission to view attendance
        self.assertOk(self.client.get(reverse("meetings:detail", args=[self.meeting.pk])), 403)

        permission = Permission.objects.get(codename="view_mtg_attendance")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("meetings:detail", args=[self.meeting.pk])))

    def test_update_event(self):
        e = EventFactory.create(event_name="Test Event")
        lighting = eventmodels.Category.objects.create(name="Lighting")
        l1 = eventmodels.Lighting.objects.create(shortname="L1", longname="Lighting", base_cost=100.00,
                                                 addtl_cost=10.00, category=lighting)
        office = LocationFactory(name="Office", setup_only=True)
        e.lighting = l1
        e.save()

        # By default, should not have permission to update the event
        self.assertOk(self.client.get(reverse("meetings:addchief", args=[self.meeting.pk, e.pk])), 403)

        permission = Permission.objects.get(codename="edit_mtg")
        self.user.user_permissions.add(permission)

        # Will also need view_mtg permissions for redirect
        permission = Permission.objects.get(codename="view_mtg_attendance")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("meetings:addchief", args=[self.meeting.pk, e.pk])))

        valid_data = {
            "main-TOTAL_FORMS": 1,
            "main-INITIAL_FORMS": 0,
            "main-MIN_NUM_FORMS": 0,
            "main-MAX_NUM_FORMS": 1000,
            "main-0-crew_chief": str(self.user.pk),
            "main-0-service": str(l1.pk),
            "main-0-category": "",
            "main-0-setup_location": str(office.pk),
            "main-0-setup_start_0": timezone.now().date(),
            "main-0-setup_start_1": timezone.now().time()
        }

        self.assertRedirects(self.client.post(reverse("meetings:addchief", args=[self.meeting.pk, e.pk]), valid_data),
                             reverse("meetings:detail", args=[self.meeting.pk]) + "#events")

    def test_edit_attendance(self):
        office = LocationFactory(name="Office", setup_only=False, available_for_meetings=True)

        # By default, should not have permission to edit attendance
        self.assertOk(self.client.get(reverse("meetings:edit", args=[self.meeting.pk])), 403)

        permission = Permission.objects.get(codename="edit_mtg")
        self.user.user_permissions.add(permission)

        # Will need view_mtg permission on redirect as well
        permission = Permission.objects.get(codename="view_mtg_attendance")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("meetings:edit", args=[self.meeting.pk])))

        path = models.mtg_attachment_file_name(self, "TotallyAFile.png")
        f = SimpleUploadedFile(path, b"some content")
        valid_data = {
            "meeting_type": str(self.meeting_type1.pk),
            "location": str(office.pk),
            "datetime_0": timezone.now().date(),
            "datetime_1": timezone.now().time(),
            "attendance": [str(self.user.pk)],
            "duration": "1 hour",
            "agenda": "",
            "minutes": "",
            "minutes_private": "",
            "attachments": f,
            "attachments_private": "",
            "save": "Save Changes"
        }

        self.assertRedirects(self.client.post(reverse("meetings:edit", args=[self.meeting.pk]), valid_data),
                             reverse("meetings:detail", args=[self.meeting.pk]) + "#attendance")

    def test_list_attendance(self):
        # User should not have permission by default
        self.assertOk(self.client.get(reverse("meetings:list")), 403)

        permission = Permission.objects.get(codename="list_mtgs")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("meetings:list")))

    def test_new_attendance(self):
        office = LocationFactory(name="Office", setup_only=False, available_for_meetings=True)

        # User should not have permission to create meetings by default
        self.assertOk(self.client.get(reverse("meetings:new")), 403)

        permission = Permission.objects.get(codename="create_mtg")
        self.user.user_permissions.add(permission)

        # Will need view_mtg permission on redirect as well
        permission = Permission.objects.get(codename="view_mtg_attendance")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("meetings:new")))

        valid_data = {
            "meeting_type": str(self.meeting_type1.pk),
            "location": str(office.pk),
            "datetime_0": timezone.now().date(),
            "datetime_1": timezone.now().time(),
            "attendance": [str(self.user.pk)],
            "duration": "1 hour",
            "agenda": "",
            "minutes": "",
            "minutes_private": "",
            "attachments": "",
            "attachments_private": "",
            "save": "Save Changes"
        }

        self.assertRedirects(self.client.post(reverse("meetings:new"), valid_data),
                             reverse("meetings:detail", args=[3]))

    def test_mknotice(self):
        recipient = models.TargetEmailList.objects.create(name="Test", email="test@wpi.edu")

        # By default user should not have permission to send notice
        self.assertOk(self.client.get(reverse("meetings:email", args=[self.meeting.pk])), 403)

        permission = Permission.objects.get(codename="send_mtg_notice")
        self.user.user_permissions.add(permission)

        # Will also need view_mtg permission for redirect
        permission = Permission.objects.get(codename="view_mtg_attendance")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("meetings:email", args=[self.meeting.pk])))

        valid_data = {
            "events": [],
            "subject": "Meeting Today",
            "message": "Hello people. Come to meeting please.",
            "email_to": str(recipient.pk),
            "save": "Save Changes"
        }

        self.assertRedirects(self.client.post(reverse("meetings:email", args=[self.meeting.pk]), valid_data),
                             reverse("meetings:detail", args=[self.meeting.pk]) + "#emails")

    def test_mkcc_notice(self):
        recipient = models.TargetEmailList.objects.create(name="Test", email="test@wpi.edu")

        # By default, user should not have permission to send notice
        self.assertOk(self.client.get(reverse("meetings:cc-email", args=[self.meeting.pk])), 403)

        permission = Permission.objects.get(codename="send_mtg_notice")
        self.user.user_permissions.add(permission)

        # Will also need view_mtg permission on redirect
        permission = Permission.objects.get(codename="view_mtg_attendance")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("meetings:cc-email", args=[self.meeting.pk])))

        valid_data = {
            "events": [],
            "addtl_message": "Hello again. Please come.",
            "email_to": str(recipient.pk),
            "save": "Save Changes"
        }

        self.assertRedirects(self.client.post(reverse("meetings:cc-email", args=[self.meeting.pk]), valid_data),
                             reverse("meetings:detail", args=[self.meeting.pk]) + "#emails")
