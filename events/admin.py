from events.models import *
from django.contrib import admin

#actions
def enable_show_in_wo_form(modeladmin, request, queryset):
    queryset.update(show_in_wo_form=True)
enable_show_in_wo_form.short_description = "Make locations show up in workorder form"

def disable_show_in_wo_form(modeladmin, request, queryset):
    queryset.update(show_in_wo_form=False)
disable_show_in_wo_form.short_description = "Make locations NOT show up in Workorder form"

def enable_setup_only(modeladmin,request,queryset):
    queryset.update(setup_only=True)
enable_setup_only.short_description = "Set Location as a Setup Location"
    
def disable_setup_only(modeladmin,request,queryset):
    queryset.update(setup_only=False)
disable_setup_only.short_description = "UN-Set Location as a Setup Location"

def client_archive(modeladmin,request,queryset):
    queryset.update(archived=True)
client_archive.short_description = "Set As Archived"
    
def client_unarchive(modeladmin,request,queryset):
    queryset.update(archived=False)
client_unarchive.short_description = "UN-Set As Archived"

#modeladmins
class EventBillingInline(admin.TabularInline):
    model = Billing
class EventCCInline(admin.TabularInline):
    model = EventCCInstance

class EventAttachmentInline(admin.TabularInline):
    model = EventAttachment
    
class EventHoursInline(admin.TabularInline):
    model = Hours
    
class EventAdmin(admin.ModelAdmin):
    inlines = [EventCCInline,EventHoursInline,EventAttachmentInline,EventBillingInline]
    filter_horizontal = ('crew','crew_chief','org')
    search_fields = ['event_name']
    
class OrgAdmin(admin.ModelAdmin):
    list_display = ('name','shortname','email','exec_email','user_in_charge','archived')
    list_filter = ('archived',)
    filter_horizontal = ('associated_users','associated_orgs')
    search_fields = ['name','shortname','email','exec_email']
    actions = [client_archive,client_unarchive]
    
class OTAdmin(admin.ModelAdmin):
    list_display = ('org','old_user_in_charge','new_user_in_charge','created','expiry','completed_on','completed','is_expired','uuid')

class LocAdmin(admin.ModelAdmin):
    list_filter = ('show_in_wo_form','building')
    actions = [enable_show_in_wo_form,disable_show_in_wo_form,enable_setup_only,disable_setup_only]

admin.site.register(Billing)
admin.site.register(Hours)
admin.site.register(Building)
admin.site.register(Location,LocAdmin)
admin.site.register(Event,EventAdmin)
admin.site.register(CCReport)
admin.site.register(Organization,OrgAdmin)
admin.site.register(OrganizationTransfer,OTAdmin)
admin.site.register(Extra)
admin.site.register(ExtraInstance)

admin.site.register(Lighting)
admin.site.register(Sound)
admin.site.register(Projection)

admin.site.register(Category)

admin.site.register(Service)