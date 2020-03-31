# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.shortcuts import render
from django.db.models import Q
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.exceptions import APIException, NotFound, ParseError, NotAuthenticated, PermissionDenied

from events.models import OfficeHour, HourChange
from data.models import Notification
from .models import Endpoint, RequestParameter, ResponseKey
from .serializers import OfficerSerializer, HourSerializer, ChangeSerializer, NotificationSerializer


# Create your views here.
def verify_endpoint(name):
    """
    All API endpoint views must make a call to this function. This ensures that authentication methods are up-to-date
    and can be configured from the Admin interface. It also forces you to provide all the details necessary to form the
    documentation!

    :param name: The user-readable name of the endpoint
    :return: Raises an exception if necessary and returns nothing if everything checks out
    """
    endpoint = Endpoint.objects.all().filter(name__iexact=name).first()
    if endpoint is None:
        raise APIException(detail="Configuration error. Please contact the webmaster.", code=500)
    # Using basic catch all for the time being
    for method in endpoint.methods.all():
        if method.auth != 'none':
            raise PermissionDenied(detail="You are not allowed to access this resource.", code=403)


class OfficerViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OfficerSerializer
    lookup_field = 'title'

    def get_queryset(self):
        verify_endpoint('Officers')
        queryset = get_user_model().objects.filter(groups__name="Officer").exclude(title__isnull=True).order_by('title')
        title = self.request.query_params.get('title', None)
        first_name = self.request.query_params.get('first_name', None)
        last_name = self.request.query_params.get('last_name', None)
        if title is not None:
            queryset = queryset.filter(title=title)
        if first_name is not None:
            queryset = queryset.filter(first_name=first_name)
        if last_name is not None:
            queryset = queryset.filter(last_name=last_name)
        if queryset.count() is 0:
            raise NotFound(detail='Not found', code=404)
        return queryset


class HourViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = HourSerializer

    def list(self, request):
        queryset = self.get_queryset()
        if queryset.count() is 0:
            content = {'204': 'No entries were found for the specified parameters'}
            return Response(content, status=status.HTTP_204_NO_CONTENT)
        serializer = HourSerializer(queryset, many=True)
        return Response(serializer.data)

    def get_queryset(self):
        verify_endpoint('Office Hours')
        queryset = OfficeHour.objects.all().order_by('day')
        officer = self.request.query_params.get('officer', None)
        day = self.request.query_params.get('day', None)
        start = self.request.query_params.get('start', None)
        end = self.request.query_params.get('end', None)
        if officer is not None:
            queryset = queryset.filter(officer__title=officer)
        if day is not None:
            queryset = queryset.filter(day=day)
        if start is not None and end is not None:
            queryset = queryset.filter(hour_start__lt=end).filter(hour_end__gt=start)
        if start is not None and end is None:
            queryset = queryset.filter(hour_start=start)
        if end is not None and start is None:
            queryset = queryset.filter(hour_end=end)
        return queryset


class ChangeViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ChangeSerializer

    def list(self, request):
        queryset = self.get_queryset()
        if queryset.count() is 0:
            content = {'204': 'No updates were found for the specified parameters'}
            return Response(content, status=status.HTTP_204_NO_CONTENT)
        serializer = ChangeSerializer(queryset, many=True)
        return Response(serializer.data)

    def get_queryset(self):
        verify_endpoint('Office Hour Updates')
        queryset = HourChange.objects.all().order_by('date_posted')
        officer = self.request.query_params.get('officer', None)
        expires = self.request.query_params.get('expires', None)
        if officer is not None:
            queryset = queryset.filter(officer__title=officer)
        if expires is not None:
            queryset = queryset.filter(expires__gte=expires)
        return queryset


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    def list(self, request):
        queryset = self.get_queryset()
        if queryset.count() is 0:
            content = {'204': 'No alerts were found for the specified parameters'}
            return Response(content, status=status.HTTP_204_NO_CONTENT)
        serializer = NotificationSerializer(queryset, many=True)
        return Response(serializer.data)

    def get_queryset(self):
        verify_endpoint('Notifications')
        queryset = Notification.objects.filter(target__iexact='all')
        project = self.request.query_params.get('project_id', None)
        page = self.request.query_params.get('page_id', None)
        dir = self.request.query_params.get('directory', None)
        if project is None or project != "LNL":
            raise NotFound(detail='Invalid project id', code=404)
        if page is None:
            raise ParseError(detail='Page ID is required', code=400)
        queryset |= Notification.objects.filter(target=page)
        if dir is not None:
            query = Q()
            directories = dir.split('/')
            directories.pop(0)
            for directory in directories:
                if directory is not None:
                    query |= Q(target__icontains=directory)
            queryset |= Notification.objects.filter(query)
        return queryset


@login_required
def docs(request):
    context = {
        'endpoints': Endpoint.objects.all(),
        'requestParameters': RequestParameter.objects.all(),
        'responseKeys': ResponseKey.objects.all(),
    }
    return render(request, 'api_docs.html', context)
