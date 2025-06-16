from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _

from .models import User, Officer


class MemberAdmin(UserAdmin):
    readonly_fields = ["is_superuser", "user_permissions"]

    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        (_('Personal info'), {'fields': ('first_name', 'last_name', 'nickname', 'email')}),
        (_('Permissions'), {'fields': ('is_active', 'is_staff', 'is_superuser',
                                       'groups', 'user_permissions')}),
        (_('Important dates'), {'fields': ('last_login', 'date_joined', 'away_exp')}),
        ('Other', {
            'fields': ['addr', 'mdc', 'wpibox', 'phone', 'carrier', 'class_year', 'student_id', 'locked', 'onboarded']
        })
    )

# each model can only have one associated admin page, so to get around this we create a new transparent proxy model
# using this new copy of the User model, we create a separate admin page with the ability to modify superuser status
class Superuser(User):
    class Meta:
        proxy = True

class SuperuserAdmin(admin.ModelAdmin):
    list_display = ("username", "email", "first_name", "last_name", "is_superuser")
    list_filter = ("is_staff", "is_superuser")
    filter_horizontal = ("user_permissions",)

    fields = ["is_superuser", "user_permissions"]
    
    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        if not request.user.is_superuser: return False
        
        # for safety purposes, prevent a superuser from modifying their own superuser status
        # so they can't accidentally lock themself out
        if obj and obj.pk == request.user.pk: return False

        return True

    def has_delete_permission(self, request, obj=None):
        return False

# We use the real User model here because the code here is specific to it.
# If it's swapped out, it also means that it gets its own admin to tinker with.
admin.site.register(User, MemberAdmin)
admin.site.register(Officer)

admin.site.register(Superuser, SuperuserAdmin)
