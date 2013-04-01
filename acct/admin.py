from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User

from acct.models import Profile
from projection.models import Projectionist

# doodeedoo
class AcctInline(admin.StackedInline):
    model = Profile
    can_delete = False
    verbose_name_plural = 'WPI Info'

class ProjectionistInline(admin.StackedInline):
    model = Projectionist
    can_delete= False
    verbose_name_plural = "Projectionist"
# Define a new User admin
class UserAdmin(UserAdmin):
    inlines = (AcctInline, ProjectionistInline)

# Re-register UserAdmin
admin.site.unregister(User)
admin.site.register(User, UserAdmin)