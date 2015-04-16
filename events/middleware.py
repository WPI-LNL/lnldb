from django.contrib import messages


class ContactReminderMiddleware(object):
    nagtext = 'Please visit <a href="/my/acct/">My Account</a> and update your information'
    def process_view(self, request, view_func, *args, **kwargs):
        if request.user.is_authenticated():
            if not (request.user.first_name and request.user.last_name):
                # messages.add_message(request, messages.WARNING, type(view_func.func_name))
                # Don't show it on the name update page, that'd be dumb.
                if "acctupdate" not in view_func.func_name.lower() and \
                        not self.nagtext in messages.get_messages(request):
                    messages.add_message(request, messages.WARNING, self.nagtext)

        return None