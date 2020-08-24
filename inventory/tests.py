import logging
from django.urls import reverse
from django.contrib.auth.models import Permission
from data.tests.util import ViewTestCase
from events.tests.generators import LocationFactory

logging.disable(logging.WARNING)

# Remnants of the old inventory system
# from django.test import TestCase

# from .forms import CategoryForm
# from .models import EquipmentCategory


# class CategoryFormTest(TestCase):
#     def setUp(self):
#         self.cat = EquipmentCategory.objects.create(name="Test Category")
#
#     def test_blank_form(self):
#         form = CategoryForm()
#         self.assertFalse(form.is_valid())  # needs a name
#
#     def test_make_cat(self):
#         form = CategoryForm({
#             'name': 'Test Category',
#             'parent': None,
#             'usual_place': None
#         })
#         self.assertTrue(form.is_valid())
#         obj = form.save()
#         self.assertIsNotNone(obj.pk)
#
#     def test_make_subcat(self):
#         form = CategoryForm({
#             'name': 'Test Subcategory',
#             'parent': self.cat.pk,
#             'usual_place': None
#         })
#         self.assertTrue(form.is_valid())
#         obj = form.save()
#         self.assertIsNotNone(obj.pk)
#         self.assertEqual(obj.parent, self.cat)
#
#     def test_make_bad_cat_self(self):
#         form = CategoryForm({
#             'name': 'Test Bad Subcategory',
#             'parent': self.cat.pk,
#             'usual_place': None
#         }, instance=self.cat)
#         self.assertFalse(form.is_valid())
#
#     def test_make_bad_cat_sub(self):
#         subcat = EquipmentCategory.objects.create(name="Test Subcategory", parent=self.cat)
#         form = CategoryForm({
#             'name': 'Test Bad Subcategory',
#             'parent': subcat.pk,
#             'usual_place': None
#         }, instance=self.cat)
#         self.assertFalse(form.is_valid())
#
#     def test_make_into_subcat(self):
#         other_cat = EquipmentCategory.objects.create(name="Test New Parent Category")
#         form = CategoryForm({
#             'name': self.cat.name,
#             'parent': other_cat.pk,
#         }, instance=self.cat)
#         self.assertTrue(form.is_valid())
#         obj = form.save()
#         self.assertEqual(obj.parent, other_cat)
#
#     def test_make_into_root_cat(self):
#         subcat = EquipmentCategory.objects.create(name="Test Subcategory", parent=self.cat)
#         form = CategoryForm({
#             'name': subcat.name,
#             'parent': None,
#         }, instance=subcat)
#         self.assertTrue(form.is_valid())
#         obj = form.save()
#         self.assertIsNone(obj.parent)


class AccessRecordTests(ViewTestCase):
    def test_log_access(self):
        location = LocationFactory(name="CC Office", holds_equipment=True)

        # Check that we get 404 if location matching query cannot be found
        self.assertOk(self.client.get(reverse("inventory:log_access", args=['Alden-Sub'])), 404)

        # Check that everything loads ok when there's a match
        self.assertOk(self.client.get(reverse("inventory:log_access", args=['CC-Office'])))

        # Verify that the checkin form redirects home once submitted successfully
        valid_data = {
            "users": [str(self.user.pk)],
            "location": str(location.pk),
            "reason": "To play with the Bose Cannon",
            "save": "Submit"
        }

        self.assertRedirects(self.client.post(reverse("inventory:log_access", args=['CC-Office']), valid_data),
                             reverse("home"))

        # Test the checkout process (checking out is optional)
        valid_data = {
            "users": [str(self.user.pk)],
            "location": str(location.pk),
            "reason": "OUT",
            "save": "Submit"
        }

        self.assertRedirects(self.client.post(reverse("inventory:log_exit", args=['cc']), valid_data),
                             reverse("home"))

    def test_view_logs(self):
        # Default user should not have permission to view access logs
        self.assertOk(self.client.get(reverse("inventory:view_logs")), 403)

        permission = Permission.objects.get(codename="view_access_logs")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("inventory:view_logs")))
