from ajax_select import LookupChannel
from django.utils.html import escape
from django.db.models import Q

from events.models import Organization

class OrgLookup(LookupChannel):
    
    model = Organization
    
    def get_query(self,q,request):
        return Organization.objects.filter(Q(name__icontains=q)).filter(archived=False)
    
    def get_result(self,obj):
        return obj.name
    
    def format_match(self,obj):
        return self.format_item_display(obj)
        
    def format_item_display(self,obj):
        return '&nbsp;<strong>%s</strong>' % escape(obj.name)
    
    
class UserLimitedOrgLookup(LookupChannel):
    
    model = Organization
    
    def get_query(self,q,request):
        user = request.user
        return Organization.objects.filter(Q(user_in_charge=user)|Q(associated_users__in=[user.id])|Q(associated_orgs__user_in_charge=user)|Q(associated_users__in=[user.id])).filter(Q(name__icontains=q)|Q(shortname__icontains=q))
    
    def get_result(self,obj):
        return obj.name
    
    def format_match(self,obj):
        return self.format_item_display(obj)
        
    def format_item_display(self,obj):
        return '&nbsp;<strong>%s</strong>' % escape(obj.name)