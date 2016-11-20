from django.apps import AppConfig
try:
    from watson import search
except:
    import watson as search

__author__ = 'Jake'


class EventsConfig(AppConfig):
    name = 'events'
    verbose_name = "Events Module"

    def ready(self):
        Event = self.get_model('Event')
        CCReport = self.get_model('CCReport')
        Fund = self.get_model('Fund')
        Organization = self.get_model('Organization')

        search.register(Event, store=('id',
                                      'datetime_nice',
                                      'description',
                                      'location__name',
                                      'org',
                                      'status',
                                      'short_services'))
        search.register(Organization)
        search.register(CCReport)
        search.register(Fund)
        from . import signals # NOQA
