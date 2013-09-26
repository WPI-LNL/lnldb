from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils.decorators import method_decorator

from helpers.challenges import is_officer

class LoginRequiredMixin(object):
    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super(LoginRequiredMixin, self).dispatch(request, *args, **kwargs)
    
class OfficerMixin(object):
    @method_decorator(user_passes_test(is_officer, login_url='/NOTOUCHING'))
    def dispatch(self, request, *args, **kwargs):
        return super(OfficerMixin, self).dispatch(request, *args, **kwargs)
    
    