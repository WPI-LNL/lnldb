from unittest import skipIf
import requests
from data.tests.util import ViewTestCase
from django.shortcuts import reverse
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from cryptography.fernet import Fernet

from accounts.models import UserPreferences


class RTAPITests(ViewTestCase):
    @skipIf(requests.head('https://lnl-rt.wpi.edu/rt/REST/2.0/ticket').status_code != 200, "RT is not reachable")
    def test_ticket_form(self):
        # Check that form loads ok
        self.assertOk(self.client.get(reverse("support:new-ticket")))

        # Test response with invalid data
        invalid_data = {
            "subject": "Website broken",
            "description": "",
            "attachments": [],
            "save": "Submit"
        }
        self.assertOk(self.client.post(reverse("support:new-ticket"), invalid_data))

        # Check response with valid data
        attachment = SimpleUploadedFile('test.txt', b'Contents of a file')
        valid_data = {
            "subject": "Website broken",
            "description": "I tried using this website to file my taxes but it isn't working for some reason",
            "attachments": [attachment],
            "save": "Submit"
        }

        # We do not want to submit new tickets if testing is triggered in prod
        if settings.RT_TOKEN in ['', None]:
            self.assertRedirects(self.client.post(reverse("support:new-ticket"), valid_data), reverse("home"))

    def test_account_setup(self):
        # Check that form loads ok if coming from scopes page
        self.assertRedirects(self.client.get(reverse("support:link-account")), reverse("accounts:scope-request"))

        self.assertOk(self.client.get(reverse("support:link-account"),
                                      HTTP_REFERER="https://lnl.wpi.edu" + reverse("accounts:scope-request")))

        # Test valid entry
        data = {
            "token": "1-234-567890abcdef1a2b3c4d5e6f7f8e9d0c",
            "save": "Submit"
        }

        self.assertRedirects(self.client.post(reverse("support:link-account"), data, follow=True),
                             reverse("accounts:detail", args=[self.user.pk]))

        # Check that user preferences exist
        self.assertTrue(UserPreferences.objects.filter(user=self.user).exists())

        # If the cryptographic key is available, check that the token was saved properly
        if settings.CRYPTO_KEY:
            prefs = UserPreferences.objects.get(user=self.user)
            cipher_suite = Fernet(settings.CRYPTO_KEY)
            self.assertEqual(data["token"], cipher_suite.decrypt(prefs.rt_token.encode('utf-8')).decode('utf-8'))
