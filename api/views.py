# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.shortcuts import render
from django.db.models import Q
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.template.loader import render_to_string
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import viewsets, status, serializers
from rest_framework.response import Response
from rest_framework.decorators import api_view, authentication_classes, action
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import NotFound, ParseError, AuthenticationFailed, PermissionDenied
from drf_spectacular.utils import extend_schema_view, extend_schema, OpenApiParameter, OpenApiTypes, OpenApiResponse, \
    OpenApiExample, inline_serializer

from random import randint

from accounts.forms import SMSOptInForm
from emails.generators import generate_sms_email
from events.models import OfficeHour, Event2019, Location, CrewAttendanceRecord
from data.models import Notification, Extension, ResizedRedirect
from pages.models import Page
from .models import TokenRequest
from .serializers import OfficerSerializer, HourSerializer, NotificationSerializer, EventSerializer, \
    AttendanceSerializer, RedirectSerializer, CustomPageSerializer, TokenRequestSerializer


# Create your views here.
@extend_schema_view(
    list=extend_schema(
        operation_id="Officers",
        parameters=[
            OpenApiParameter('title', OpenApiTypes.STR, OpenApiParameter.QUERY, False, "The officer's title"),
            OpenApiParameter(
                'first_name', OpenApiTypes.STR, OpenApiParameter.QUERY, False, "The first name of the officer"
            ),
            OpenApiParameter(
                'last_name', OpenApiTypes.STR, OpenApiParameter.QUERY, False, "The last name of the officer"
            ),
            OpenApiParameter(
                'options', OpenApiTypes.STR, OpenApiParameter.QUERY, False, "Additional fields to include in response",
                style='simple'
            )
        ],
        responses={
            200: OpenApiResponse(OfficerSerializer, description="Ok"),
            404: OpenApiResponse(description="Not found")
        }
    )
)
class OfficerViewSet(viewsets.ReadOnlyModelViewSet):
    """ Use this endpoint to get a list of the club's officers """
    serializer_class = OfficerSerializer
    authentication_classes = []
    lookup_field = 'title'

    def get_queryset(self):
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
        if queryset.count() == 0:
            raise NotFound(detail='Not found', code=404)
        return queryset


