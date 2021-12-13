from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

import datetime

# Create your models here.

class Position(models.Model):
    """
    Describes a leadership position for a specific time. A new position instance
    should be created every time one needs to be filled.
    """
    name = models.CharField(verbose_name="Position Name", max_length=64,
            null=False, blank=False)
    description = models.TextField(verbose_name="Position Description",
            null=False, blank=False)
    position_start = models.DateField(verbose_name="Term Start", null=False,
            blank=False)
    position_end = models.DateField(verbose_name="Term End", null=False,
            blank=False)
    reports_to = models.ForeignKey(get_user_model(), on_delete=models.CASCADE,
            blank=True, null=True)
    closes = models.DateTimeField(verbose_name="Applications Close", null=True,
            blank=True)
    application_form = models.URLField(verbose_name="Link to external application form", null=True, blank=True, max_length=128)

    def __str__(self):
        return f"{self.name}"

    class Meta:
        permissions = [
                ('apply', 'Can apply for positions')
                ]

    def is_open(self):
        return self.closes >= timezone.now()
    
