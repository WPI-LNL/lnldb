from rest_framework import serializers
from events.models import OfficeHour, HourChange, Event2019, CrewAttendanceRecord
from accounts.models import User


# Create your serializers here.
class OfficerSerializer(serializers.ModelSerializer):
    def __init__(self, *args, **kwargs):
        super(OfficerSerializer, self).__init__(*args, **kwargs)

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

    img = serializers.CharField(source='img.img.url')

    class Meta:
        model = User
        fields = ('title', 'name', 'img', 'class_year')


class HourSerializer(serializers.ModelSerializer):
    officer = serializers.CharField(source='officer.title')

    class Meta:
        model = OfficeHour
        fields = ('officer', 'day', 'hour_start', 'hour_end')


class ChangeSerializer(serializers.ModelSerializer):
    officer = serializers.CharField(source='officer.title')

    class Meta:
        model = HourChange
        fields = ('officer', 'date_posted', 'expires', 'message')


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
            'message': instance.message,
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
