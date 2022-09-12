# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models
from django.conf import settings


# Create your models here.
class TokenRequest(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="token_requests", on_delete=models.CASCADE)
    code = models.PositiveIntegerField()
    attempts = models.PositiveSmallIntegerField()
    timestamp = models.DateTimeField()
