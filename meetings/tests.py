from django.test import TestCase
from django.core.urlresolvers import reverse
from data.tests.util import ViewTestCase
from django.core.exceptions import PermissionDenied
from django.utils import timezone
from . import models
from meetings.models import get_default_email, mtg_attachment_file_name
from events import models as eventmodels
from events.tests.generators import UserFactory
from django.urls.base import reverse
import logging

logging.disable(logging.WARNING)

class MeetingsModelTest(TestCase):
    def setUp(self):
        self.date = timezone.now()
        self.meeting_type1 = models.MeetingType(name='test')
        self.meeting_type1.save()
        self.meeting = models.Meeting(datetime=self.date, meeting_type=self.meeting_type1)
        self.meeting.save()

    def test_name(self):
        self.assertEqual(self.meeting.name, "test Meeting on %s" % self.date.date())

    def test_endtime(self):
        endTime = self.date
        endTime += timezone.timedelta(hours=1)
        self.assertEqual(endTime, self.meeting.endtime)

    def test_cal_name(self):
        self.assertEqual("Meeting - %s" % self.meeting_type1.name, self.meeting.cal_name())

    def test_cal_desc(self):
        self.assertEqual("", self.meeting.cal_desc())

    def test_cal_location(self):
        self.assertEqual("", self.meeting.cal_location())
        testBuilding = eventmodels.Building(name="Some Building", shortname="SB")
        testLoca = eventmodels.Location(name="Test Location", building=testBuilding)
        self.meeting.location = testLoca
        self.assertEqual(testLoca.name, self.meeting.cal_location())

    def test_cal_start(self):
        self.assertEqual(self.date, self.meeting.cal_start())

    def test_cal_end(self):
        endTime = self.date
        endTime += timezone.timedelta(hours=1)
        self.assertEqual(endTime, self.meeting.cal_end())

    def test_cal_link(self):
        path = reverse('meetings:detail', args=[self.meeting.pk])
        self.assertEqual(path, self.meeting.cal_link())

    def test_cal_guid(self):
        guid = "mtg" + str(self.meeting.id) + "@lnldb"
        self.assertEqual(guid, self.meeting.cal_guid())

    def test_get_default_email(self):
        #Just returns the primary key of the default email which seems to always be 1...
        self.assertEqual(1, get_default_email())

    def test_mtg_attachment_file_name(self):
        file = "someFileName.png"
        URL = '/'.join(['meeting_uploads', str(self.meeting.pk), file])
        self.assertEqual(URL, mtg_attachment_file_name(self, file))
        print(models.TargetEmailList("Name", "lnl@wpi.edu"))

class MeetingsViewTest(ViewTestCase):
    def setUp(self):
        self.date = timezone.now()
        self.user = UserFactory.create(password="123")
        self.meeting_type1 = models.MeetingType(name='test')
        self.meeting_type1.save()
        self.meeting = models.Meeting(datetime=self.date, meeting_type=self.meeting_type1)
        file = models.mtg_attachment_file_name(self,"TotallyAFile.png")
        self.attachment = models.MtgAttachment(name="Attachment1", file=file, author=self.user, meeting=self.meeting)
        self.meeting.save()
        super(MeetingsViewTest, self).setUp()

    def test_download_att(self):
        # meeting = Meeting.objects.create()
        self.assertOk(self.client.get(reverse("meetings:att-dl", args=[self.meeting.id, 1])), 403)

    def test_viewattendace(self):
        self.assertOk(self.client.get(reverse("meetings:detail", args=[self.meeting.id])), 403)

        #set permissions

        #make sure okay