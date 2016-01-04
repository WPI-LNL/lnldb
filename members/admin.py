from django.contrib import admin
from members.models import StatusChange
from django.contrib.auth import get_user_model


class SCAdmin(admin.ModelAdmin):
    list_display = ["member", "group_list", "date"]


admin.site.register(StatusChange, SCAdmin)


# to add last login to the django admin site
from django.contrib.auth.admin import UserAdmin

UserAdmin.list_display += ('last_login',)
UserAdmin.list_filter += ('last_login',)

# admin.site.unregister(get_user_model())
# admin.site.register(get_user_model(), UserAdmin)