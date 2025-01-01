import logging
import json
from django.shortcuts import reverse
from django.utils import timezone
from .util import ViewTestCase
from events.tests.generators import UserFactory, LocationFactory, OrgFactory, ServiceFactory, CategoryFactory, \
    Event2019Factory
from events.models import Extra, ServiceInstance


logging.disable(logging.WARNING)


class DataViewsTestCase(ViewTestCase):
    def test_maintenance(self):
        self.assertOk(self.client.get(reverse("maintenance")))

    def test_search(self):
        self.assertOk(self.client.get(reverse("search")))

        UserFactory.create(password="123", first_name="Ellen")

        self.assertContains(self.client.get(reverse("search"), {'q': 'ell'}), "Ellen")
