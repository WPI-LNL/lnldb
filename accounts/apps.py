import watson
from django.apps import AppConfig


class AcctConfig(AppConfig):
    name = 'accounts'
    verbose_name = "Account Module"

    def ready(self):
        watson.register(self.get_model("User"), UserSearchAdapter, fields=('id', 'email', 'username', 'mdc', 'phone',
                                                                           'first_name', 'last_name'))


class UserSearchAdapter(watson.SearchAdapter):
    def get_title(self, obj):
        return str(obj)
