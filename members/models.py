from datetime import date

from django.conf import settings
from django.db import models


class TrainingType(models.Model):
    name = models.CharField(max_length=64, unique=True)
    external = models.BooleanField(default=False)
    description = models.TextField()

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Training(models.Model):
    """ A training event """
    training_type = models.ForeignKey(TrainingType, on_delete=models.PROTECT, related_name='trainings')
    date = models.DateField()
    trainer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='trainings_run')
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, editable=False, related_name='trainings_entered')
    recorded_on = models.DateTimeField(auto_now_add=True)
    expiration_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-date', '-recorded_on']

    def __str__(self):
        return str(self.training_type) + ' on ' + str(self.date)

    def is_expired(self):
        return self.expiration_date is not None and date.today() > self.expiration_date


class Trainee(models.Model):
    """ Record of an individual's completion or revocation of training """
    training = models.ForeignKey(Training, on_delete=models.CASCADE, related_name='trainees')
    person = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='trainings')
    revoked = models.BooleanField(default=False)
    revoked_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='trainings_revoked')
    revoked_on = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        order_with_respect_to = 'training'
        permissions = (
            ('revoke_training', 'Revoke a member\'s training'),
            ('edit_trainee_notes', 'Edit training notes on a person'),
        )

    def __str__(self):
        return str(self.person) + ' for ' + str(self.training)

    def is_valid(self):
        return not self.revoked and not self.training.is_expired()

    def was_valid_on(self, date):
        return date > self.training.date \
            and (self.training.expiration_date is None or date <= self.training.expiration_date) \
            and (not self.revoked or date <= self.revoked_on.date())