class HourViewSet(viewsets.ReadOnlyModelViewSet):
    """ Use this endpoint to get a list of our office hours """
    serializer_class = HourSerializer
    authentication_classes = []

    @extend_schema(
        operation_id="Office Hours",
        parameters=[
            OpenApiParameter("officer", OpenApiTypes.STR, OpenApiParameter.QUERY, False, "The officer's title"),
            OpenApiParameter(
                "day", OpenApiTypes.INT, OpenApiParameter.QUERY, False,
                "The day of the week (0 = Sunday, 1 = Monday, etc.)", list(range(7))
            ),
            OpenApiParameter("start", OpenApiTypes.TIME, OpenApiParameter.QUERY, False, "The start time"),
            OpenApiParameter("end", OpenApiTypes.TIME, OpenApiParameter.QUERY, False, "The end time")
        ],
        responses={
            200: OpenApiResponse(HourSerializer),
            204: None,
            400: OpenApiResponse(description="Bad request")
        },
        examples=[
            OpenApiExample(
                'Example with start and end time',
                [{'officer': 'President', 'day': 4, 'hour_start': '13:30:00', 'hour_end': '15:30:00'}],
                description='If both "start" and "end" are included in the request, the response will contain entries '
                            'that overlap with that time span.',
                summary="/api/v1/office-hours?start=13:00&end=14:00",
                response_only=True
            )
        ]
    )
    def list(self, request):
        try:
            queryset = self.get_queryset()
        except ValidationError:
            content = {
                '400': 'Bad request. Please ensure that you have supplied valid start and end times, if applicable.'
            }
            return Response(content, status=status.HTTP_400_BAD_REQUEST)
        if queryset.count() == 0:
            content = {'204': 'No entries were found for the specified parameters'}
            return Response(content, status=status.HTTP_204_NO_CONTENT)
        serializer = HourSerializer(queryset, many=True)
        return Response(serializer.data)

    def get_queryset(self):
        queryset = OfficeHour.objects.all().order_by('day', 'hour_start')
        officer = self.request.query_params.get('officer', None)
        day = self.request.query_params.get('day', None)
        location = self.request.query_params.get('location', None)
        start = self.request.query_params.get('start', None)
        end = self.request.query_params.get('end', None)
        if officer is not None:
            queryset = queryset.filter(officer__title__iexact=officer)
        if day is not None:
            queryset = queryset.filter(day=day)
        if location is not None:
            queryset = queryset.filter(location__name__icontains=location)
        if start is not None and end is not None:
            queryset = queryset.filter(hour_start__lte=end).filter(hour_end__gte=start)
        if start is not None and end is None:
            queryset = queryset.filter(hour_start=start)
        if end is not None and start is None:
            queryset = queryset.filter(hour_end=end)
        return queryset


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """ Use this endpoint to fetch notifications for the website """
    authentication_classes = []

    @extend_schema(
        operation_id="Site Notifications",
        parameters=[
            OpenApiParameter(
                'project_id', OpenApiTypes.STR, OpenApiParameter.QUERY, True,
                "Unique identifier for the application accessing the endpoint"
            ),
            OpenApiParameter(
                'page_id', OpenApiTypes.STR, OpenApiParameter.QUERY, True,
                "Unique identifier assigned to the calling view"
            ),
            OpenApiParameter(
                'directory', OpenApiTypes.STR, OpenApiParameter.QUERY, False,
                "Parent directory of the calling view (if applicable). Subscribes the page to directory notifications."
            ),
        ],
        responses={
            200: inline_serializer(
                'Notification',
                fields={
                    'id': serializers.CharField(),
                    'class': serializers.IntegerField(),
                    'format': serializers.CharField(),
                    'type': serializers.CharField(),
                    'expires': serializers.DateTimeField(),
                    'title': serializers.CharField(),
                    'message': serializers.CharField()
                }
            ),
            204: None
        },
        examples=[
            OpenApiExample(
                'Notification',
                {
                    "id": "SWA001",
                    "format": "notification",
                    "type": "advisory",
                    "class": 2,
                    "title": "Upcoming Maintenance",
                    "message": "All Lens and Lights web services will be temporarily unavailable on January 5 from "
                               "2:00-2:45 AM EST as we perform routine upgrades and maintenance. We apologize for the "
                               "inconvenience.",
                    "expires": "2020-01-05T07:00:00Z"
                },
                description=render_to_string('api/notification_response.html').strip(),
                response_only=True
            )
        ]
    )
    def list(self, request):
        queryset = self.get_queryset()
        if queryset.count() == 0:
            content = {'204': 'No alerts were found for the specified parameters'}
            return Response(content, status=status.HTTP_204_NO_CONTENT)
        serializer = NotificationSerializer(queryset, many=True)
        return Response(serializer.data)

    def get_queryset(self):
        queryset = Notification.objects.filter(target__iexact='all')
        project = self.request.query_params.get('project_id', None)
        page = self.request.query_params.get('page_id', None)
        dirs = self.request.query_params.get('directory', None)
        if project is None or project != "LNL":
            raise NotFound(detail='Invalid project id', code=404)
        if page is None:
            raise ParseError(detail='Page ID is required', code=400)
        queryset |= Notification.objects.filter(target=page)
        if dirs not in [None, '']:
            directories = dirs.split('/')
            queryset |= Notification.objects.filter(target__in=directories)
        return queryset


