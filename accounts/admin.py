from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import ugettext_lazy as _

from .models import User


class MemberAdmin(UserAdmin):
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        (_('Personal info'), {'fields': ('first_name', 'last_name', 'nickname', 'email')}),
        (_('Permissions'), {'fields': ('is_active', 'is_staff', 'is_superuser',
                                       'groups', 'user_permissions')}),
        (_('Important dates'), {'fields': ('last_login', 'date_joined', 'away_exp')}),
        ('Other', {'fields': ['addr', 'mdc', 'wpibox', 'phone', 'carrier', 'class_year', 'student_id', 'locked']})
    )


# We use the real User model here because the code here is specific to it.
# If it's swapped out, it also means that it gets its own admin to tinker with.
admin.site.register(User, MemberAdmin)
