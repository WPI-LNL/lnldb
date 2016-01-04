from django.db import models
from django.conf import settings

# Create your models here.
import logging
import datetime

from django.db.models import Q
from django.core.urlresolvers import reverse

from django.utils.functional import cached_property
from mptt.fields import TreeForeignKey
from mptt.managers import TreeManager
from mptt.models import MPTTModel
from events.models import Location

GLOBAL_LOC_DEFAULT = {'name': "Office", "building__name": "Campus Center"}
GLOBAL_STATUS_DEFAULT = {'name': "Available"}

logger = logging.getLogger(__name__)


class EquipmentCategory(MPTTModel):
    name = models.CharField(max_length=64, blank=False, null=False)
    usual_place = models.ForeignKey(Location, blank=True, null=True,
                                    help_text="Default place for items of this category. "
                                              "Inherits from parent categories.")

    parent = TreeForeignKey('self', null=True, blank=True,
                            related_name='children', db_index=True,
                            help_text="If this is a subcategory, the parent is what this is a subcategory of. "
                                      "Choose '---' if not.")

    # for templates
    @cached_property
    def get_ancestors_inclusive(self, ascending=False):
        return self.get_ancestors(ascending=ascending, include_self=True)

    @cached_property
    def get_descendants_inclusive(self):
        return self.get_descendants(include_self=True)

    @classmethod
    def possible_locations(cls):
        return Location.objects.complex_filter(
            Q(holds_equipment=True) |  # The usual culprits
            Q(equipmentcategory__isnull=False) |  # or is the default place of a category
            Q(equipmentitem__isnull=False)  # or has at least one item in it.
        ).distinct()

    @cached_property
    def default_location(self):
        if self.usual_place:
            return self.usual_place

        parent_places = self.get_ancestors(ascending=True).filter(usual_place__isnull=False)
        if parent_places:
            return parent_places.first().usual_place

        try:
            return Location.objects.get(**GLOBAL_LOC_DEFAULT)
        except (Location.MultipleObjectsReturned, Location.DoesNotExist):
            logging.warn("Unable to load default location for %s" % self.name)
            return None

    @cached_property
    def breadcrumbs(self):
        out = [('Inventory', reverse('inventory:view_all'))]
        out.extend([
            (cat.name, reverse('inventory:cat', args=[cat.pk])) for cat in self.get_ancestors_inclusive
        ])
        return out

    def __str__(self):
        return self.name

    class MPTTMeta:
        order_insertion_by = ['name']


class EquimentItemManager(TreeManager):
    def bulk_add_helper(self, item_type, num_to_add, put_into=None):
        items = []

        # loc is usually automatic, but not in bulk queries
        default_loc = item_type.category.default_location if put_into is None else None
        with self.delay_mptt_updates():
            for i in xrange(0, num_to_add):
                items.append(EquipmentItem(item_type=item_type, home=default_loc,
                                           purchase_date=datetime.date.today(),
                                           case=put_into,
                                           level=0, rght=0, lft=0, tree_id=0))
        self.bulk_create(items)
        self.rebuild()


class EquipmentItem(MPTTModel):
    objects = EquimentItemManager()
    item_type = models.ForeignKey('EquipmentClass', related_name="items", null=False, blank=False)
    serial_number = models.CharField(max_length=256, null=True, blank=True)
    case = TreeForeignKey('self', null=True, blank=True,
                          related_name='contents', db_index=True,
                          help_text="Case or item that contains this item")

    barcode = models.BigIntegerField(null=True, blank=True, unique=True)
    purchase_date = models.DateField(null=False, blank=True)
    home = models.ForeignKey(Location, null=True, blank=True, help_text="Place where this item typically resides.")
    features = models.CharField(max_length=128, null=True, blank=True, verbose_name='Identifying Features')

    def save(self, *args, **kwargs):
        if self.purchase_date is None:
            self.purchase_date = datetime.date.today()
        if self.pk is None and not self.home and not self.case:
            self.home = self.item_type.category.default_location
        if self.case and self.home:
            self.home = None  # location inherits from parent
        super(EquipmentItem, self).save(*args, **kwargs)

    @cached_property
    def breadcrumbs(self):
        out = self.item_type.breadcrumbs

        out.append(
            ("Item %s" % (self.barcode or self.pk), reverse('inventory:item_detail', args=[self.pk]))
        )
        return out

    @property
    def location(self):
        if self.case:
            return self.get_root().location
        elif self.home:
            return self.home
        elif self.case:
            return self.case.home
        else:
            return None

    @cached_property
    def unsafe_to_delete(self):
        return self.get_children().exists()

    @cached_property
    def status(self):
        try:
            return self.maintenance.latest('date').status
        except:
            try:
                return EquipmentStatus.objects.get(**GLOBAL_STATUS_DEFAULT)
            except Exception as e:
                logging.warn("Unable to load default status for item %d [%s]" %
                             (self.pk, e.message))
                return None

    def __str__(self):
        return "%s (%d)" % (str(self.item_type),
                            self.barcode or self.pk)

    class MPTTMeta:
        parent_attr = 'case'


class EquipmentClass(models.Model):
    name = models.CharField(max_length=256)
    category = TreeForeignKey(EquipmentCategory, null=False, blank=False)
    description = models.TextField(help_text="Function, appearance, and included acessories", null=True, blank=True)
    value = models.DecimalField(help_text="Estimated purchase value", max_digits=9, decimal_places=2,
                                null=True, blank=True)
    model_number = models.CharField(max_length=256, null=True, blank=True)
    manufacturer = models.CharField(max_length=128, null=True, blank=True)
    url = models.URLField(null=True, blank=True)
    holds_items = models.BooleanField(default=False, help_text="Can hold other items")

    length = models.DecimalField(help_text="Length in inches", max_digits=6, decimal_places=2, null=True, blank=True)
    width = models.DecimalField(help_text="Width in inches", max_digits=6, decimal_places=2, null=True, blank=True)
    height = models.DecimalField(help_text="Height in inches", max_digits=6, decimal_places=2, null=True, blank=True)
    weight = models.DecimalField(help_text="Weight in lbs.", max_digits=6, decimal_places=2, null=True, blank=True)

    wiki_text = models.TextField(help_text="How to use this item", null=True, blank=True)

    def __unicode__(self):
        return self.name

    @cached_property
    def breadcrumbs(self):
        out = self.category.breadcrumbs
        out.append(
            (self.name, reverse('inventory:type_detail', args=[self.pk]))
        )
        return out

    def size(self):
        dims = filter(lambda dim: dim is not None,
                      [self.length, self.width, self.height])
        return "x".join((str(dim) for dim in dims))

    class Meta:
        permissions = (
            ("edit_equipment_wiki", "Edit the wiki of an equipment"),
            ("view_equipment_value", "View estimated value of an equipment"),
            ("view_equipment", "View equipment")
        )


# Eg. 'In Repair', 'Out on rental', 'In service'
class EquipmentStatus(models.Model):
    name = models.CharField(max_length=32)
    glyphicon = models.CharField(max_length=32)

    def __unicode__(self):
        return self.name


class EquipmentMaintEntry(models.Model):
    date = models.DateTimeField(auto_now_add=True)

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=False, blank=False)

    title = models.CharField(max_length=32, null=False, blank=False)
    entry = models.TextField(null=True, blank=True)

    equipment = models.ForeignKey(EquipmentItem, related_name='maintenance',
                                  null=False, blank=False)
    status = models.ForeignKey(EquipmentStatus, null=False, blank=False)

    def __unicode__(self):
        return str(self.date)

    class Meta:
        get_latest_by = "date"
        ordering = ['-date']