class EventViewSet(viewsets.ReadOnlyModelViewSet):
    """ Use this endpoint to retrieve event objects """
    serializer_class = EventSerializer
    authentication_classes = []

    # For now, do not accept new event submissions through the API (the workorder tool already does that well)
    @extend_schema(
        operation_id="Events",
        parameters=[
            OpenApiParameter('id', OpenApiTypes.INT, OpenApiParameter.QUERY, False, "Retrieve an event by its pk value"),
            OpenApiParameter('name', OpenApiTypes.STR, OpenApiParameter.QUERY, False, "Filter by event name"),
            OpenApiParameter('location', OpenApiTypes.STR, OpenApiParameter.QUERY, False, "Filter by location"),
            OpenApiParameter('start', OpenApiTypes.DATETIME, OpenApiParameter.QUERY, False, "Filter by start time"),
            OpenApiParameter('end', OpenApiTypes.DATETIME, OpenApiParameter.QUERY, False, "Filter by end time"),
        ],
        responses={
            200: EventSerializer,
            204: None
        },
        examples=[
            OpenApiExample(
                'Event',
                [{"id": 21, "event_name": "Test Event", "description": "A test event", "location": "Library",
                  "datetime_start": "2021-01-01T04:00:00.000Z", "datetime_end": "2021-01-01T06:00:00.000Z"}],
                description='If both "start" and "end" are provided, only events that fall fully within the specified '
                            'time span will be returned.',
                response_only=True
            )
        ]
    )
    def list(self, request):
        queryset = self.get_queryset()
        if queryset.count() == 0:
            content = {'204': 'No events could be found with the specified parameters'}
            return Response(content, status=status.HTTP_204_NO_CONTENT)
        serializer = EventSerializer(queryset, many=True)
        return Response(serializer.data)

    def get_queryset(self):
        queryset = Event2019.objects.filter(sensitive=False, test_event=False, approved=True).order_by('id')
        event_id = self.request.query_params.get('id', None)
        name = self.request.query_params.get('name', None)
        location_slug = self.request.query_params.get('location', None)
        start = self.request.query_params.get('start', None)
        end = self.request.query_params.get('end', None)
        default = True
        if event_id:
            return queryset.filter(pk=event_id)
        if name:
            default = False
            queryset = queryset.filter(event_name__icontains=name)
        if location_slug:
            search = Event2019.objects.none()
            for location in Location.objects.filter(Q(name__icontains=location_slug) |
                                                    Q(building__name__icontains=location_slug)):
                default = False
                search |= queryset.filter(location=location)
            queryset = search
        if start and end:
            default = False
            queryset = queryset.filter(datetime_start__lte=end, datetime_end__gte=start)
        elif start:
            default = False
            queryset = queryset.filter(datetime_start=start)
        elif end:
            default = False
            queryset = queryset.filter(datetime_end=end)

        if default is True:
            queryset = queryset.filter(datetime_end__gt=timezone.now(), reviewed=False, closed=False, cancelled=False)
        return queryset


class AttendanceViewSet(viewsets.ModelViewSet):
    serializer_class = AttendanceSerializer
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def check_required_fields(self):
        student_id = self.request.data.get('id', None)
        event_id = self.request.data.get('event', None)
        if student_id in [None, ''] or event_id in [None, '']:
            raise ParseError(detail="Bad request. One or more required keys are missing or malformed.")
        user = get_object_or_404(get_user_model(), student_id=student_id)
        event = get_object_or_404(Event2019, pk=event_id)
        if not event.approved or event.datetime_end + timezone.timedelta(hours=5) <= timezone.now() or event.closed or \
                min(event.ccinstances.values_list('setup_start', flat=True)) > timezone.now() or event.cancelled:
            raise PermissionDenied(detail="This event is not currently accepting checkin / checkout requests.")
        return user, event

    @extend_schema(
        operation_id="Crew Checkin",
        request=inline_serializer(
            'Checkin Request',
            fields={
                'id': serializers.IntegerField(),
                'event': serializers.IntegerField(),
                'checkin': serializers.DateTimeField(required=False)
            }
        ),
        responses={
            201: OpenApiResponse(description="Created"),
            400: OpenApiResponse(description="Bad request. One or more required keys are missing or malformed."),
            401: OpenApiResponse(description="Unauthorized"),
            403: OpenApiResponse(description="Event is not accepting checkin / checkout requests at this time"),
            404: OpenApiResponse(description="User or event not found")
        }
    )
    @action(['POST'], True)
    def checkin(self, request):
        """ Use this endpoint to check a user into an event as a crew member """
        user, event = self.check_required_fields()
        time = request.data.get('checkin', None)
        if time in [None, '']:
            time = str(timezone.now().replace(second=0, microsecond=0))
        if event.max_crew and event.crew_attendance.filter(active=True).values('user').count() == event.max_crew:
            raise PermissionDenied(detail="This event has reached it's crew member or occupancy limit. Please try "
                                          "again later.")
        if CrewAttendanceRecord.objects.filter(user=user, active=True).exists():
            return Response({'detail': 'This user is already checked into an event.'}, status=status.HTTP_409_CONFLICT)
        data = {
            "user": user.pk,
            "event": event.pk,
            "checkin": time,
            "active": True
        }
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        if not event.hours.filter(user=user).exists():
            event.hours.create(user=user)
        return Response(status=status.HTTP_201_CREATED)

    @extend_schema(
        operation_id="Crew Checkout",
        request=inline_serializer(
            'Checkout Request',
            fields={
                'id': serializers.IntegerField(),
                'event': serializers.IntegerField(),
                'checkout': serializers.DateTimeField(required=False)
            }
        ),
        responses={
            200: OpenApiResponse(description="Ok"),
            400: OpenApiResponse(description="Bad request. One or more required keys are missing or malformed."),
            401: OpenApiResponse(description="Unauthorized"),
            403: OpenApiResponse(description="Event is not accepting checkin / checkout requests at this time"),
            404: OpenApiResponse(description="Could not retrieve crew record. This will be returned if the user is not "
                                             "checked into the specified event or the user or event does not exist.")
        }
    )
    @action(['POST'], True)
    def checkout(self, request):
        """ Use this endpoint to check a user out of an event """
        user, event = self.check_required_fields()
        time = request.data.get('checkout', None)
        if time in [None, '']:
            time = timezone.now().replace(second=0, microsecond=0)
        record = CrewAttendanceRecord.objects.filter(user=user, event=event, active=True).first()
        if record is None:
            raise NotFound(detail="It appears this user has not yet checked in for this event")
        data = {
            "user": user.pk,
            "event": event.pk,
            "checkout": time,
            "active": False
        }
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        serializer.update(record, serializer.validated_data)
        return Response(status=status.HTTP_200_OK)


