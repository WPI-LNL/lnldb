from django.test import TestCase
from django.core.urlresolvers import reverse
from data.tests.util import ViewTestCase
from django.contrib.auth.models import Permission
from django.forms.formsets import formset_factory
from events.tests.generators import UserFactory
from events.models import Organization, Fund, Event2019
from django.utils import timezone
from . import models, forms, views
import datetime
import logging


# Disable annoying permission warnings
logging.disable(logging.WARNING)


class ProjectionistModelTests(TestCase):
    def setUp(self):
        self.user = UserFactory.create(password="123")
        self.projectionist = models.Projectionist(user=self.user)
        self.projectionist.save()

    def test_expired(self):
        today = timezone.datetime.today().date()
        yesterday = today + timezone.timedelta(days=-1)
        tomorrow = today + timezone.timedelta(days=1)

        self.projectionist.license_expiry = today
        self.projectionist.save()
        self.assertTrue(self.projectionist.expired)

        self.projectionist.license_expiry = yesterday
        self.projectionist.save()
        self.assertTrue(self.projectionist.expired)

        self.projectionist.license_expiry = tomorrow
        self.projectionist.save()
        self.assertFalse(self.projectionist.expired)

    def test_expiring(self):
        today = timezone.datetime.today().date()
        day_15 = today + timezone.timedelta(days=15)
        day_30 = today + timezone.timedelta(days=30)
        day_45 = today + timezone.timedelta(days=45)

        self.projectionist.license_expiry = day_15
        self.projectionist.save()
        self.assertTrue(self.projectionist.expiring)

        self.projectionist.license_expiry = day_45
        self.projectionist.save()
        self.assertFalse(self.projectionist.expiring)

        # Assumes 30 day warning
        self.projectionist.license_expiry = day_30
        self.projectionist.save()
        self.assertTrue(self.projectionist.expiring)


