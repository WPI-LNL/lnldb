from rest_framework import serializers
from rest_framework.reverse import reverse
from drf_spectacular.utils import extend_schema_serializer, extend_schema_field, OpenApiTypes
from events.models import OfficeHour, Event2019, CrewAttendanceRecord
from accounts.models import Officer
from data.models import ResizedRedirect
from pages.models import Page
from spotify.models import Session, SpotifyUser, SongRequest
from spotify.api import get_playback_state, queue_estimate
from sats.models import Asset,AssetEvent

from .models import TokenRequest


# Create your serializers here.
@extend_schema_serializer(
    exclude_fields=['img', 'class_year']
)
class OfficerSerializer(serializers.ModelSerializer):
    def __init__(self, *args, **kwargs):
        super(OfficerSerializer, self).__init__(*args, **kwargs)

        if self.context.get('request', None):
            fields = self.context['request'].query_params.get('options')
            if fields:
                fields = fields.split(',')
                fields.append('title')
                fields.append('name')
                allowed = set(fields)
                current = set(self.fields.keys())
                for field_name in current - allowed:
                    self.fields.pop(field_name)
            else:
                self.fields.pop('img')
                self.fields.pop('class_year')

    class_year = serializers.IntegerField(source='user.class_year')
    img = serializers.SerializerMethodField()
    name = serializers.CharField(source='user.name')

    def get_img(self, obj):
        if obj.img:
            return obj.img.img.url
        else:
            return None

    class Meta:
        model = Officer
        fields = ('title', 'name', 'img', 'class_year')


class HourSerializer(serializers.ModelSerializer):
    officer = serializers.CharField(source='officer.exec_position.title')
    location = serializers.CharField(source='location.name')

    class Meta:
        model = OfficeHour
        fields = ('officer', 'day', 'location', 'hour_start', 'hour_end')


class NotificationSerializer(serializers.BaseSerializer):
    def to_representation(self, instance):
        ref_id = "LNLWN-" + str(instance.pk)
        class_type = 2
        if instance.target == "all" or instance.target == "All":
            if instance.dismissible is True and instance.format == "alert":
                class_type = 2
            else:
                class_type = 1
        elif instance.dismissible is True:
            class_type = 3
        return {
            'id': ref_id,
            'class': class_type,
            'format': instance.format,
            'type': instance.type,
            'expires': instance.expires,
            'title': instance.title,
            'message': instance.message
        }


class EventSerializer(serializers.ModelSerializer):
    location = serializers.CharField(source='location.name')
    datetime_start = serializers.DateTimeField(format="%Y-%m-%dT%H:%M:%S%z", read_only=True)
    datetime_end = serializers.DateTimeField(format="%Y-%m-%dT%H:%M:%S%z", read_only=True)

    class Meta:
        model = Event2019
        fields = ('id', 'event_name', 'description', 'location', 'datetime_start', 'datetime_end',)


class AttendanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = CrewAttendanceRecord
        fields = ('user', 'event', 'checkin', 'checkout', 'active')


class RedirectSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResizedRedirect
        fields = ('name', 'old_path')

    def to_representation(self, instance):
        path = instance.old_path
        if instance.old_path[0] == '/':
            path = instance.old_path[1:]
        return {
            'title': instance.name,
            'path': path,
            'category': 'Redirects'
        }


class CustomPageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Page
        fields = ('title', 'slug', 'sitemap_category')

    def to_representation(self, instance):
        category = 'Redirects'
        if instance.sitemap_category is not None:
            category = instance.sitemap_category
        return {
            'title': instance.title,
            'path': instance.slug,
            'category': category
        }

class AssetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Asset
        fields = ['asset_id', 'asset_display_name', 'asset_status', 'asset_position',  'asset_last_seen']
        read_only_fields = ['asset_id']

class AssetEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetEvent
        fields = ['event_id', 'event_type', 'asset_id', 'asset_position', 'event_datetime', 'user']

class SpotifyUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = SpotifyUser
        fields = ('id', 'display_name', 'spotify_id', 'personal')


class SpotifySessionReadOnlySerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='slug')
    event = EventSerializer()
    user = SpotifyUserSerializer()
    urls = serializers.SerializerMethodField()

    is_playing = serializers.SerializerMethodField()
    device = serializers.SerializerMethodField()
    current_track = serializers.SerializerMethodField()
    runtime_ms = serializers.SerializerMethodField()

    def __new__(cls, *args, **kwargs):
        if kwargs.get('many', False) is True:
            context = kwargs.get('context', {})
            context.update({'has_many': True})
            kwargs.update({'context': context})

        return super().__new__(cls, *args, **kwargs)

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super(SpotifySessionReadOnlySerializer, self).__init__(*args, **kwargs)

        many = self.context.get('has_many', False)

        # If session is inactive, do not return playback state
        if isinstance(self.instance, Session):
            event = self.instance.event
            if not event.approved or event.cancelled or event.closed or event.reviewed or \
                    not self.instance.accepting_requests:
                many = True

        if many:
            self.fields.pop('is_playing')
            self.fields.pop('device')
            self.fields.pop('current_track')
            self.fields.pop('runtime_ms')
        elif isinstance(self.instance, Session):
            self.playback_state = get_playback_state(self.instance)

        # Do not show certain fields to unprivileged users
        if not self.request or not self.request.user or not self.request.user.has_perm('spotify.view_session'):
            self.fields.pop('user')
            self.fields.pop('private')
            self.fields.pop('auto_approve')
            not many and self.fields.pop('device')

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_urls(self, obj):
        urls = {
            'request_form': reverse('spotify:request', args=[obj.slug], request=self.request),
            'qr_code': reverse('spotify:qr', args=[obj.pk], request=self.request)
        }
        return urls

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_is_playing(self, obj):
        if self.playback_state:
            return self.playback_state.get('is_playing', False)
        return False

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_device(self, obj):
        if self.playback_state:
            return self.playback_state.get('device', None)
        return None

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_current_track(self, obj):
        if self.playback_state:
            return self.playback_state.get('item', None)
        return None

    @extend_schema_field(OpenApiTypes.INT)
    def get_runtime_ms(self, obj):
        return queue_estimate(obj, True)

    class Meta:
        model = Session
        fields = ('id', 'event', 'user', 'allow_explicit', 'require_payment', 'private', 'accepting_requests',
                  'auto_approve', 'is_playing', 'runtime_ms', 'device', 'current_track', 'urls')
        depth = 1


class SpotifySessionWriteSerializer(serializers.ModelSerializer):
    event = serializers.PrimaryKeyRelatedField(
        queryset=Event2019.objects.filter(approved=True, reviewed=False, closed=False, cancelled=False),
        help_text="Primary key value of the corresponding event"
    )
    user = serializers.PrimaryKeyRelatedField(
        queryset=SpotifyUser.objects.all(), help_text="Primary key value of the Spotify account to use"
    )
    auto_approve = serializers.BooleanField(default=False, help_text="Attempt to automatically queue song requests")
    private = serializers.BooleanField(default=False, help_text="Restrict session to LNL members")

    def __init__(self, *args, **kwargs):
        partial = kwargs.get('partial', None)
        super(SpotifySessionWriteSerializer, self).__init__(*args, **kwargs)

        if partial:
            for field in self.fields:
                self.fields[field].required = False

    def update(self, instance, validated_data):
        validated_data['event'] = instance.event  # Changing this field is not permitted
        return super(SpotifySessionWriteSerializer, self).update(instance, validated_data)

    class Meta:
        model = Session
        fields = ('event', 'user', 'accepting_requests', 'allow_explicit', 'auto_approve', 'private')


class SongRequestSerializer(serializers.ModelSerializer):
    session = serializers.CharField(source='session.slug')
    queued_ts = serializers.DateTimeField(source='queued')
    requestor = serializers.SerializerMethodField()
    urls = serializers.SerializerMethodField()

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_requestor(self, obj):
        return {"name": obj.submitted_by, "email": obj.email, "phone": obj.phone}

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_urls(self, obj):
        return {'spotify_url': 'https://open.spotify.com/track/{}'.format(obj.identifier)}

    class Meta:
        model = SongRequest
        fields = ('id', 'session', 'name', 'duration', 'approved', 'queued_ts', 'requestor', 'urls')


class TokenRequestSerializer(serializers.ModelSerializer):
    APIKey = serializers.CharField(help_text="Your application's API key")
    username = serializers.CharField(source='user.username', help_text="The user's username")
    code = serializers.IntegerField(help_text="The user's verification code")

    class Meta:
        model = TokenRequest
        fields = ('code', 'APIKey', 'username')
