from django.contrib import messages
from django.utils.safestring import mark_safe


class ContactReminderMiddleware(object):
    nagtext = mark_safe('Please visit <a href="/my/acct/">My Account</a> and update your information')

    def process_view(self, request, view_func, *args, **kwargs):
        if request.user.is_authenticated():
            if not (request.user.first_name and request.user.last_name):
                # messages.add_message(request, messages.WARNING, type(view_func.func_name))
                # Don't show it on the name update page, that'd be dumb.
                if hasattr(view_func, "func_name") and "acctupdate" not in view_func.func_name.lower() and \
                        self.nagtext not in messages.get_messages(request):
                    messages.add_message(request, messages.WARNING, self.nagtext)

        return None