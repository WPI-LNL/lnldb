from rest_framework import serializers
from drf_spectacular.utils import extend_schema_serializer
from events.models import OfficeHour, Event2019, CrewAttendanceRecord
from accounts.models import Officer
from data.models import ResizedRedirect
from pages.models import Page

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


class TokenRequestSerializer(serializers.ModelSerializer):
    APIKey = serializers.CharField(help_text="Your application's API key")
    username = serializers.CharField(source='user.username', help_text="The user's username")
    code = serializers.IntegerField(help_text="The user's verification code")

    class Meta:
        model = TokenRequest
        fields = ('code', 'APIKey', 'username')
