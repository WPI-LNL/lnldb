from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings


@override_settings(TEMPLATE_STRING_IF_INVALID='TEMPLATE_WARNING [%s]')
class ViewTestCase(TestCase):
    def setUp(self):
        # I have the same password on my luggage!!!
        self.credentials = {'username': 'testuser',
                            'password': '12345'}
        extra = {'email': 'abc@foo.com',
                 'is_staff': True,
                 'is_superuser': False}
        extra.update(self.credentials)
        self.user = get_user_model().objects._create_user(**extra)
        self.user.save()

        self.assertTrue(self.client.login(username='testuser', password='12345'))

    def assertOk(self, response, status_code=200):
        return self.assertNotContains(response, "TEMPLATE_WARNING", status_code)
