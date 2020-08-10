# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models
from django.conf import settings

METHODS = (
    ('GET', 'GET'),
    ('POST', 'POST'),
    ('DELETE', 'DELETE'),
)

AUTH_OPTIONS = (
    ('none', 'None'),
    # ('session', 'Session-based'),
    ('token', 'Token-based'),
    ('project', 'Project-based')
)

PRIMITIVE_TYPES = (
    ('int', 'integer'),
    ('string', 'string'),
    ('bool', 'boolean'),
    ('datetime', 'datetime'),
    ('date', 'date'),
    ('time', 'time'),
    ('array', 'array'),
)


# Create your models here.
class Endpoint(models.Model):
    name = models.CharField(max_length=60)
    url = models.CharField(max_length=100, verbose_name="Path",
                           help_text="Relative path to endpoint (Ex: https://lnl.wpi.edu/api/v1/example --> example)")
    description = models.TextField(help_text="What is this endpoint used for?")
    parameter_note = models.CharField(max_length=500, null=True, blank=True, verbose_name="Note",
                                      help_text="Explain any special relationships between parameters here")
    example = models.CharField(max_length=200, help_text="Provide an example of how the parameters might be "
                                                         "formatted. (Ex: id=Example&display=true)")
    response = models.TextField(help_text="Paste the API response using the URL generated from the example above")
    last_modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class Method(models.Model):
    endpoint = models.ForeignKey(Endpoint, related_name="methods", on_delete=models.CASCADE)
    method = models.CharField(max_length=7, choices=METHODS)
    auth = models.CharField(max_length=7, choices=AUTH_OPTIONS)


class Parameter(models.Model):
    endpoint = models.ForeignKey(Endpoint, related_name="parameters", on_delete=models.CASCADE)
    name = models.CharField(max_length=20)
    type = models.CharField(max_length=8, choices=PRIMITIVE_TYPES)
    description = models.TextField()

    def __str__(self):
        return self.name


class RequestParameter(Parameter):
    required = models.BooleanField(null=False, default=False)

    class Meta:
        verbose_name = "Request Parameter"


class ResponseKey(Parameter):
    class Meta:
        verbose_name = "Response Value"


class Option(models.Model):
    endpoint = models.ForeignKey(Endpoint, related_name="parameterOptions", on_delete=models.CASCADE)
    parameter = models.ForeignKey(Parameter, related_name="options", on_delete=models.CASCADE)
    key = models.CharField(max_length=20)
    value = models.CharField(max_length=120, null=True, blank=True)

    def __str__(self):
        return self.parameter.name


class TokenRequest(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="token_requests", on_delete=models.CASCADE)
    code = models.PositiveSmallIntegerField()
    attempts = models.PositiveSmallIntegerField()
    timestamp = models.DateTimeField()
