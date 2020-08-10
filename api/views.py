# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.shortcuts import render
from django.db.models import Q
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import api_view, authentication_classes
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import APIException, NotFound, ParseError, AuthenticationFailed, PermissionDenied

from random import randint

from accounts.forms import SMSOptInForm
from emails.generators import generate_sms_email
from events.models import OfficeHour, HourChange
from data.models import Notification, Extension
from .models import Endpoint, RequestParameter, ResponseKey, TokenRequest
from .serializers import OfficerSerializer, HourSerializer, ChangeSerializer, NotificationSerializer


# Create your views here.
def verify_endpoint(name, request):
    """
    All API endpoint views must make a call to this function. This ensures that authentication methods are up-to-date
    and can be configured from the Admin interface. It also forces you to provide all the details necessary to form the
    documentation!

    :param name: The user-readable name of the endpoint
    :param request: The calling view's request object
    :return: Raises an exception if necessary and returns nothing if everything checks out
    """
    endpoint = Endpoint.objects.all().filter(name__iexact=name).first()
    if endpoint is None:
        raise APIException(detail="Configuration error. Please contact the webmaster.", code=500)
    for method in endpoint.methods.all():
        if method.auth != 'none' and method.method == request.method:
            if not request.user.is_authenticated:
                raise AuthenticationFailed(detail="You must be signed in to access this resource.")
            app = Extension.objects.filter(api_key=request.data.get('APIKey', 'None')).first()
            user_apps = request.user.connected_services.filter(enabled=True)
            if app is None or app not in user_apps:
                raise PermissionDenied(detail="You are not allowed to access this resource. "
                                              "API key may be missing or invalid. ", code=403)


class OfficerViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OfficerSerializer
    authentication_classes = []
    lookup_field = 'title'

    def get_queryset(self):
        verify_endpoint('Officers', self.request)
        queryset = get_user_model().objects.filter(groups__name="Officer").exclude(title__isnull=True).order_by('title')
        title = self.request.query_params.get('title', None)
        first_name = self.request.query_params.get('first_name', None)
        last_name = self.request.query_params.get('last_name', None)
        if title is not None:
            queryset = queryset.filter(title__iexact=title)
        if first_name is not None:
            queryset = queryset.filter(first_name__iexact=first_name)
        if last_name is not None:
            queryset = queryset.filter(last_name__iexact=last_name)
        if queryset.count() is 0:
            raise NotFound(detail='Not found', code=404)
        return queryset


class HourViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = HourSerializer
    authentication_classes = []

    def list(self, request):
        queryset = self.get_queryset()
        if queryset.count() is 0:
            content = {'204': 'No entries were found for the specified parameters'}
            return Response(content, status=status.HTTP_204_NO_CONTENT)
        serializer = HourSerializer(queryset, many=True)
        return Response(serializer.data)

    def get_queryset(self):
        verify_endpoint('Office Hours', self.request)
        queryset = OfficeHour.objects.all().order_by('day')
        officer = self.request.query_params.get('officer', None)
        day = self.request.query_params.get('day', None)
        start = self.request.query_params.get('start', None)
        end = self.request.query_params.get('end', None)
        if officer is not None:
            queryset = queryset.filter(officer__title__iexact=officer)
        if day is not None:
            queryset = queryset.filter(day=day)
        if start is not None and end is not None:
            queryset = queryset.filter(hour_start__lte=end).filter(hour_end__gte=start)
        if start is not None and end is None:
            queryset = queryset.filter(hour_start=start)
        if end is not None and start is None:
            queryset = queryset.filter(hour_end=end)
        return queryset


class ChangeViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ChangeSerializer
    authentication_classes = []

    def list(self, request):
        queryset = self.get_queryset()
        if queryset.count() is 0:
            content = {'204': 'No updates were found for the specified parameters'}
            return Response(content, status=status.HTTP_204_NO_CONTENT)
        serializer = ChangeSerializer(queryset, many=True)
        return Response(serializer.data)

    def get_queryset(self):
        verify_endpoint('Office Hour Updates', self.request)
        queryset = HourChange.objects.all().order_by('date_posted')
        officer = self.request.query_params.get('officer', None)
        expires = self.request.query_params.get('expires', None)
        if officer is not None:
            queryset = queryset.filter(officer__title__iexact=officer)
        if expires is not None:
            queryset = queryset.filter(expires__gte=expires)
        return queryset


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    authentication_classes = []

    def list(self, request):
        queryset = self.get_queryset()
        if queryset.count() is 0:
            content = {'204': 'No alerts were found for the specified parameters'}
            return Response(content, status=status.HTTP_204_NO_CONTENT)
        serializer = NotificationSerializer(queryset, many=True)
        return Response(serializer.data)

    def get_queryset(self):
        verify_endpoint('Notifications', self.request)
        queryset = Notification.objects.filter(target__iexact='all')
        project = self.request.query_params.get('project_id', None)
        page = self.request.query_params.get('page_id', None)
        dir = self.request.query_params.get('directory', None)
        if project is None or project != "LNL":
            raise NotFound(detail='Invalid project id', code=404)
        if page is None:
            raise ParseError(detail='Page ID is required', code=400)
        queryset |= Notification.objects.filter(target=page)
        if dir not in [None, '']:
            query = Q()
            directories = dir.split('/')
            directories.pop(0)
            for directory in directories:
                if directory is not None:
                    query |= Q(target__icontains=directory)
            queryset |= Notification.objects.filter(query)
        return queryset


