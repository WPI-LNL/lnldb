from ajax_select import LookupChannel
from django.utils.html import escape
from django.db.models import Q
from django.contrib.auth.models import User


class UserLookup(LookupChannel):
    model = User

    def check_auth(self, request):
        if request.user.groups.filter(Q(name="Alumni") | Q(name="Active") | Q(name="Officer")).exists():
            return True

    def get_query(self, q, request):
        for term in q.split():
            return User.objects.filter(
                Q(username__icontains=term) | Q(first_name__icontains=term) | Q(last_name__icontains=term))

    def get_result(self, obj):
        return obj.first_name + " " + obj.last_name

    def format_match(self, obj):
        return self.format_item_display(obj)

    def format_item_display(self, obj):
        return '&nbsp;<strong>%s</strong>' % escape(obj.first_name + " " + obj.last_name)


class OfficerLookup(LookupChannel):
    model = User

    def check_auth(self, request):
        if request.user.groups.filter(Q(name="Alumni") | Q(name="Active") | Q(name="Officer")).exists():
            return True

    def get_query(self, q, request):
        for term in q.split():
            return User.objects.filter(
                Q(username__icontains=term) | Q(first_name__icontains=term) | Q(last_name__icontains=term)).filter(
                groups__name="Officer").distinct()

    def get_result(self, obj):
        return obj.first_name + " " + obj.last_name

    def format_match(self, obj):
        return self.format_item_display(obj)

    def format_item_display(self, obj):
        return '&nbsp;<strong>%s</strong>' % escape(obj.first_name + " " + obj.last_name)


class MemberLookup(LookupChannel):
    model = User

    def check_auth(self, request):
        if request.user.groups.filter(Q(name="Alumni") | Q(name="Active") | Q(name="Officer")).exists():
            return True

    def get_query(self, q, request):
        for term in q.split():
            return User.objects.filter(
                Q(username__icontains=term) | Q(first_name__icontains=term) | Q(last_name__icontains=term)).filter(
                Q(groups__name="Alumni") | Q(groups__name="Active") | Q(groups__name="Officer")).distinct()

    def get_result(self, obj):
        return obj.first_name + " " + obj.last_name

    def format_match(self, obj):
        return self.format_item_display(obj)

    def format_item_display(self, obj):
        return '&nbsp;<strong>%s</strong>' % escape(obj.first_name + " " + obj.last_name)


class AssocMemberLookup(LookupChannel):
    model = User

    def check_auth(self, request):
        if request.user.groups.filter(Q(name="Alumni") | Q(name="Active") | Q(name="Officer")).exists():
            return True

    def get_query(self, q, request):
        for term in q.split():
            return User.objects.filter(
                Q(username__icontains=term) | Q(first_name__icontains=term) | Q(last_name__icontains=term)).filter(
                Q(groups__name="Associate") | Q(groups__name="Alumni") | Q(groups__name="Active") | Q(
                    groups__name="Officer")).distinct()

    def get_result(self, obj):
        return obj.first_name + " " + obj.last_name

    def format_match(self, obj):
        return self.format_item_display(obj)

    def format_item_display(self, obj):
        return '&nbsp;<strong>%s</strong>' % escape(obj.first_name + " " + obj.last_name)