class ProjViewTest(ViewTestCase):
    def test_plist(self):
        # make sure normies can't see this
        self.assertOk(self.client.get(reverse("projection:list")), 403)

        permission = Permission.objects.get(codename='view_pits')
        self.user.user_permissions.add(permission)

        # blank
        self.assertOk(self.client.get(reverse("projection:list")))

        proj = models.Projectionist.objects.create(user=self.user)
        proj.save()

        # with people
        self.assertOk(self.client.get(reverse("projection:list")))

    def test_plist_detail(self):
        # make sure normies can't see this
        self.assertOk(self.client.get(reverse("projection:grid")), 403)

        permission = Permission.objects.get(codename='view_pits')
        self.user.user_permissions.add(permission)
        self.assertOk(self.client.get(reverse("projection:grid")))

        # blank
        proj = models.Projectionist.objects.create(user=self.user)
        proj.save()

        # with people
        self.assertOk(self.client.get(reverse("projection:grid")))

    def test_pdf(self):
        # make sure normies can't see this
        self.assertOk(self.client.get(reverse("projection:pdf")), 403)

        permission = Permission.objects.get(codename='view_pits')
        self.user.user_permissions.add(permission)

        # blank
        self.assertOk(self.client.get(reverse("projection:pdf")+"?raw=true"))
        self.assertOk(self.client.get(reverse("projection:pdf")), binary=True)

        proj = models.Projectionist.objects.create(user=self.user)
        proj.save()

        # with people
        self.assertOk(self.client.get(reverse("projection:pdf")+"?raw=true"))
        self.assertOk(self.client.get(reverse("projection:pdf")), binary=True)

    def test_create(self):
        valid_form_data = {
            'user_text': "",
            'user': self.user.pk,
            'license_number': "",
            'license_expiry': "",
            'pitinstances-TOTAL_FORMS': 1,
            'pitinstances-INITIAL_FORMS': 0,
            'pitinstances-MIN_NUM_FORMS': 0,
            'pitinstances-MAX_NUM_FORMS': 1000,
            'pitinstances-0-id': "",
            'pitinstances-0-pit_level': "",
            'pitinstances-0-created_on': "",
            'pitinstances-0-valid': "on",
            'submit': 'Save changes'
        }

        # make sure normies can't see this
        self.assertOk(self.client.get(reverse("projection:new")), 403)

        # give ourselves permissions
        permission = Permission.objects.get(codename='edit_pits')
        self.user.user_permissions.add(permission)

        # we can view the form now!
        self.assertOk(self.client.get(reverse("projection:new")))

        # submitting with invalid data redisplays form
        self.assertOk(self.client.post(reverse("projection:new")))

        # needed for the page we redirect to
        permission = Permission.objects.get(codename='view_pits')
        self.user.user_permissions.add(permission)

        # Get a redirect on valid data
        resp = self.client.post(reverse("projection:new"), valid_form_data)
        self.assertRedirects(resp, reverse("projection:grid"))

        # check it was actually created
        self.assertTrue(models.Projectionist.objects.filter(user=self.user).exists())

    def test_delete(self):
        # make an object for us
        proj = models.Projectionist.objects.create(user=self.user)
        proj.save()

        # make sure normies can't see this
        self.assertOk(self.client.get(reverse("projection:remove", args=[self.user.pk])), 403)

        # give ourselves permissions
        permission = Permission.objects.get(codename='edit_pits')
        self.user.user_permissions.add(permission)

        # we can view the form now!
        self.assertOk(self.client.get(reverse("projection:remove", args=[self.user.pk])))

        # needed for the page we redirect to
        permission = Permission.objects.get(codename='view_pits')
        self.user.user_permissions.add(permission)

        # Get a redirect on valid data
        self.assertRedirects(self.client.post(reverse("projection:remove", args=[self.user.pk])),
                             reverse("projection:grid"))

        # check it was actually deleted
        self.assertFalse(models.Projectionist.objects.filter(user=self.user).exists())

    def test_edit(self):
        # make an object for us
        proj = models.Projectionist.objects.create(user=self.user)
        proj.save()

        valid_form_data = {
            'main-license_number': "12345",
            'main-license_expiry': "",
            'nested-TOTAL_FORMS': 1,
            'nested-INITIAL_FORMS': 0,
            'nested-MIN_NUM_FORMS': 0,
            'nested-MAX_NUM_FORMS': 1000,
            'nested-0-id': "",
            'nested-0-pit_level': "",
            'nested-0-created_on': "",
            'nested-0-valid': "on",
            'submit': 'Save changes'
        }

        invalid_form_data = {
            'main-license_number': "",
            'main-license_expiry': "invalid",
            'nested-TOTAL_FORMS': 1,
            'nested-INITIAL_FORMS': 0,
            'nested-MIN_NUM_FORMS': 0,
            'nested-MAX_NUM_FORMS': 1000,
            'nested-0-id': "",
            'nested-0-pit_level': "",
            'nested-0-created_on': "",
            'nested-0-valid': "on",
            'submit': 'Save changes'
        }

        # make sure normies can't see this
        self.assertOk(self.client.get(reverse("projection:edit", args=[proj.pk])), 403)

        # give ourselves permissions
        permission = Permission.objects.get(codename='edit_pits')
        self.user.user_permissions.add(permission)
        # needed for the page we redirect to
        permission = Permission.objects.get(codename='view_pits')
        self.user.user_permissions.add(permission)

        # we can view the form now!
        self.assertOk(self.client.get(reverse("projection:edit", args=[proj.pk])))

        # Get a redirect on valid data
        resp = self.client.post(reverse("projection:edit", args=[proj.pk]), valid_form_data)
        self.assertRedirects(resp, reverse("projection:grid"))

        # Get the forms back on invalid data
        resp = self.client.post(reverse("projection:edit", args=[proj.pk]), invalid_form_data)
        self.assertOk(resp)

        # check it was actually changed
        self.assertEqual(models.Projectionist.objects.get(user=self.user).license_number, '12345')

    def test_bulk_edit(self):
        # make sure normies can't see this
        self.assertOk(self.client.get(reverse("projection:bulk-edit")), 403)

        permission = Permission.objects.get(codename='edit_pits')
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("projection:bulk-edit")))

        level = models.PITLevel.objects.create(name_short="P1", name_long="PIT1", ordering=1)
        level.save()

        cleaned_data = {
            'users': str(self.user.pk),
            'date': timezone.datetime.today().date(),
            'pit_level': str(level.pk),
            'submit': 'Save Changes'
        }

        # Test form
        form = forms.BulkUpdateForm(data=cleaned_data)
        self.assertTrue(form.is_valid())

        permission = Permission.objects.get(codename="view_pits")
        self.user.user_permissions.add(permission)

        self.assertRedirects(self.client.post(reverse("projection:bulk-edit"), cleaned_data),
                             reverse("projection:grid"))

        # Test that updates are applied correctly
        instances = models.PitInstance.objects.all()
        self.assertTrue(instances.filter(projectionist__user=self.user, pit_level=level).exists())

    def test_bulk_projection(self):
        # make sure normies can't see this
        self.assertOk(self.client.get(reverse("projection:add-movies")), 403)

        permission = Permission.objects.get(codename='add_bulk_events')
        self.user.user_permissions.add(permission)
        self.assertOk(self.client.get(reverse("projection:add-movies")))

        invalid_details = {
            'contact': '',
            'billing': '',
            'date_first': '',
            'date_second': '',
            'submit': 'Save Changes'
        }

        # Create test organization
        fund = Fund.objects.create(fund=0, organization=0, account=12345, name="LNL Test",
                                   last_used=timezone.datetime.today(), last_updated=timezone.datetime.today())
        org = Organization.objects.create(name="LNL", email="test@test.com", phone="1234567890",
                                          user_in_charge=self.user)
        org.save()
        org.associated_users.add(self.user)
        org.accounts.add(fund)
        org.save()

        valid_details = {
            'contact': str(self.user.pk),
            'billing': str(org.pk),
            'date_first': timezone.datetime.today().date(),
            'date_second': timezone.datetime.today().date() + timezone.timedelta(days=14),
            'submit': 'Save Changes'
        }
        # Should present errors on invalid data
        self.assertOk(self.client.get(reverse("projection:add-movies"), invalid_details))

        first_form = forms.BulkCreateForm(data=invalid_details)
        self.assertFalse(first_form.is_valid())

        first_form = forms.BulkCreateForm(data=valid_details)
        self.assertTrue(first_form.is_valid())

        # Test DateEntryFormsetBase is valid / invalid
        formset = formset_factory(forms.DateEntryFormSetBase, extra=0)

        valid_data = {
            'form-TOTAL_FORMS': 1,
            'form-INITIAL_FORMS': 1,
            'form-MIN_NUM_FORMS': 0,
            'form-MAX_NUM_FORMS': 1000,
            'form-0-date': datetime.date(2020, 1, 4),
            'form-0-name': 'Test Movie',
            'form-0-friday': False,
            'form-0-matinee': False,
            'form-0-saturday': True,
            'form-0-sunday': True,
            'submit': 'Submit'
        }

        invalid_data = {
            'form-TOTAL_FORMS': 1,
            'form-INITIAL_FORMS': 1,
            'form-MIN_NUM_FORMS': 0,
            'form-MAX_NUM_FORMS': 1000,
            'form-0-date': '',
            'form-0-name': 'Test Movie',
            'form-0-friday': False,
            'form-0-matinee': False,
            'form-0-saturday': True,
            'form-0-sunday': True,
            'submit': 'Submit'
        }
        valid_form = formset(data=valid_data)
        invalid_form = formset(data=invalid_data)

        self.assertTrue(valid_form.is_valid())
        self.assertFalse(invalid_form.is_valid())

        # Do not count week if not filled out
        empty_data = {
            'form-TOTAL_FORMS': 1,
            'form-INITIAL_FORMS': 1,
            'form-MIN_NUM_FORMS': 0,
            'form-MAX_NUM_FORMS': 1000,
            'form-0-date': datetime.date(2020, 1, 4),
            'form-0-name': '',
            'form-0-friday': False,
            'form-0-matinee': False,
            'form-0-saturday': True,
            'form-0-sunday': True,
            'submit': 'Submit'
        }
        empty_formset = formset(data=empty_data)
        for form in empty_formset:
            output = form.save_objects(user=self.user, contact=self.user, org=org, ip=None)
            self.assertEqual(output, [])

        # Give permissions to approve event
        permission = Permission.objects.get(codename="approve_event")
        self.user.user_permissions.add(permission)

        # Test posting of data (invalid and valid)
        resp = self.client.post("%s?contact=%s&billing=1&date_first=2020-01-01&date_second=2020-01-08&save=Continue" %
                                (reverse("projection:add-movies"), self.user.pk), invalid_data)
        self.assertNotContains(resp, "Events Added")
        self.assertOk(resp)

        resp = self.client.post("%s?contact=%s&billing=1&date_first=2020-01-01&date_second=2020-01-08&save=Continue" %
                                (reverse("projection:add-movies"), self.user.pk), valid_data)
        self.assertContains(resp, "Events Added")
        self.assertOk(resp)

        # Check that event was automatically approved
        movie = Event2019.objects.get(
            event_name="Test Movie",
            datetime_start=timezone.make_aware(datetime.datetime.combine(datetime.date(2020, 1, 4), datetime.time(20)))
        )
        self.assertTrue(movie.approved)

        # Check for both saturday and sunday events in output
        self.assertTrue(Event2019.objects.filter(
            event_name="Test Movie",
            datetime_start=timezone.make_aware(datetime.datetime.combine(datetime.date(2020, 1, 5),
                                                                         datetime.time(20)))).exists())

    def test_get_saturdays_for_range(self):
        # Test no Saturday in range
        output = views.get_saturdays_for_range(datetime.date(2020, 1, 1), datetime.date(2020, 1, 2))
        self.assertEqual(output, [])

        # Test one Saturday in range
        output = views.get_saturdays_for_range(datetime.date(2020, 1, 1), datetime.date(2020, 1, 8))
        self.assertEqual(output, [datetime.date(2020, 1, 4)])

        # Test two Saturdays in range and include end date if Saturday
        output = views.get_saturdays_for_range(datetime.date(2020, 1, 1), datetime.date(2020, 1, 11))
        self.assertEqual(output, [datetime.date(2020, 1, 4), datetime.date(2020, 1, 11)])

    def test_pit_request(self):
        level = models.PITLevel.objects.create(name_short="P1", name_long="PIT1", ordering=1)
        level.save()

        data = {
            "level": str(level.pk),
            "submitted_for": '',  # Allows empty date field
            "requested_on": timezone.now()
        }

        # Only members should be able to see
        res = self.client.post(reverse("projection:pit-request"), data)
        self.assertEqual(res.status_code, 403)

        permission = Permission.objects.get(codename='view_pits')
        self.user.user_permissions.add(permission)

        # Test form is valid
        form = forms.PITRequestForm(data=data)
        self.assertTrue(form.is_valid())

        self.assertOk(self.client.post(reverse("projection:pit-request"), data))

        # Test that new projectionist has been created
        self.assertTrue(models.Projectionist.objects.filter(user=self.user).exists())

    def test_pit_schedule(self):
        # Only those with editing permissions should have access
        self.assertOk(self.client.get(reverse("projection:pit-schedule")), 403)

        permission = Permission.objects.get(codename='edit_pits')
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("projection:pit-schedule")), 200)

    def test_pit_request_management(self):
        proj = models.Projectionist.objects.create(user=self.user)
        proj.save()
        date = timezone.now()
        level = models.PITLevel.objects.create(name_long="PIT 3", name_short="P3")
        level.save()
        request = models.PitRequest.objects.create(projectionist=proj, level=level, requested_on=date,
                                                   scheduled_for=date)
        request.save()

        # Only those with view permissions should have access to update a PIT request
        self.assertOk(self.client.get(reverse("projection:edit-request", args=[request.id])), 403)
        self.assertOk(self.client.get(reverse("projection:cancel-request", args=[request.id])), 403)

        permission = Permission.objects.get(codename='view_pits')
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("projection:edit-request", args=[request.id])), 200)
        self.assertOk(self.client.get(reverse("projection:cancel-request", args=[request.id])), 200)

        # On valid post, without edit permissions, should redirect to projection:grid
        valid_data = {
            'main-level': str(level.pk),
            'main-scheduled_for_0': timezone.datetime.today().date(),
            'main-scheduled_for_1': timezone.now().time(),
            'main-approved': True,
            'submit': 'Update'
        }
        self.assertRedirects(self.client.post(reverse("projection:edit-request", args=[request.id]), valid_data),
                             reverse("projection:grid"))

        # Only those with edit access should be able to manage/approve PIT requests
        self.assertOk(self.client.get(reverse("projection:manage-request", args=[request.id])), 403)

        permission = Permission.objects.get(codename='edit_pits')
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("projection:manage-request", args=[request.id])), 200)

        invalid_data = {
            'main-level': str(level.pk),
            'main-scheduled_for_0': '',
            'main-scheduled_for_1': '',
            'main-approved': True,
            'submit': 'Update'
        }

        admin_form = forms.PITRequestAdminForm(data=valid_data, instance=request, prefix='main')
        user_form = forms.PITRequestForm(data=valid_data, instance=request, prefix='main')

        self.assertTrue(admin_form.is_valid())
        self.assertTrue(user_form.is_valid())

        admin_form = forms.PITRequestAdminForm(data=invalid_data, prefix='main')
        invalid_data['main-level'] = ''
        user_form = forms.PITRequestForm(data=invalid_data, prefix='main')

        self.assertFalse(admin_form.is_valid())
        self.assertFalse(user_form.is_valid())

        # On error, we should get the forms back (should not redirect)
        self.assertOk(self.client.post(reverse("projection:edit-request", args=[request.pk]), invalid_data))
        self.assertOk(self.client.post(reverse("projection:manage-request", args=[request.pk]), invalid_data))

        # On success, all redirects should go to the pit schedule
        self.assertRedirects(self.client.post(reverse("projection:edit-request", args=[request.pk]), valid_data),
                             reverse("projection:pit-schedule"))
        self.assertRedirects(self.client.post(reverse("projection:manage-request", args=[request.pk]), valid_data),
                             reverse("projection:pit-schedule"))

    def test_cancel_pit_request(self):
        projectionist = models.Projectionist(user=self.user)
        projectionist.save()
        level = models.PITLevel.objects.create(name_short="P1", name_long="PIT1", ordering=1)
        level.save()
        request = models.PitRequest(projectionist=projectionist, level=level)
        request.save()
        request2 = models.PitRequest(projectionist=projectionist, level=level)
        request2.save()

        # The user should not be able to cancel a request without permission
        self.assertOk(self.client.get(reverse("projection:cancel-request", args=[1])), 403)

        permission = Permission.objects.get(codename="view_pits")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("projection:cancel-request", args=[1])))

        self.assertRedirects(self.client.post(reverse("projection:cancel-request", args=[1])),
                             reverse("projection:grid"))

        # Check redirect on edit perms
        permission = Permission.objects.get(codename="edit_pits")
        self.user.user_permissions.add(permission)

        self.assertRedirects(self.client.post(reverse("projection:cancel-request", args=[2])),
                             reverse("projection:pit-schedule"))
