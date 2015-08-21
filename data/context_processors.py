from django.conf import settings


def airplane_mode(request):
    # return the value you want as a dictionnary. you may add multiple values in there.
    return {'AIRPLANE_MODE': settings.AIRPLANE_MODE}
    
def analytics(request):
    return {'GA_ID': settings.GA_ID}
