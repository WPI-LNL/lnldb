import logging
from random import randint
from data.tests.util import ViewTestCase
from django.urls.base import reverse
from django.contrib.auth.models import Group
from django.contrib.sites.shortcuts import get_current_site

from . import models, forms
from accounts.models import PhoneVerificationCode


logging.disable(logging.WARNING)


class PagesTestCase(ViewTestCase):
    def test_page(self):
        self.assertOk(self.client.get(reverse("page", args=['test'])), 404)

        page = models.Page.objects.create(title="Test", slug="test", body="This is the page content!")
        page.save()

        self.assertOk(self.client.get(reverse("page", args=['test'])))

    #def test_recruitment_page(self):
    #    self.assertOk(self.client.get(reverse("pages:recruitment-page")))


class OnboardingTestCase(ViewTestCase):
    def setUp(self):
        super(OnboardingTestCase, self).setUp()
        self.user.onboarded = False
        self.user.save()
        self.screen = models.OnboardingScreen.objects.create(title='Test Screen', slug='test',
                                                             content="Hello there. Here's a test message for you.")
        self.group = Group.objects.create(name="Test Group")
        self.group.user_set.add(self.user)

    def test_new_member_welcome(self):
        # Users not associated with LNL should not be onboarded
        self.assertOk(self.client.get(reverse("home")))

        # Associate user
        group = Group.objects.create(name="Associate")
        group.user_set.add(self.user)

        # If user has not yet been onboarded, redirect to the onboarding system
        self.assertRedirects(self.client.get(reverse("home")), reverse('pages:new-member'))

        # Repeating this should now redirect to the actual home page (this should only be displayed once upon login)
        self.assertOk(self.client.get(reverse("home")))

    def test_screen(self):
        self.assertOk(self.client.get(reverse("pages:onboarding-screen", args=['test2'])), 404)

        # Check that the page is only visible for users the page has been assigned to
        self.assertOk(self.client.get(reverse("pages:onboarding-screen", args=['test'])), 403)

        self.screen.users.add(self.user)

        # Check that the page displays properly
        self.assertOk(self.client.get(reverse("pages:onboarding-screen", args=['test'])))

        # Check that pages can be assigned by group
        self.screen.users.remove(self.user)

        self.assertOk(self.client.get(reverse("pages:onboarding-screen", args=['test'])), 403)

        self.screen.groups.add(self.group)

        self.assertOk(self.client.get(reverse("pages:onboarding-screen", args=['test'])))

    def test_redirect_on_login(self):
        # Create two onboarding pages and check that it redirects to both before redirecting back to the home page
        second_screen = models.OnboardingScreen.objects.create(title='Another Test', slug='test2',
                                                               content='Not much to see here')

        self.screen.users.add(self.user)
        second_screen.users.add(self.user)

        # Also check to ensure we record when users have seen a page
        self.assertFalse(models.OnboardingRecord.objects.filter(user=self.user).exists())
        self.assertRedirects(self.client.get(reverse("home")), reverse("pages:onboarding-screen", args=['test']))
        self.assertTrue(models.OnboardingRecord.objects.filter(user=self.user).exists())

        # Use referer to verify that the user actually saw the page
        domain = get_current_site(None)
        self.assertRedirects(self.client.get(reverse("home"), HTTP_REFERER='http://%s/onboarding/test/' % domain),
                             reverse("pages:onboarding-screen", args=['test2']))
        self.assertOk(self.client.get(reverse('home'), HTTP_REFERER='http://%s/onboarding/test2/' % domain))

    def test_onboarding_forms(self):
        # Check that forms in wizard handle data properly
        self.assertOk(self.client.get(reverse("pages:onboarding-wizard")))

        valid_user_info = {
            'first_name': 'Peter',
            'last_name': 'Peters',
            'nickname': 'Peterboy',
            'email': 'example@wpi.edu',
            'class_year': '2020',
            'student_id': '',
            'wpibox': ''
        }

        contact_info = {
            'address': '123 Main St',
            'line_2': 'Apt. 4B',
            'city': 'Worcester',
            'state': 'Massachusetts',
            'phone': '1234567890',
            'sms': 'True',
            'carrier': ''
        }

        verification_code = randint(100000, 999999)
        PhoneVerificationCode.objects.create(user=self.user, code=verification_code)
        phone_verification = {
            'code': verification_code
        }
        invalid_verification = {
            'code': verification_code - 1
        }

        contact_form = forms.OnboardingContactInfoForm(data=contact_info, has_address=False)
        self.assertFalse(contact_form.is_valid())

        contact_info['carrier'] = 'txt.att.net'

        user_info = forms.OnboardingUserInfoForm(data=valid_user_info)
        contact_form = forms.OnboardingContactInfoForm(data=contact_info, has_address=False)
        self.assertTrue(user_info.is_valid())
        self.assertTrue(contact_form.is_valid())

        verification = forms.SMSVerificationForm(data=phone_verification, user=self.user)
        self.assertTrue(verification.is_valid())

        # Check invalid code
        failed_verification = forms.SMSVerificationForm(data=invalid_verification, user=self.user)
        self.assertFalse(failed_verification.is_valid())

        # The code's record should be deleted from the database after use
        verification.save()
        self.assertFalse(PhoneVerificationCode.objects.filter(code=verification_code).exists())

    def test_onboarding_flow(self):
        step1 = {
            'onboarding_wizard-current_step': ['0'],
            '0-first_name': ['Sally'],
            '0-last_name': ['Supervisor'],
            '0-nickname': ['Chief'],
            '0-email': ['lnl-w@wpi.edu'],
            '0-class_year': ['2022'],
            '0-student_id': [''],
            '0-wpibox': ['']
        }

        step2 = {
            'onboarding_wizard-current_step': ['1'],
            '1-address': ['123 Main St'],
            '1-line_2': ['Apt 1'],
            '1-city': ['Worcester'],
            '1-state': ['MA'],
            '1-phone': ['1234567890'],
            '1-sms': ['False'],
            '1-carrier': ['txt.att.net']
        }

        resp = self.client.post(reverse("pages:onboarding-wizard"), step1)
        self.assertOk(resp)
        self.assertContains(resp, "Contact Information")

        self.assertRedirects(self.client.post(reverse("pages:onboarding-wizard"), step2), reverse("home"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.nickname, 'Chief')
        self.assertEqual(self.user.phone, '1234567890')
        self.assertEqual(self.user.carrier, '')  # User did not want to opt in so this field should be blank

        # Test with existing address and SMS opt-in set to true
        self.user.address = "123 Main St"
        self.user.save()

        resp = self.client.post(reverse("pages:onboarding-wizard"), step1)
        self.assertContains(resp, "Already Complete")

        step2_with_sms = {
            'onboarding_wizard-current_step': ['1'],
            '1-address': [''],
            '1-line_2': [''],
            '1-city': [''],
            '1-state': [''],
            '1-phone': ['1234567890'],
            '1-sms': ['True'],
            '1-carrier': ['txt.att.net']
        }

        resp = self.client.post(reverse("pages:onboarding-wizard"), step2_with_sms)
        self.assertOk(resp)
        self.assertContains(resp, "SMS Verification")

        # User should still be opted out until after completing the verification
        self.user.refresh_from_db()
        self.assertEqual(self.user.carrier, '')

        # Verify that the verification process can be completed successfully
        verification_code = randint(100000, 999999)
        code = PhoneVerificationCode.objects.get(user=self.user)
        code.code = verification_code
        code.save()
        step3 = {
            'onboarding_wizard-current_step': ['2'],
            '2-code': [str(verification_code)]
        }

        self.assertRedirects(self.client.post(reverse("pages:onboarding-wizard"), step3), reverse("home"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.carrier, 'txt.att.net')
