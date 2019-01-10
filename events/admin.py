from django.contrib import admin
from polymorphic.admin import PolymorphicChildModelAdmin, PolymorphicParentModelAdmin
from reversion.admin import VersionAdmin

from . import models


def enable_show_in_wo_form(modeladmin, request, queryset):
    queryset.update(show_in_wo_form=True)


enable_show_in_wo_form.short_description = "Make locations show up in workorder form"


def disable_show_in_wo_form(modeladmin, request, queryset):
    queryset.update(show_in_wo_form=False)


disable_show_in_wo_form.short_description = "Make locations NOT show up in Workorder form"


def enable_setup_only(modeladmin, request, queryset):
    queryset.update(setup_only=True)


enable_setup_only.short_description = "Set Location as a Setup Location"


def disable_setup_only(modeladmin, request, queryset):
    queryset.update(setup_only=False)


disable_setup_only.short_description = "UN-Set Location as a Setup Location"


def client_archive(modeladmin, request, queryset):
    queryset.update(archived=True)


client_archive.short_description = "Set As Archived"


def client_unarchive(modeladmin, request, queryset):
    queryset.update(archived=False)


client_unarchive.short_description = "UN-Set As Archived"


# modeladmins
class EventBillingInline(admin.TabularInline):
    model = models.Billing


class EventCCInline(admin.TabularInline):
    model = models.EventCCInstance


class EventAttachmentInline(admin.TabularInline):
    model = models.EventAttachment


class EventHoursInline(admin.TabularInline):
    model = models.Hours

class ServiceInstanceInline(admin.TabularInline):
    model = models.ServiceInstance

class EventAdmin(PolymorphicChildModelAdmin, VersionAdmin):
    inlines = [EventCCInline, EventHoursInline, EventAttachmentInline, EventBillingInline]
    filter_horizontal = ('crew', 'crew_chief', 'org')
    search_fields = ['event_name']
    readonly_fields = ['submitted_on']

class Event2019Admin(PolymorphicChildModelAdmin, VersionAdmin):
    inlines = [ServiceInstanceInline, EventCCInline, EventHoursInline, EventAttachmentInline, EventBillingInline]
    filter_horizontal = ('org',)
    search_fields = ['event_name']
    readonly_fields = ['submitted_on']

class BaseEventAdmin(VersionAdmin, PolymorphicParentModelAdmin):
    child_models = models.Event, models.Event2019

fieldsets = (
    ("Submitter Information", {
        'fields': ('submitted_by', 'submitted_ip', 'submitted_on')
    }),
    ('Event And Contact Information', {
        'fields': ('event_name', 'description', 'internal_notes', 'contact', 'org', 'billing_org')
    }),
    ('Scheduling & Location', {
        'fields': ('datetime_setup_complete', 'datetime_start', 'datetime_end', 'location')
    }),
    ('Services', {
        'fields': ('lighting', 'lighting_reqs', 'sound', 'sound_reqs', 'projection', 'proj_reqs', 'otherservices',
                   'otherservice_reqs')
    }),
    ('Status Flags', {
        'fields': ('billed_by_semester',
                   ('approved', 'approved_on', 'approved_by'),
                   ('reviewed', 'reviewed_on', 'reviewed_by'),
                   ('closed', 'closed_on', 'closed_by'),
                   ('cancelled', 'cancelled_on', 'cancelled_by'),
                   'cancelled_reason')
    }),
    ('OLD STYLE DEPRECATED FIELDS', {
        'classes': ('collapse',),
        'fields': ('datetime_setup_start',  # part of a CrewChiefInstance object
                   'setup_location',  # part of a CrewChiefInstance object
                   'payment_amount')  # Billing Object
    }),
)


class OrgAdmin(VersionAdmin):
    list_display = ('name', 'shortname', 'email', 'exec_email', 'user_in_charge', 'archived')
    list_filter = ('archived',)
    filter_horizontal = ('accounts', 'associated_users', 'associated_orgs')
    search_fields = ['name', 'shortname', 'email', 'exec_email']
    actions = [client_archive, client_unarchive]


class OTAdmin(admin.ModelAdmin):
    list_display = (
        'org', 'initiator', 'old_user_in_charge', 'new_user_in_charge', 'created', 'expiry',
        'completed_on', 'completed', 'is_expired', 'uuid')


class LocAdmin(admin.ModelAdmin):
    list_filter = ('show_in_wo_form', 'building', 'setup_only')
    actions = [enable_show_in_wo_form, disable_show_in_wo_form, enable_setup_only, disable_setup_only]


class ExtraAdmin(admin.ModelAdmin):
    list_display = ('name', 'cost', 'category', 'disappear', 'checkbox')
    list_filter = ('category', 'disappear', 'checkbox')


class FundAdmin(admin.ModelAdmin):
    search_fields = ['name', 'notes', 'fund', 'account', 'organization']


admin.site.register(models.Fund, FundAdmin)
admin.site.register(models.Billing)
admin.site.register(models.Hours)
admin.site.register(models.Building)
admin.site.register(models.Location, LocAdmin)
admin.site.register(models.Event, EventAdmin)
admin.site.register(models.Event2019, Event2019Admin)
admin.site.register(models.BaseEvent, BaseEventAdmin)
admin.site.register(models.CCReport)
admin.site.register(models.Organization, OrgAdmin)
admin.site.register(models.OrganizationTransfer, OTAdmin)
admin.site.register(models.Extra, ExtraAdmin)
admin.site.register(models.ExtraInstance)

admin.site.register(models.Lighting)
admin.site.register(models.Sound)
admin.site.register(models.Projection)

admin.site.register(models.Category)

admin.site.register(models.Service)
