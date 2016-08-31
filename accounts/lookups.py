from ajax_select import LookupChannel
from django.contrib.auth import get_user_model
from django.db.models import Q
from logging import debug

from . import ldap

class UserLookup(LookupChannel):
    model = get_user_model()

    def check_auth(self, request):
        if request.user.groups.filter(Q(name="Alumni") | Q(name="Active") | Q(name="Officer")).exists():
            return True

    def get_query(self, q, request, search_ldap=True):
        qs = Q()
        for term in q.split():
            qs &=  (Q(username__icontains=term) | Q(first_name__icontains=term) | \
                    Q(nickname__icontains=term) | Q(last_name__icontains=term))
        results = get_user_model().objects.filter(qs).\
                prefetch_related('groups').distinct().all()
        if (results or search_ldap == False):
            return results

        results = ldap.search_or_create_users(q)
        if results: # call the thing again to ensure any prefetches
            return self.get_query(q, request, search_ldap=False)
        return []
        
    def format_match(self, obj):
        return self.format_item_display(obj)

    def format_item_display(self, obj):
        if obj.groups.all():
            return '&nbsp;<strong>%s</strong> <i>(%s)</i>' % \
                    (self.get_result(obj), ", ".join(map(str, obj.groups.all())))
        return '&nbsp;<strong>%s</strong>' % self.get_result(obj)


class OfficerLookup(LookupChannel):
    model = get_user_model()

    def check_auth(self, request):
        if request.user.groups.filter(Q(name="Alumni") | Q(name="Active") | Q(name="Officer")).exists():
            return True

    def get_query(self, q, request):
        for term in q.split():
            return get_user_model().objects.filter(
                    Q(username__icontains=term) | Q(first_name__icontains=term) | \
                    Q(nickname__icontains=term) | Q(last_name__icontains=term))\
                    .filter( groups__name="Officer").distinct()

    def format_match(self, obj):
        return self.format_item_display(obj)

    def format_item_display(self, obj):
        return '&nbsp;<strong>%s</strong>' % self.get_result(obj)


class MemberLookup(LookupChannel):
    model = get_user_model()

    def check_auth(self, request):
        if request.user.groups.filter(Q(name="Alumni") | Q(name="Active") | Q(name="Officer")).exists():
            return True

    def get_query(self, q, request):
        for term in q.split():
            return get_user_model().objects.filter(
                    Q(username__icontains=term) | Q(first_name__icontains=term) | \
                    Q(nickname__icontains=term) | Q(last_name__icontains=term))\
                    .filter(Q(groups__name="Alumni") | Q(groups__name="Active") | Q(groups__name="Officer")).distinct()

    def format_match(self, obj):
        return self.format_item_display(obj)

    def format_item_display(self, obj):
        return '&nbsp;<strong>%s</strong>' % self.get_result(obj)


class AssocMemberLookup(LookupChannel):
    model = get_user_model()

    def check_auth(self, request):
        if request.user.groups.filter(Q(name="Alumni") | Q(name="Active") | Q(name="Officer")).exists():
            return True

    def get_query(self, q, request):
        for term in q.split():
            return get_user_model().objects.filter(
                    Q(username__icontains=term) | Q(first_name__icontains=term) | \
                    Q(nickname__icontains=term) | Q(last_name__icontains=term))\
                    .filter(Q(groups__name="Associate") | Q(groups__name="Alumni") | \
                            Q(groups__name="Active") | Q( groups__name="Officer")) \
                    .distinct()

    def format_match(self, obj):
        return self.format_item_display(obj)

    def format_item_display(self, obj):
        return '&nbsp;<strong>%s</strong>' % self.get_result(obj)
