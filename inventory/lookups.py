from ajax_select import LookupChannel
from .models import *
from django.utils.html import escape


class ClassLookup(LookupChannel):
    model = EquipmentClass

    def check_auth(self, request):
        return request.user.has_perm('inventory.view_equipment')

    def get_query(self, q, request):
        return EquipmentClass.objects.filter(name__contains=q).all()

    def get_result(self, obj):
        return obj.name

    def format_match(self, obj):
        return self.format_item_display(obj)

    def format_item_display(self, obj):
        long_cat = ">".join(map(lambda cat: cat.name,
                                obj.category.get_ancestors_inclusive.all()))
        return ' <span class="text-muted">[x%02d]</span> <strong>%s</strong> (%s)' % (obj.items.count(),
                                                                                      escape(obj.name),
                                                                                      escape(long_cat))
