from ajax_select import LookupChannel
from django.utils.html import escape
from django.db.models import Q

from events.models import Organization, Fund


class OrgLookup(LookupChannel):
    model = Organization

    def check_auth(self, request):
        return request.user.is_authenticated()

    def get_query(self, q, request):
        return Organization.objects.filter(Q(name__icontains=q) | Q(
            shortname__icontains=q)).filter(archived=False) .distinct()

    def get_result(self, obj):
        return obj.name

    def format_match(self, obj):
        return self.format_item_display(obj)

    def format_item_display(self, obj):
        return '&nbsp;<strong>%s</strong>' % escape(obj.name)


class FundLookup(LookupChannel):
    model = Fund

    def check_auth(self, request):
        return request.user.is_authenticated()

    def get_query(self, q, request):
        return Fund.objects.filter(Q(name__icontains=q) |
                                   Q(account__icontains=q) |
                                   Q(organization__icontains=q) |
                                   Q(fund__icontains=q)).distinct()

    def get_result(self, obj):
        return obj.id

    def format_match(self, obj):
        return self.format_item_display(obj)

    def format_item_display(self, obj):
        return '&nbsp;<strong>%s</strong>' % escape(str(obj))


class FundLookupLimited(LookupChannel):
    model = Fund

    def check_auth(self, request):
        return request.user.is_authenticated()

    def get_query(self, q, request):
        user = request.user
        return Fund.objects.filter(
            Q(
                orgfunds__user_in_charge=user) | Q(
                orgfunds__associated_users__in=[
                    user.id]) | Q(
                    orgfunds__associated_orgs__user_in_charge=user) | Q(
                        orgfunds__associated_users__in=[
                            user.id])) .filter(
                                Q(
                                    name__icontains=q) | Q(
                                        account__icontains=q) | Q(
                                            organization__icontains=q) | Q(
                                                fund__icontains=q)) .distinct()

    def get_result(self, obj):
        return obj.id

    def format_match(self, obj):
        return self.format_item_display(obj)

    def format_item_display(self, obj):
        return '&nbsp;<strong>%s</strong>' % escape(str(obj))


class UserLimitedOrgLookup(LookupChannel):
    model = Organization

    def check_auth(self, request):
        return True

    def get_query(self, q, request):
        user = request.user
        return Organization.objects.filter(
            Q(
                user_in_charge=user) | Q(
                associated_users__in=[
                    user.id]) | Q(
                    associated_orgs__user_in_charge=user) | Q(
                        associated_users__in=[
                            user.id]) | Q(
                                shortname="nl")).filter(
                                    Q(
                                        name__icontains=q) | Q(
                                            shortname__icontains=q))

    def get_result(self, obj):
        return obj.name

    def format_match(self, obj):
        return self.format_item_display(obj)

    def format_item_display(self, obj):
        return '&nbsp;<strong>%s</strong>' % escape(obj.name)
