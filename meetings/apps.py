import watson
from django.apps import AppConfig


class MeetingsConfig(AppConfig):
    name = 'meetings'
    verbose_name = "Meetings Module"

    def ready(self):
        # noinspection PyPep8Naming
        Meeting = self.get_model('Meeting')
        watson.register(Meeting)
