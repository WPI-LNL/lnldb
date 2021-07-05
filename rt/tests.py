from data.tests.util import ViewTestCase
from django.shortcuts import reverse
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile


class RTAPITests(ViewTestCase):
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
