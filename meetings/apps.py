from django.apps import AppConfig

try:
    from watson import search
except:
    import watson as search


class MeetingsConfig(AppConfig):
    name = 'meetings'
    verbose_name = "Meetings Module"

    def ready(self):
        # noinspection PyPep8Naming
        Meeting = self.get_model('Meeting')
        search.register(Meeting)
