# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.contrib import admin
from django.core.urlresolvers import resolve
from .models import Endpoint, Method, Parameter, RequestParameter, ResponseKey, Option


# Register your models here.
class MethodAdmin(admin.TabularInline):
    model = Method


class ParameterAdmin(admin.StackedInline):
    model = RequestParameter


class OptionAdmin(admin.TabularInline):
    model = Option

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'parameter':
            resolved = resolve(request.path_info)
            if resolved.args:
                endpoint = self.parent_model.objects.get(pk=resolved.args[0])
            else:
                endpoint = None
            kwargs["queryset"] = Parameter.objects.filter(endpoint=endpoint)
            return super(OptionAdmin, self).formfield_for_foreignkey(db_field, request, **kwargs)


class ResponseKeyAdmin(admin.StackedInline):
    model = ResponseKey


class EndpointAdmin(admin.ModelAdmin):
    inlines = [MethodAdmin, ParameterAdmin, ResponseKeyAdmin, OptionAdmin]


admin.site.register(Endpoint, EndpointAdmin)
