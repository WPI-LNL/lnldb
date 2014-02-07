from ajax_select import LookupChannel
from django.utils.html import escape
from django.db.models import Q
from django.contrib.auth.models import User

class UserLookup(LookupChannel):
    
    model = User
    
    def get_query(self,q,request):
        return User.objects.filter(Q(username__icontains=q)|Q(first_name__icontains=q)|Q(last_name__icontains=q))
    
    def get_result(self,obj):
        return obj.first_name + " " + obj.last_name
    
    def format_match(self,obj):
        return self.format_item_display(obj)
        
    def format_item_display(self,obj):
        return '&nbsp;<strong>%s</strong>' % escape(obj.first_name + " " + obj.last_name)


class MemberLookup(LookupChannel):
    
    model = User
    
    def get_query(self,q,request):
        return User.objects.filter(Q(username__icontains=q)|Q(first_name__icontains=q)|Q(last_name__icontains=q)).filter(Q(groups__name="Alumni")|Q(groups__name="Active")|Q(groups__name="Officer")).distinct()
    
    def get_result(self,obj):
        return obj.first_name + " " + obj.last_name
    
    def format_match(self,obj):
        return self.format_item_display(obj)
        
    def format_item_display(self,obj):
        return '&nbsp;<strong>%s</strong>' % escape(obj.first_name + " " + obj.last_name)


class AssocMemberLookup(LookupChannel):
    
    model = User
    
    def get_query(self,q,request):
        return User.objects.filter(Q(username__icontains=q)|Q(first_name__icontains=q)|Q(last_name__icontains=q)).filter(Q(groups__name="Associate")|Q(groups__name="Alumni")|Q(groups__name="Active")|Q(groups__name="Officer")).distinct()
    
    def get_result(self,obj):
        return obj.first_name + " " + obj.last_name
    
    def format_match(self,obj):
        return self.format_item_display(obj)
        
    def format_item_display(self,obj):
        return '&nbsp;<strong>%s</strong>' % escape(obj.first_name + " " + obj.last_name)