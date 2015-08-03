from events.models import *
from django.contrib import admin


# actions
import reversion


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
    model = Billing


class EventCCInline(admin.TabularInline):
    model = EventCCInstance


class EventAttachmentInline(admin.TabularInline):
    model = EventAttachment


class EventHoursInline(admin.TabularInline):
    model = Hours


class EventAdmin(reversion.VersionAdmin):
    inlines = [EventCCInline, EventHoursInline, EventAttachmentInline, EventBillingInline]
    filter_horizontal = ('crew', 'crew_chief', 'org')
    search_fields = ['event_name']
    readonly_fields = ['submitted_on']


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


class OrgAdmin(reversion.VersionAdmin):
    list_display = ('name', 'shortname', 'email', 'exec_email', 'user_in_charge', 'archived')
    list_filter = ('archived',)
    filter_horizontal = ('accounts', 'associated_users', 'associated_orgs')
    search_fields = ['name', 'shortname', 'email', 'exec_email']
    actions = [client_archive, client_unarchive]


class OTAdmin(admin.ModelAdmin):
    list_display = (
        'org', 'old_user_in_charge', 'new_user_in_charge', 'created', 'expiry', 'completed_on', 'completed',
        'is_expired',
        'uuid')


class LocAdmin(admin.ModelAdmin):
    list_filter = ('show_in_wo_form', 'building', 'setup_only')
    actions = [enable_show_in_wo_form, disable_show_in_wo_form, enable_setup_only, disable_setup_only]


class ExtraAdmin(admin.ModelAdmin):
    list_display = ('name', 'cost', 'category', 'disappear', 'checkbox')
    list_filter = ('category', 'disappear', 'checkbox')


class FundAdmin(admin.ModelAdmin):
    search_fields = ['name', 'notes', 'fund', 'account', 'organization']


admin.site.register(Fund, FundAdmin)
admin.site.register(Billing)
admin.site.register(Hours)
admin.site.register(Building)
admin.site.register(Location, LocAdmin)
admin.site.register(Event, EventAdmin)
admin.site.register(CCReport)
admin.site.register(Organization, OrgAdmin)
admin.site.register(OrganizationTransfer, OTAdmin)
admin.site.register(Extra, ExtraAdmin)
admin.site.register(ExtraInstance)

admin.site.register(Lighting)
admin.site.register(Sound)
admin.site.register(Projection)

admin.site.register(Category)

admin.site.register(Service)