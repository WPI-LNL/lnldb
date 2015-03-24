from django.contrib import admin
from members.models import StatusChange


class SCAdmin(admin.ModelAdmin):
    list_display = ["member", "group_list", "date"]


admin.site.register(StatusChange, SCAdmin)


# to add last login to the django admin site
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User

UserAdmin.list_display += ('last_login',)
UserAdmin.list_filter += ('last_login',)

admin.site.unregister(User)
admin.site.register(User, UserAdmin)