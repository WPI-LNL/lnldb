from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.conf import settings
from django.contrib.auth import get_user_model

from acct.models import Profile
from acct.models import Orgsync_User, Orgsync_Org, Orgsync_OrgCat
from projection.models import Projectionist


# doodeedoo
class AcctInline(admin.StackedInline):
    model = Profile
    can_delete = False
    verbose_name_plural = 'WPI Info'


class ProjectionistInline(admin.StackedInline):
    model = Projectionist
    can_delete = False
    verbose_name_plural = "Projectionist"


# Define a new User admin
class UserAdmin(UserAdmin):
    inlines = (AcctInline, ProjectionistInline)


class OOAdmin(admin.ModelAdmin):
    search_fields = ('name', 'orgsync_id')

# Re-register UserAdmin
# admin.site.unregister(get_user_model())
# admin.site.register(get_user_model(), UserAdmin)

admin.site.register(Orgsync_User)
admin.site.register(Orgsync_Org, OOAdmin)
admin.site.register(Orgsync_OrgCat)