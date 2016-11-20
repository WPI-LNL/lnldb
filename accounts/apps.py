from django.apps import AppConfig

try:
    from watson import search
except:
    import watson as search


class AcctConfig(AppConfig):
    name = 'accounts'
    verbose_name = "Account Module"

    def ready(self):
        search.register(self.get_model("User"), UserSearchAdapter, fields=('id', 'email', 'username', 'mdc', 'phone',
                                                                           'first_name', 'last_name'))


class UserSearchAdapter(search.SearchAdapter):
    def get_title(self, obj):
        return str(obj)
