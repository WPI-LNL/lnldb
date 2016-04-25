from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import PermissionDenied
from django.utils.decorators import method_decorator

from helpers.challenges import is_officer


# flake8: noqa


class LoginRequiredMixin(object):

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super(LoginRequiredMixin, self).dispatch(request,
                                                        *args, **kwargs)


class OfficerMixin(object):

    @method_decorator(user_passes_test(is_officer, ))
    def dispatch(self, request, *args, **kwargs):
        if 'Officer' not in request.user.groups:
            raise PermissionDenied
        return super(OfficerMixin, self).dispatch(request, *args, **kwargs)


class HasPermMixin(object):
    perms = []

    # assumed you have to log in to have any permissions...
    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        from django.utils import six

        if isinstance(self.perms, six.string_types):
            if not request.user.has_perm(self.perms):
                raise PermissionDenied
        elif not request.user.has_perms(self.perms):
            raise PermissionDenied

        return super(HasPermMixin, self).dispatch(request, *args, **kwargs)


class HasPermOrTestMixin(object):
    perms = []

    def user_passes_test(self, request, *args, **kwargs):
        raise NotImplementedError

    # assumed you have to log in to have any permissions...
    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        from django.utils import six

        if self.user_passes_test(request, *args, **kwargs):
            pass  # don't check for perms; we're good.
        elif isinstance(self.perms, six.string_types):
            if not request.user.has_perm(self.perms):
                raise PermissionDenied
        elif not request.user.has_perms(self.perms):
            raise PermissionDenied

        return super(HasPermOrTestMixin, self).dispatch(request,
                                                        *args, **kwargs)


class SetFormMsgMixin(object):
    msg = None

    def get_context_data(self, **kwargs):
        context = super(SetFormMsgMixin, self).get_context_data(**kwargs)
        context['msg'] = self.msg
        return context


class ConditionalFormMixin(object):

    def get_form_kwargs(self):
        kwargs = super(ConditionalFormMixin, self).get_form_kwargs()
        if kwargs is None:
            kwargs = {}
        kwargs['request_user'] = self.request.user
        return kwargs
