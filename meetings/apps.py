import watson
from django.apps import AppConfig


class MeetingsConfig(AppConfig):
    name = 'meetings'
    verbose_name = "Meetings Module"

    def ready(self):
        Meeting = self.get_model('Meeting')
        watson.register(Meeting)


class UserSearchAdapter(watson.SearchAdapter):
    def get_title(self, obj):
        return obj.profile.fullname