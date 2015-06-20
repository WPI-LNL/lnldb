import watson

__author__ = 'Jake'

from django.apps import AppConfig


class EventsConfig(AppConfig):
    name = 'events'
    verbose_name = "Events Module"

    def ready(self):
        Event = self.get_model('Event')
        CCReport = self.get_model('CCReport')
        Fund = self.get_model('Fund')
        Organization = self.get_model('Organization')

        watson.register(Event, store=('id',
                                      'datetime_nice',
                                      'description',
                                      'location__name',
                                      'org',
                                      'status',
                                      'short_services'))
        watson.register(Organization)
        watson.register(CCReport)
        watson.register(Fund)
