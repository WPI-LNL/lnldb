from django.conf import settings
from django.contrib import messages

class ContactReminderMiddleware(object):
    def process_view(self, request, view_func, view_args, view_kwargs):
        if request.user.is_authenticated():
            if not (request.user.first_name and request.user.last_name):
                #messages.add_message(request, messages.WARNING, type(view_func.func_name))
                if "acctupdate" not in view_func.func_name.lower():# == "acctupdate" or "i18n_javascript":
                    messages.add_message(request, messages.ERROR, 'Please visit <a href="/my/acct/">My Account</a> and update your information')
            
        return None