from rest_framework import serializers
from events.models import OfficeHour, HourChange
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
        id = "LNLWN-" + str(instance.pk)
        classType = 2
        if instance.target == "all" or instance.target == "All":
            if instance.dismissible is True and instance.format == "alert":
                classType = 2
            else:
                classType = 1
        elif instance.dismissible is True:
            classType = 3
        return {
            'id': id,
            'format': instance.format,
            'type': instance.type,
            'class': classType,
            'title': instance.title,
            'message': instance.message,
            'expires': instance.expires
        }
