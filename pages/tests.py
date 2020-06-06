from data.tests.util import ViewTestCase
from django.core.urlresolvers import reverse

from . import models


class PagesTestCase(ViewTestCase):
    def test_page(self):
        self.assertOk(self.client.get(reverse("page", args=['test'])), 404)

        page = models.Page.objects.create(title="Test", slug="test", body="This is the page content!")
        page.save()

        self.assertOk(self.client.get(reverse("page", args=['test'])))

    def test_recruitment_page(self):
        self.assertOk(self.client.get(reverse("recruitment-page")))
