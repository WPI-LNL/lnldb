import logging
from datetime import date, timedelta
from django.utils import timezone
from django.contrib.auth.models import Permission
from data.tests.util import ViewTestCase
from events.tests.generators import UserFactory
from django.urls.base import reverse

from . import models


logging.disable(logging.WARNING)


class TrainingTests(ViewTestCase):
    def setUp(self):
        super(TrainingTests, self).setUp()
        self.user2 = UserFactory.create(password="123")
        self.training_type = models.TrainingType.objects.create(name="Truss Training", description="It's in the name")
        self.training = models.Training.objects.create(
            training_type=self.training_type, date=date.today(), trainer=self.user, recorded_by=self.user
        )
        self.trainee = models.Trainee.objects.create(training=self.training, person=self.user2)

    def test_training_is_expired(self):
        # A training with no expiration
        self.assertFalse(self.training.is_expired())

        # A training with an expiration in the future (includes today)
        self.training.expiration_date = date.today() + timedelta(days=1)
        self.training.save()

        self.assertFalse(self.training.is_expired())

        # A training with an expiration in the past
        self.training.expiration_date = date.today() + timedelta(days=-1)
        self.training.save()

        self.assertTrue(self.training.is_expired())

    def test_trainee_is_valid(self):
        # Training should be valid if it hasn't been revoked and has not expired
        self.assertTrue(self.trainee.is_valid())

        self.training.expiration_date = date.today() + timedelta(days=-1)
        self.training.save()

        self.assertFalse(self.trainee.is_valid())

        self.training.expiration_date = date.today()
        self.training.save()
        self.trainee.revoked = True
        self.trainee.save()

        self.assertFalse(self.trainee.is_valid())

    def test_trainee_was_valid_on(self):
        # Try date before training
        now = date.today()
        days_past_2 = now + timedelta(days=-2)
        days_future_2 = now + timedelta(days=2)
        self.assertFalse(self.trainee.was_valid_on(days_past_2))

        # Try date before expiration
        self.training.expiration_date = days_future_2
        self.training.save()

        self.assertTrue(self.trainee.was_valid_on(date.today()))

        # Try date after expiration
        self.assertFalse(self.trainee.was_valid_on(date.today() + timedelta(days=3)))

        # Check that if it was revoked it was valid on date before revocation
        self.trainee.revoked = True
        self.trainee.revoked_on = timezone.now() + timezone.timedelta(days=1)
        self.trainee.save()

        self.assertTrue(self.trainee.was_valid_on(timezone.now().date()))
        self.assertFalse(self.trainee.was_valid_on(timezone.now().date() + timezone.timedelta(days=1)))

    def test_training_list(self):
        # Create some extra data
        training_type2 = models.TrainingType.objects.create(name="Lift Training", description="Lifts!!!")
        training2 = models.Training.objects.create(
            training_type=training_type2, date=date.today() + timedelta(days=-1), trainer=self.user,
            recorded_by=self.user
        )
        models.Trainee.objects.create(training=training2, person=self.user)
        models.Trainee.objects.create(training=training2, person=self.user2)

        # Check that the user has the proper permissions then make sure the page loads ok
        self.assertOk(self.client.get(reverse("members:training:list")), 403)

        permission = Permission.objects.get(codename="view_training")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("members:training:list")))

        # Check that POST requests are not permitted
        self.assertOk(self.client.post(reverse("members:training:list")), 405)

    def test_enter_training(self):
        # Check that the user has proper permissions
        self.assertOk(self.client.get(reverse("members:training:entry")), 403)

        permission = Permission.objects.get(codename="add_training")
        self.user.user_permissions.add(permission)

        # Will the need the following permissions as well for redirects
        permission = Permission.objects.get(codename="view_training")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("members:training:entry")))

        valid_data = {
            'training_type': str(self.training_type.pk),
            'date': date.today(),
            'trainer': str(self.user.pk),
            'trainees': [str(self.user2.pk)],
            'expiration_date': date.today() + timedelta(days=365),
            'notes': '',
            'save': 'Save'
        }

        valid_data_external = {
            'training_type': str(self.training_type.pk),
            'date': date.today(),
            'trainer': '',
            'trainees': [str(self.user2.pk)],
            'expiration_date': '',
            'notes': '',
            'save': 'Save'
        }

        self_training = {
            'training_type': str(self.training_type.pk),
            'date': date.today(),
            'trainer': str(self.user.pk),
            'trainees': [str(self.user.pk)],
            'expiration_date': '',
            'notes': '',
            'save': 'Save'
        }

        invalid_date = {
            'training_type': str(self.training_type.pk),
            'date': date.today() + timedelta(days=1),
            'trainer': str(self.user.pk),
            'trainees': [str(self.user2.pk)],
            'expiration_date': '',
            'notes': '',
            'save': 'Save'
        }

        # Should throw an error because this training type is not marked as external (requires trainer field)
        self.assertOk(self.client.post(reverse("members:training:entry"), valid_data_external))

        self.training_type.external = True
        self.training_type.save()

        self.assertRedirects(self.client.post(reverse("members:training:entry"), valid_data_external),
                             reverse("members:training:list"))

        # Trainer cannot train others unless they have the training themselves
        self.assertOk(self.client.post(reverse("members:training:entry"), valid_data))

        models.Trainee.objects.create(training=self.training, person=self.user)

        self.assertRedirects(self.client.post(reverse("members:training:entry"), valid_data),
                             reverse("members:training:list"))

        # Users cannot train themselves
        self.assertOk(self.client.post(reverse("members:training:entry"), self_training))

        # Training cannot have taken place in the future
        self.assertOk(self.client.post(reverse("members:training:entry"), invalid_date))

    def test_trainee_notes(self):
        # Check that the user has proper permissions
        self.assertOk(self.client.get(reverse("members:training:traineenotes", args=[self.trainee.pk])), 403)

        permission = Permission.objects.get(codename="edit_trainee_notes")
        self.user.user_permissions.add(permission)

        # Will need the following permissions as well for redirects
        permission = Permission.objects.get(codename="view_user")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("members:training:traineenotes", args=[self.trainee.pk])))

        # Return 404 if training record does not exist
        self.assertOk(self.client.get(reverse("members:training:traineenotes", args=[self.trainee.pk + 1])), 404)

        # Redirect back to user profile if training has expired (can't update notes)
        self.training.expiration_date = date.today() + timedelta(days=-1)
        self.training.save()

        self.assertRedirects(self.client.get(reverse("members:training:traineenotes", args=[self.trainee.pk])),
                             reverse("accounts:detail", args=[self.user2.pk]))

        self.training.expiration_date = date.today() + timedelta(days=365)
        self.training.save()

        valid_data = {
            'notes': 'The dingus crashed the skyjack into a wall',
            'save': 'Save'
        }

        self.assertRedirects(self.client.post(reverse("members:training:traineenotes", args=[self.trainee.pk]),
                                              valid_data), reverse("accounts:detail", args=[self.user2.pk]))
        self.trainee.refresh_from_db()
        self.assertEqual(self.trainee.notes, 'The dingus crashed the skyjack into a wall')

    def test_revoke_training(self):
        # Check that the user has proper permissions
        self.assertOk(self.client.post(reverse("members:training:revoke", args=[self.trainee.pk])), 403)

        permission = Permission.objects.get(codename="revoke_training")
        self.user.user_permissions.add(permission)

        # Will need the following permissions as well for redirects
        permission = Permission.objects.get(codename="view_user")
        self.user.user_permissions.add(permission)

        # Ensure only POST requests are permitted
        self.assertOk(self.client.get(reverse("members:training:revoke", args=[self.trainee.pk])), 405)

        # Check that we cannot revoke a training that is already invalid or has already been revoked
        self.training.expiration_date = date.today() + timedelta(days=-1)
        self.training.save()

        resp = self.client.post(reverse("members:training:revoke", args=[self.trainee.pk]))
        self.assertRedirects(resp, reverse("accounts:detail", args=[self.user2.pk]))

        resp = self.client.post(reverse("members:training:revoke", args=[self.trainee.pk]), follow=True)
        self.assertContains(resp, "not currently valid")

        self.training.expiration_date = date.today() + timedelta(days=365)
        self.training.save()
        self.trainee.revoked = True
        self.trainee.save()

        resp = self.client.post(reverse("members:training:revoke", args=[self.trainee.pk]), follow=True)
        self.assertContains(resp, "already revoked")

        resp = self.client.post(reverse("members:training:revoke", args=[self.trainee.pk]))
        self.assertRedirects(resp, reverse("accounts:detail", args=[self.user2.pk]))

        self.trainee.revoked = False
        self.trainee.save()

        # Verify that the training has been revoked
        self.assertRedirects(self.client.post(reverse("members:training:revoke", args=[self.trainee.pk])),
                             reverse("accounts:detail", args=[self.user2.pk]))
        self.trainee.refresh_from_db()
        self.assertFalse(self.trainee.is_valid())
