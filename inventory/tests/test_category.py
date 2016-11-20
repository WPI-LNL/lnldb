from django.test import TestCase

from ..forms import CategoryForm
from ..models import EquipmentCategory


class CategoryFormTest(TestCase):
    def setUp(self):
        self.cat = EquipmentCategory.objects.create(name="Test Category")

    def test_blank_form(self):
        form = CategoryForm()
        self.assertFalse(form.is_valid())  # needs a name

    def test_make_cat(self):
        form = CategoryForm({
            'name': 'Test Category',
            'parent': None,
            'usual_place': None
        })
        self.assertTrue(form.is_valid())
        obj = form.save()
        self.assertIsNotNone(obj.pk)

    def test_make_subcat(self):
        form = CategoryForm({
            'name': 'Test Subcategory',
            'parent': self.cat.pk,
            'usual_place': None
        })
        self.assertTrue(form.is_valid())
        obj = form.save()
        self.assertIsNotNone(obj.pk)
        self.assertEqual(obj.parent, self.cat)

    def test_make_bad_cat_self(self):
        form = CategoryForm({
            'name': 'Test Bad Subcategory',
            'parent': self.cat.pk,
            'usual_place': None
        }, instance=self.cat)
        self.assertFalse(form.is_valid())

    def test_make_bad_cat_sub(self):
        subcat = EquipmentCategory.objects.create(name="Test Subcategory", parent=self.cat)
        form = CategoryForm({
            'name': 'Test Bad Subcategory',
            'parent': subcat.pk,
            'usual_place': None
        }, instance=self.cat)
        self.assertFalse(form.is_valid())

    def test_make_into_subcat(self):
        other_cat = EquipmentCategory.objects.create(name="Test New Parent Category")
        form = CategoryForm({
            'name': self.cat.name,
            'parent': other_cat.pk,
        }, instance=self.cat)
        self.assertTrue(form.is_valid())
        obj = form.save()
        self.assertEqual(obj.parent, other_cat)

    def test_make_into_root_cat(self):
        subcat = EquipmentCategory.objects.create(name="Test Subcategory", parent=self.cat)
        form = CategoryForm({
            'name': subcat.name,
            'parent': None,
        }, instance=subcat)
        self.assertTrue(form.is_valid())
        obj = form.save()
        self.assertIsNone(obj.parent)