class SitemapViewSet(viewsets.ReadOnlyModelViewSet):
    """ Use this endpoint to retrieve a list of custom pages and redirect links to display in our sitemap """
    authentication_classes = []

    @extend_schema(
        operation_id="Sitemap",
        parameters=[
            OpenApiParameter('type', OpenApiTypes.STR, OpenApiParameter.QUERY, False, 'Filter by link type',
                             ['page', 'redirect']),
            OpenApiParameter('category', OpenApiTypes.STR, OpenApiParameter.QUERY, False, 'Filter by sitemap category')
        ],
        responses={
            200: OpenApiResponse([CustomPageSerializer, RedirectSerializer], description="Ok"),
            204: None
        },
        examples=[
            OpenApiExample(
                'Page', [{"title": "Example Page", "path": "example", "category": "Support"}], response_only=True
            ),
            OpenApiExample(
                'Redirect', [{"title": "Sharepoint", "path": "drive/", "category": "Redirects"}], response_only=True,
                description='**Note:** Redirects cannot be filtered by category. If "category" is set, the value of '
                            '"type" will be ignored and pages will be returned instead.'
            ),
            OpenApiExample(
                'Both',
                [{"title": "Example Page", "path": "example", "category": "Support"},
                 {"title": "Sharepoint", "path": "sharepoint/", "category": "Redirects"}],
                description='**Note:** Redirects cannot be filtered by category. If "category" is set, the value of '
                            '"type" will be ignored and only pages will be returned.'
            )
        ]
    )
    def list(self, request):
        (pages, redirects) = self.get_queryset()
        if pages.count() == 0 and redirects.count() == 0:
            content = {'204': 'No data was found for the specified parameters'}
            return Response(content, status=status.HTTP_204_NO_CONTENT)
        page_serializer = CustomPageSerializer(pages, many=True)
        redirect_serializer = RedirectSerializer(redirects, many=True)

        data = page_serializer.data + redirect_serializer.data
        return Response(data)

    def get_queryset(self):
        pages = Page.objects.filter(sitemap=True)
        redirects = ResizedRedirect.objects.filter(sitemap=True)

        link_type = self.request.query_params.get('type', None)
        category = self.request.query_params.get('category', None)

        if category not in [None, '']:
            pages = pages.filter(sitemap_category__icontains=category)
            redirects = ResizedRedirect.objects.none()
            link_type = 'page'
        if link_type == 'page':
            return pages, ResizedRedirect.objects.none()
        elif link_type == 'redirect':
            return Page.objects.none(), redirects
        return pages, redirects


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


@extend_schema(
    operation_id="Token",
    request=TokenRequestSerializer,
    responses={
        200: inline_serializer('Token', fields={'token': serializers.CharField()}),
        400: OpenApiResponse(description="Bad request. One or more required keys are missing or malformed."),
        403: OpenApiResponse(description="User has not granted proper permissions for the application or the provided "
                                         "verification code is invalid."),
        404: OpenApiResponse(description="The specified user, application, or corresponding token request could not "
                                         "be found."),
        410: OpenApiResponse(description="Verification code has expired or the number of allowed attempts has been "
                                         "exceeded.")
    }
)
@api_view(['POST'])
@authentication_classes([])
def fetch_token(request):
    """
    Use this endpoint to retrieve a user's API token. The user will need to have already granted access to your
    application and should have already received a verification code.
    """
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
            status=status.HTTP_403_FORBIDDEN
        )

    # Everything checks out
    token_request.code = 0
    token_request.attempts = 0
    token_request.save()

    token, created = Token.objects.get_or_create(user=user)

    token = {"token": token.key}

    return Response(token, status=status.HTTP_200_OK)
