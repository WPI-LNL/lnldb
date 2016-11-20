from . import models


def get_level_object(level, etype):
    lo = None
    if etype == 0:  # lighting
        lo = models.Lighting.objects.get(shortname__endswith=str(level))
    elif etype == 1:  # sound
        lo = models.Sound.objects.get(shortname__endswith=str(level))
    elif etype == 2:  # projection
        lo = models.Projection.objects.get(shortname=str(level))

    return lo


def consume_event_method(emethod, methodname):
    level = emethod.pop(methodname)
    reqs = emethod.pop('requirements')

    return level, reqs


class EventManager(models.Manager):
    def consume_workorder_formwiz(self, form_fields):
        contact_fields = form_fields[0]
        # org_fields = form_fields[1]
        event_details = form_fields[2]
        event_method_details = form_fields[3:-2]
        event_schedule = form_fields[-1]

        # break things out
        contact_email = contact_fields['email']
        contact_phone = contact_fields['phone']
        person_name = contact_fields['name']

        # group stuff
        group = models.Organization.objects.get(pk=1)  # do this later

        # set levels
        lighting = None
        sound = None
        projection = None
        # set reqs
        lighting_reqs = None
        sound_reqs = None
        proj_reqs = None

        # setup buckets for our extras
        lighting_extras = []
        sound_extras = []

        event_methods = event_details['eventtypes']
        event_name = event_details['eventname']
        event_location = event_details['location']

        # event_methods
        for emethod, details in zip(event_methods, event_method_details):
            # this totally makes sense
            if emethod == 0:  # lighting
                level, lighting_reqs = consume_event_method(emethod, 'lighting')
                for k in emethod:
                    lighting_extras.append((k[2:], emethod[k]))
                lighting = get_level_object(level, 0)

            elif emethod == 1:  # sound
                level, sound_reqs = consume_event_method(emethod, 'sound')
                for k in emethod:
                    sound_extras.append((k[2:], emethod[k]))
                sound = get_level_object(level, 1)

            elif emethod == 2:  # projection
                level, proj_reqs = consume_event_method(emethod, 'projection')
                projection = get_level_object(level, 2)

        # scheduling
        setup_start = event_schedule['setup_start']
        setup_complete = event_schedule['setup_complete']
        event_start = event_schedule['event_start']
        event_end = event_schedule['event_end']

        return self.create(
            submitted_by=3,  # getthissomehow
            submitted_ip=3,  # getthissomehow
            event_name=event_name,

            person_name=person_name,
            group=group,
            contact_email=contact_email,
            contact_phone=contact_phone,

            datetime_setup_start=setup_start,
            datetime_setup_complete=setup_complete,
            datetime_start=event_start,
            datetime_end=event_end,

            location=event_location,

            lighting=lighting,
            sound=sound,
            projection=projection,

            lighting_reqs=lighting_reqs,
            sound_reqs=sound_reqs,
            proj_reqs=proj_reqs,

        )
