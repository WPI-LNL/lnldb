import django.contrib.auth
from watson import search as watson
from django.apps import AppConfig


class AcctConfig(AppConfig):
    name = 'acct'
    verbose_name = "Account Module"

    def ready(self):
        User = django.contrib.auth.get_user_model()

        watson.register(User, UserSearchAdapter, fields=('id', 'email',
                                                         'profile__fullname',
                                                         'profile__mdc',
                                                         'profile__phone',
                                                         'profile__group_str',
                                                         'profile__owns',
                                                         'profile__orgs'))


class UserSearchAdapter(watson.SearchAdapter):
    def get_title(self, obj):
        return obj.profile.fullname
