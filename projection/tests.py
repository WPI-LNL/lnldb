from django.core.urlresolvers import reverse
from data.tests.util import ViewTestCase
from django.contrib.auth.models import Permission
from . import models
import datetime


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
            'pitinstances-0-created_on_0': "",
            'pitinstances-0-created_on_1': "",
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
            'nested-0-created_on_0': "",
            'nested-0-created_on_1': "",
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

        # check it was actually changed
        self.assertEqual(models.Projectionist.objects.get(user=self.user).license_number, '12345')
        # TODO: Check pitinstances

    def test_bulk_edit(self):
        # make sure normies can't see this
        self.assertOk(self.client.get(reverse("projection:bulk-edit")), 403)

        permission = Permission.objects.get(codename='edit_pits')
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("projection:bulk-edit")))
        # TODO: the rest of the test

    def test_bulk_movies(self):
        # make sure normies can't see this
        self.assertOk(self.client.get(reverse("projection:add-movies")), 403)

        permission = Permission.objects.get(codename='add_bulk_events')
        self.user.user_permissions.add(permission)
        self.assertOk(self.client.get(reverse("projection:add-movies")))

        # TODO: the rest of the test

    def test_pit_request(self):
        # Creates new projectionist if necessary
        data = {
            "level": "P3",
            "submitted_for": datetime.datetime.now(),
            "requested_on": datetime.datetime.now()
        }

        # Only members should be able to see
        res = self.client.post(reverse("projection:pit-request"), data)
        self.assertEqual(res.status_code, 403)

        permission = Permission.objects.get(codename='view_pits')
        self.user.user_permissions.add(permission)

        res = self.client.post(reverse("projection:pit-request"), data)
        self.assertEqual(res.status_code, 200)

    def test_pit_schedule(self):
        # Only those with editing permissions should have access
        self.assertOk(self.client.get(reverse("projection:pit-schedule")), 403)

        permission = Permission.objects.get(codename='edit_pits')
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("projection:pit-schedule")), 200)

    def test_pit_request_manage(self):
        proj = models.Projectionist.objects.create(user=self.user)
        proj.save()
        date = datetime.datetime.now()
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

        # Only those with edit access should be able to manage/approve PIT requests
        self.assertOk(self.client.get(reverse("projection:manage-request", args=[request.id])), 403)

        permission = Permission.objects.get(codename='edit_pits')
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("projection:manage-request", args=[request.id])), 200)
