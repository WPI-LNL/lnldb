from django.conf import settings


def flags(request):
    # return the value you want as a dictionary. you may add multiple values in there.
    return {'AIRPLANE_MODE': settings.AIRPLANE_MODE,
            'USE_CAS': settings.USE_CAS,
            'SAML2_ENABLED': settings.SAML2_ENABLED}


def analytics(request):
    return {'GA_ID': settings.GA_ID}


def revision(request):
    return {'GIT_RELEASE': settings.GIT_RELEASE[:7],
            'GIT_RELEASE_FULL': settings.GIT_RELEASE}
