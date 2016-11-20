from ajax_select import LookupChannel
from django.db.models import Q
from django.utils.html import escape

from . import models


class ClassLookup(LookupChannel):
    model = models.EquipmentClass

    def check_auth(self, request):
        return request.user.has_perm('inventory.view_equipment')

    def get_query(self, q, request):
        filters = Q(name__icontains=q)

        if q.isdigit():
            filters |= Q(items__barcode=int(q))

        return models.EquipmentClass.objects.filter(filters).all()

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


class ContainerLookup(LookupChannel):
    model = models.EquipmentItem

    def check_auth(self, request):
        return request.user.has_perm('inventory.view_equipment')

    def get_query(self, q, request):
        filters = Q(item_type__name__icontains=q)

        if q.isdigit():
            filters |= Q(barcode=int(q))
            filters |= Q(pk=int(q))

        filters &= Q(item_type__holds_items=True)

        return self.model.objects.filter(filters).all()

    def get_result(self, obj):
        return str(obj)

    def format_match(self, obj):
        return self.format_item_display(obj)

    def format_item_display(self, obj):
        long_cat = ">".join(map(lambda cat: cat.name,
                                obj.item_type.category.get_ancestors_inclusive.all()))
        return ' <span class="text-muted">[%d inside]</span> <strong>%s</strong> (%s)' % (obj.get_children().count(),
                                                                                          escape(obj),
                                                                                          escape(long_cat))
