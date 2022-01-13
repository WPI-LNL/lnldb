import logging
from django.urls import reverse
from django.contrib.auth.models import Permission
from data.tests.util import ViewTestCase
logging.disable(logging.WARNING)


class SnipeTests(ViewTestCase):
    def test_snipe_credentials_view(self):
        # Check that only users with view equipment permissions can access the page
        self.assertOk(self.client.get(reverse("inventory:snipe_password")), 403)

        permission = Permission.objects.get(codename="view_equipment")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("inventory:snipe_password")))
