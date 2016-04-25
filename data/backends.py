# A little wrapper so that object permission checks are overridden by
# global permissions.


class PermissionShimBackend(object):
    supports_object_permissions = True

    def has_perm(self, user, perm, obj=None):
        if obj is not None:
            return user.has_perm(perm)
        else:
            return False

    def has_module_perms(self, user_obj, app_label):
        return False

    def authenticate(self, username, password):
        return None