@login_required
def request_token(request):
    missing = True
    sent = False
    context = {'NO_FOOT': True, 'NO_NAV': True, 'NO_API': True,
               'styles': "#main {\n\tbackground-color: white !important;\n\theight: 100vh;\n}\n.text-white {"
                         "\n\tcolor: black !important;\n}\n.help-block {\n\tdisplay: none;\n}"}

    if request.user.phone and request.user.carrier:
        missing = False
        context['phone'] = "(" + request.user.phone[:3] + ") " + request.user.phone[3:6] + "-" + request.user.phone[6:]

    if request.method == 'POST':
        form = SMSOptInForm(request.POST, instance=request.user, request=request, exists=not missing)
        if form.is_valid():
            if missing:
                form.save()
                missing = False
                form = SMSOptInForm(request=request, exists=not missing)
                context['phone'] = "(" + request.user.phone[:3] + ") " + request.user.phone[3:6] + "-" + \
                                   request.user.phone[6:]
            else:
                code = randint(100000, 999999)
                message = {
                    "user": request.user,
                    "message": str(code) + "\nUse this code for LNL verification"
                }
                email = generate_sms_email(message)
                try:
                    token_request = TokenRequest.objects.get(user=request.user)
                    token_request.code = code
                    token_request.attempts = settings.TFV_ATTEMPTS
                    token_request.timestamp = timezone.now()
                    token_request.save()
                except TokenRequest.DoesNotExist:
                    TokenRequest.objects.create(user=request.user, code=code, attempts=settings.TFV_ATTEMPTS,
                                                timestamp=timezone.now())
                email.send()
                sent = True
    else:
        form = SMSOptInForm(instance=request.user, request=request, exists=not missing)
    context['form'] = form
    context['missing'] = missing
    context['sent'] = sent
    return render(request, "phone_verification.html", context)


@api_view(['POST'])
@authentication_classes([])
def fetch_token(request):
    data = request.data
    key = data.get('APIKey', None)
    code = data.get('code', None)
    username = data.get('username', None)
    if key is None or code is None or username is None:
        raise ParseError(detail="Bad request. One or more required keys are missing or malformed.", code=400)
    app = get_object_or_404(Extension, api_key=key, enabled=True)
    user = get_object_or_404(get_user_model(), username=username)
    if app not in user.connected_services.filter(enabled=True):
        raise AuthenticationFailed(detail="User has not granted proper permissions for this application", code=403)
    try:
        token_request = TokenRequest.objects.get(user=user)
    except TokenRequest.DoesNotExist:
        raise NotFound(detail="Not found", code=404)
    if token_request.timestamp + timezone.timedelta(seconds=settings.TFV_CODE_EXPIRES) <= timezone.now() or \
            token_request.attempts == 0:
        return Response({'detail': "Code has expired or exceeded allowed attempts"}, status=status.HTTP_410_GONE)
    if token_request.code != int(code):
        token_request.attempts -= 1
        token_request.save()
        return Response(
            {"detail": "Invalid verification code. {} attempts remaining.".format(token_request.attempts)},
            status=status.HTTP_202_ACCEPTED
        )

    # Everything checks out
    token_request.code = 0
    token_request.attempts = 0
    token_request.save()

    token, created = Token.objects.get_or_create(user=user)

    token = {"token": token.key}

    return Response(token, status=status.HTTP_200_OK)


@login_required
def docs(request):
    endpoints = Endpoint.objects.all()

    # Obtain the most recent last_modified date
    last_modified = None
    for endpoint in endpoints:
        if last_modified is None or endpoint.last_modified > last_modified:
            last_modified = endpoint.last_modified

    context = {
        'endpoints': endpoints,
        'requestParameters': RequestParameter.objects.all(),
        'responseKeys': ResponseKey.objects.all(),
        'last_modified': last_modified
    }
    return render(request, 'api_docs.html', context)
