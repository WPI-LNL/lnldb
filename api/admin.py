# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.contrib import admin
from .models import Endpoint, Method, RequestParameter, ResponseKey, Option


# Register your models here.
class MethodAdmin(admin.TabularInline):
    model = Method


class ParameterAdmin(admin.StackedInline):
    model = RequestParameter


class OptionAdmin(admin.TabularInline):
    model = Option


class ResponseKeyAdmin(admin.StackedInline):
    model = ResponseKey


class EndpointAdmin(admin.ModelAdmin):
    inlines = [MethodAdmin, ParameterAdmin, ResponseKeyAdmin, OptionAdmin]


admin.site.register(Endpoint, EndpointAdmin)
