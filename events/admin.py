from events.models import *
from django.contrib import admin

class EventAdmin(admin.ModelAdmin):
    filter_horizontal = ('crew','crew_chief')
    
class OrgAdmin(admin.ModelAdmin):
    filter_horizontal = ('user_in_charge','assoicated_users','associated_orgs')

admin.site.register(Location)
admin.site.register(Event,EventAdmin)
admin.site.register(CCReport)
admin.site.register(Organization)
admin.site.register(Extra)
admin.site.register(ExtraInstance)

admin.site.register(Lighting)
admin.site.register(Sound)
admin.site.register(Projection)

admin.site.register(Category)

admin.site.register(Service)