from events.models import *
from django.contrib import admin

#actions
def enable_show_in_wo_form(modeladmin, request, queryset):
    queryset.update(show_in_wo_form=True)
enable_show_in_wo_form.short_description = "Make locations show up in workorder form"

def disable_show_in_wo_form(modeladmin, request, queryset):
    queryset.update(show_in_wo_form=False)
disable_show_in_wo_form.short_description = "Make locations NOT show up in Workorder form"    

class EventAdmin(admin.ModelAdmin):
    filter_horizontal = ('crew','crew_chief','org')
    
class OrgAdmin(admin.ModelAdmin):
    list_display = ('name','shortname','email','exec_email','email_exec','email_normal','user_in_charge')
    filter_horizontal = ('associated_users','associated_orgs')
    search_fields = ['name','shortname','email','exec_email']

class LocAdmin(admin.ModelAdmin):
    list_filter = ('show_in_wo_form',)
    actions = [enable_show_in_wo_form,disable_show_in_wo_form]

admin.site.register(Billing)
admin.site.register(Location,LocAdmin)
admin.site.register(Event,EventAdmin)
admin.site.register(CCReport)
admin.site.register(Organization,OrgAdmin)
admin.site.register(Extra)
admin.site.register(ExtraInstance)

admin.site.register(Lighting)
admin.site.register(Sound)
admin.site.register(Projection)

admin.site.register(Category)

admin.site.register(Service)