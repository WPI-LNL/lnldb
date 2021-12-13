from django.test import TestCase
from django.utils import timezone
import datetime

from data.tests.util import ViewTestCase
from django.contrib.auth.models import Permission
from django.urls.base import reverse


from .models import Position

# Create your tests here.

class PositionModelTests(TestCase):

    def setUp(self):
        self.position = Position(name="Test", description="Test",
                position_start=timezone.now() + timezone.timedelta(days=-2),
                position_end=timezone.now(),
                closes=timezone.now(), application_form="https://example.com")

    def test_closed(self):
        today = timezone.now()
        yesterday = today + timezone.timedelta(days=-1)
        tomorrow = today + timezone.timedelta(days=1)

        self.position.closes = today
        self.position.save()
        self.assertFalse(self.position.is_open())

        self.position.closes = yesterday
        self.position.save()
        self.assertFalse(self.position.is_open())

        self.position.closes = tomorrow
        self.position.save()
        self.assertTrue(self.position.is_open())

class PositionViewTests(ViewTestCase):
    def setUp(self):
        super(PositionViewTests, self).setUp()

        self.position = Position.objects.create(name="Test", description="Test",
                position_start=timezone.now() + timezone.timedelta(days=-2),
                position_end=timezone.now() + timezone.timedelta(days=10),
                closes = timezone.now() + timezone.timedelta(days=1),
                application_form="https://example.com")

    def test_listposition(self):
        # Should not be able to view positions by default
        self.assertOk(self.client.get(reverse("positions:list")), 403)

        perm = Permission.objects.get(codename="apply")
        self.user.user_permissions.add(perm)

        self.assertOk(self.client.get(reverse("positions:list")))

    def test_createposition(self):
        self.assertOk(self.client.get(reverse("positions:create")), 403)

        perm = Permission.objects.get(codename="add_position")
        self.user.user_permissions.add(perm)

        self.assertOk(self.client.get(reverse("positions:create")))

    def test_viewposition(self):
        self.assertOk(self.client.get(reverse("positions:detail",
            args=[self.position.pk])), 403)

        perm = Permission.objects.get(codename="apply")
        self.user.user_permissions.add(perm)

        self.assertOk(self.client.get(reverse("positions:detail",
            args=[self.position.pk])))

    def test_updateposition(self):
        self.assertOk(self.client.get(reverse("positions:update",
        args=[self.position.pk])), 403)

        perm = Permission.objects.get(codename="change_position")
        self.user.user_permissions.add(perm)

        self.assertOk(self.client.get(reverse("positions:update",
            args=[self.position.pk])))
