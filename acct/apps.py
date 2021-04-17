import django.contrib.auth
from watson import search as watson
from django.apps import AppConfig


class AcctConfig(AppConfig):
    name = 'acct'
    verbose_name = "Account Module"

    def ready(self):
        User = django.contrib.auth.get_user_model()

        if watson.is_registered(User):
            watson.unregister(User)

        watson.register(User, UserSearchAdapter, fields=('id', 'email', 'name', 'mdc', 'phone', 'group_str',
                                                         'owns', 'orgs'))


class UserSearchAdapter(watson.SearchAdapter):
    def get_title(self, obj):
        return obj.name
