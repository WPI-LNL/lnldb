from django.conf.urls import include, url

from ..views import list as list_views


def generate_date_patterns(func, name):
    return include([
        url(r'^$', func, name=name),
        url(r'^(?P<start>\d{4}-\d{2}-\d{2})/$', func, name=name),
        url(r'^(?P<start>\d{4}-\d{2}-\d{2})/(?P<end>\d{4}-\d{2}-\d{2})/$', func, name=name),
    ])


# prefix: /db/events
urlpatterns = [
    # list views
    url(r'^upcoming/', generate_date_patterns(list_views.upcoming, name="upcoming")),
    url(r'^findchief/', generate_date_patterns(list_views.findchief, name="findchief")),
    url(r'^incoming/', generate_date_patterns(list_views.incoming, name="incoming")),
    url(r'^open/', generate_date_patterns(list_views.openworkorders, name="open")),
    url(r'^unreviewed/', generate_date_patterns(list_views.unreviewed, name="unreviewed")),
    url(r'^unbilled/', generate_date_patterns(list_views.unbilled, name="unbilled")),
    url(r'^unbilledsemester/', generate_date_patterns(list_views.unbilled_semester, name="unbilled-semester")),
    url(r'^paid/', generate_date_patterns(list_views.paid, name="paid")),
    url(r'^unpaid/', generate_date_patterns(list_views.unpaid, name="unpaid")),
    url(r'^closed/', generate_date_patterns(list_views.closed, name="closed")),
]
