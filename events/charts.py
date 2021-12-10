import datetime

from django.db.models import Avg, Q
from django.utils import timezone
from jchart import Chart
from jchart.config import Axes, DataSet

from events.models import BaseEvent

class SurveyVpChart(Chart):
    chart_type = 'line'
    scales = {
        'xAxes': [Axes(type='time', position='bottom')],
        'yAxes': [Axes(ticks={'min': 0, 'max': 4})],
    }

    def get_datasets(self, *args, **kwargs):
        now = timezone.now()
        year_ago = now - datetime.timedelta(days=365)
        events = BaseEvent.objects \
            .filter(approved=True, datetime_start__gte=year_ago, datetime_end__lt=now) \
            .filter(surveys__isnull=False) \
            .distinct()
        data_communication_responsiveness = []
        for event in events:
            data = event.surveys.aggregate(
                Avg('communication_responsiveness'),
            )
            if data['communication_responsiveness__avg'] >= 0:
                data_communication_responsiveness.append({'x': event.datetime_start.isoformat(), 'y': data['communication_responsiveness__avg']})
        options = {'type': 'line', 'fill': False, 'lineTension': 0}
        return [
            DataSet(label='Communication responsiveness', data=data_communication_responsiveness, color=(193, 37, 82), **options),
        ]


class SurveyCrewChart(Chart):
    chart_type = 'line'
    scales = {
        'xAxes': [Axes(type='time', position='bottom')],
        'yAxes': [Axes(ticks={'min': 0, 'max': 4})],
    }

    def get_datasets(self, *args, **kwargs):
        now = timezone.now()
        year_ago = now - datetime.timedelta(days=365)
        events = BaseEvent.objects \
            .filter(approved=True, datetime_start__gte=year_ago, datetime_end__lt=now) \
            .filter(surveys__isnull=False) \
            .distinct()
        data_lighting_quality = []
        data_sound_quality = []
        data_setup_on_time = []
        data_crew_respectfulness = []
        data_crew_preparedness = []
        data_crew_knowledgeability = []
        for event in events:
            data = event.surveys.aggregate(
                Avg('lighting_quality'),
                Avg('sound_quality'),
                Avg('setup_on_time'),
                Avg('crew_respectfulness'),
                # Avg('crew_preparedness'),
                # Avg('crew_knowledgeability'),
            )
            if data['lighting_quality__avg'] >= 0:
                data_lighting_quality.append({'x': event.datetime_start.isoformat(), 'y': data['lighting_quality__avg']})
            if data['sound_quality__avg'] >= 0:
                data_sound_quality.append({'x': event.datetime_start.isoformat(), 'y': data['sound_quality__avg']})
            if data['setup_on_time__avg'] >= 0:
                data_setup_on_time.append({'x': event.datetime_start.isoformat(), 'y': data['setup_on_time__avg']})
            if data['crew_respectfulness__avg'] >= 0:
                data_crew_respectfulness.append({'x': event.datetime_start.isoformat(), 'y': data['crew_respectfulness__avg']})
            # data_crew_preparedness.append({'x': event.datetime_start.isoformat(), 'y': data['crew_preparedness__avg']})
            # data_crew_knowledgeability.append({'x': event.datetime_start.isoformat(), 'y': data['crew_knowledgeability__avg']})
        options = {'type': 'line', 'fill': False, 'lineTension': 0}
        return [
            DataSet(label='Lighting quality', data=data_lighting_quality, color=(193, 37, 82), **options),
            DataSet(label='Sound quality', data=data_sound_quality, color=(255, 102, 0), **options),
            DataSet(label='Setup on time', data=data_setup_on_time, color=(245, 199, 0), **options),
            DataSet(label='Crew was helpful', data=data_crew_respectfulness, color=(106, 150, 31), **options),
            # DataSet(label='Crew preparedness', data=data_crew_preparedness, color=(0, 133, 53), **options),
            # DataSet(label='Crew knowledgeability', data=data_crew_knowledgeability, color=(110, 45, 214), **options),
        ]


class SurveyPricelistChart(Chart):
    chart_type = 'line'
    scales = {
        'xAxes': [Axes(type='time', position='bottom')],
        'yAxes': [Axes(ticks={'min': 0, 'max': 4})],
    }

    def get_datasets(self, *args, **kwargs):
        now = timezone.now()
        year_ago = now - datetime.timedelta(days=365)
        events = BaseEvent.objects \
            .filter(approved=True, datetime_start__gte=year_ago, datetime_end__lt=now) \
            .filter(surveys__isnull=False) \
            .distinct()
        data_pricelist_ux = []
        data_quote_as_expected = []
        data_price_appropriate = []
        for event in events:
            data = event.surveys.aggregate(
                Avg('pricelist_ux'),
                # Avg('quote_as_expected'),
                Avg('price_appropriate'),
            )
            if data['pricelist_ux__avg'] >= 0:
                data_pricelist_ux.append({'x': event.datetime_start.isoformat(), 'y': data['pricelist_ux__avg']})
            # data_quote_as_expected.append({'x': event.datetime_start.isoformat(), 'y': data['quote_as_expected__avg']})
            if data['price_appropriate__avg'] >= 0:
                data_price_appropriate.append({'x': event.datetime_start.isoformat(), 'y': data['price_appropriate__avg']})
        options = {'type': 'line', 'fill': False, 'lineTension': 0}
        return [
            DataSet(label='Pricelist UX', data=data_pricelist_ux, color=(193, 37, 82), **options),
            # DataSet(label='Quote as expected', data=data_quote_as_expected, color=(245, 199, 0), **options),
            DataSet(label='Price appropriate', data=data_price_appropriate, color=(0, 133, 53), **options),
        ]


class SurveyLnlChart(Chart):
    chart_type = 'line'
    scales = {
        'xAxes': [Axes(type='time', position='bottom')],
        'yAxes': [Axes(ticks={'min': 0, 'max': 4})],
    }

    def get_datasets(self, *args, **kwargs):
        now = timezone.now()
        year_ago = now - datetime.timedelta(days=365)
        events = BaseEvent.objects \
            .filter(approved=True, datetime_start__gte=year_ago, datetime_end__lt=now) \
            .filter(surveys__isnull=False) \
            .distinct()
        data_services_quality = []
        data_customer_would_return = []
        for event in events:
            data = event.surveys.aggregate(
                Avg('services_quality'),
                Avg('customer_would_return'),
            )
            if data['services_quality__avg'] >= 0:
                data_services_quality.append({'x': event.datetime_start.isoformat(), 'y': data['services_quality__avg']})
            if data['customer_would_return__avg'] >= 0:
                data_customer_would_return.append({'x': event.datetime_start.isoformat(), 'y': data['customer_would_return__avg']})
        options = {'type': 'line', 'fill': False, 'lineTension': 0}
        return [
            DataSet(label='Services quality', data=data_services_quality, color=(193, 37, 82), **options),
            DataSet(label='Customer would return', data=data_customer_would_return, color=(106, 150, 31), **options),
        ]
