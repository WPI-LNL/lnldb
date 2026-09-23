"""
The admin, which is where this module is configured rather than merely browsed.

Most of what used to be constants in this app -- spend categories, fund codes,
partition codes, the fiscal year's start month, the suggestion rules -- are now
rows a Treasurer edits here. That makes the admin part of the product and not
just a debugging tool, so its guard rails are worth testing: a vocabulary row
still attached to real money must be retirable but not deletable, and the bank
truth must stay unwritable from every direction including this one.
"""
import datetime
from decimal import Decimal

from django.contrib.admin.sites import site
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from finance.admin import ColumnAliasAdmin, VocabularyAdmin
from finance.importers import COLUMN_ALIASES
from finance.models import (ColumnAlias, FinanceSettings, ParsedTransaction, PartitionCode,
                            ServiceColor, SpendCategory, SuggestionRule, WorkdayTransaction)
from finance.tests.util import category, fund


class AdminSmokeTests(TestCase):
    """
    Every registered page loads.

    A changelist that 500s is invisible until somebody opens it, and these are
    opened rarely -- once a year, by whoever inherited the Treasurer role.
    """

    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username='root', email='root@wpi.edu', password='x')
        self.client.force_login(self.user)

    def test_every_registered_changelist_loads(self):
        from finance import models as finance_models
        for model, model_admin in site._registry.items():
            if model.__module__ != finance_models.__name__:
                continue
            url = reverse('admin:%s_%s_changelist'
                          % (model._meta.app_label, model._meta.model_name))
            response = self.client.get(url, follow=True)
            self.assertEqual(response.status_code, 200, model.__name__)

    def test_the_add_pages_load_where_adding_is_allowed(self):
        for model in (SpendCategory, SuggestionRule, PartitionCode, ColumnAlias, ServiceColor):
            url = reverse('admin:%s_%s_add' % (model._meta.app_label, model._meta.model_name))
            self.assertEqual(self.client.get(url).status_code, 200, model.__name__)


class VocabularyGuardTests(TestCase):
    """
    A category still attached to money is retired, never deleted.

    The foreign key is ``PROTECT``, so a delete would fail anyway -- the point
    is not to offer it, since an admin button that always errors is worse than
    an absent one.
    """

    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username='root2', email='root2@wpi.edu', password='x')
        self.request = type('R', (), {'user': self.user})()
        self.admin = site._registry[SpendCategory]
        self.txn = WorkdayTransaction.objects.create(
            operational_transaction='OT-A1', accounting_date=datetime.date(2025, 9, 15),
            net_amount=Decimal('-40.00'))

    def test_an_unused_category_may_be_deleted(self):
        spare = SpendCategory.objects.create(name='Rigging Hardware', slug='rigging')
        self.assertTrue(self.admin.has_delete_permission(self.request, spare))

    def test_a_category_in_use_may_not_be_deleted(self):
        ParsedTransaction.objects.create(
            parent_transaction=self.txn, amount=Decimal('-40.00'),
            effective_date=self.txn.accounting_date, fund_source=fund('sga_budget'),
            lnl_spend_category=category('consumables'))
        self.assertFalse(self.admin.has_delete_permission(self.request, category('consumables')))

    def test_the_changelist_counts_what_is_filed_under_each_row(self):
        """ The number that tells a Treasurer whether retiring a row is safe. """
        ParsedTransaction.objects.create(
            parent_transaction=self.txn, amount=Decimal('-40.00'),
            effective_date=self.txn.accounting_date, fund_source=fund('sga_budget'),
            lnl_spend_category=category('consumables'))
        self.assertEqual(self.admin.in_use(category('consumables')), 1)
        self.assertEqual(self.admin.in_use(category('repairs')), 0)

    def test_the_delete_guard_holds_for_funds_as_well(self):
        """ ``usage_related_name`` is what makes one base class serve them all. """
        fund_admin = site._registry[type(fund('sga_budget'))]
        self.assertIsInstance(fund_admin, VocabularyAdmin)
        ParsedTransaction.objects.create(
            parent_transaction=self.txn, amount=Decimal('-40.00'),
            effective_date=self.txn.accounting_date, fund_source=fund('sga_budget'),
            lnl_spend_category=category('consumables'))
        self.assertFalse(fund_admin.has_delete_permission(self.request, fund('sga_budget')))

    def test_the_colour_swatch_renders_the_stored_colour(self):
        html = self.admin.swatch(category('consumables'))
        self.assertIn(category('consumables').color, html)

    def test_the_rule_count_is_shown_against_each_category(self):
        SuggestionRule.objects.create(
            match_field='memo', match_mode='word', pattern='gaff',
            spend_category=category('consumables'))
        self.assertGreaterEqual(self.admin.rule_count(category('consumables')), 1)


class BankTruthAdminTests(TestCase):
    """
    The imported Workday rows are immutable, and the admin is the likeliest
    place for someone to try to "just fix one".
    """

    def setUp(self):
        self.admin = site._registry[WorkdayTransaction]
        self.user = get_user_model().objects.create_superuser(
            username='root3', email='root3@wpi.edu', password='x')
        self.request = type('R', (), {'user': self.user})()
        self.txn = WorkdayTransaction.objects.create(
            operational_transaction='OT-A2', accounting_date=datetime.date(2025, 9, 15),
            net_amount=Decimal('-40.00'),
            worktags_json={'student_organization': '315-AG'})

    def test_rows_cannot_be_added_by_hand(self):
        """ They arrive only through the importer, which assigns their identity. """
        self.assertFalse(self.admin.has_add_permission(self.request))

    def test_rows_cannot_be_changed(self):
        self.assertFalse(self.admin.has_change_permission(self.request, self.txn))

    def test_rows_cannot_be_deleted(self):
        self.assertFalse(self.admin.has_delete_permission(self.request, self.txn))

    def test_every_field_is_read_only(self):
        names = {f.name for f in WorkdayTransaction._meta.fields}
        self.assertEqual(set(self.admin.readonly_fields), names)

    def test_the_default_partition_is_shown(self):
        self.assertTrue(self.admin.defaults_to_projection(self.txn))


class SuggestionRuleAdminTests(TestCase):
    """ The column that tells a rule that fills a box from one that offers a chip. """

    def setUp(self):
        self.admin = site._registry[SuggestionRule]

    def test_an_exact_code_match_fills_the_form_in(self):
        rule = SuggestionRule.objects.create(
            match_field='spend_category', match_mode='exact', pattern='Supplies',
            spend_category=category('consumables'))
        self.assertTrue(self.admin.fills_in(rule))

    def test_a_word_spotted_in_prose_only_offers_itself(self):
        rule = SuggestionRule.objects.create(
            match_field='memo', match_mode='word', pattern='gaff',
            spend_category=category('consumables'))
        self.assertFalse(self.admin.fills_in(rule))


class PartitionCodeAdminTests(TestCase):
    def test_the_side_is_spelled_out_rather_than_shown_as_a_boolean(self):
        """ "Projection" reads; ``True`` does not say which side it means. """
        admin = site._registry[PartitionCode]
        projection = PartitionCode.objects.get(code='315-AG')
        events = PartitionCode.objects.get(code='226-AG')
        self.assertEqual(admin.partition(projection), 'Projection')
        self.assertEqual(admin.partition(events), 'Event Production')


class FinanceSettingsAdminTests(TestCase):
    """ One row, so the admin neither adds a second nor deletes the only one. """

    def setUp(self):
        self.admin = site._registry[FinanceSettings]
        self.user = get_user_model().objects.create_superuser(
            username='root4', email='root4@wpi.edu', password='x')
        self.request = type('R', (), {'user': self.user})()
        self.client.force_login(self.user)

    def test_a_second_row_cannot_be_added(self):
        FinanceSettings.load()
        self.assertFalse(self.admin.has_add_permission(self.request))

    def test_the_only_row_cannot_be_deleted(self):
        self.assertFalse(self.admin.has_delete_permission(self.request, FinanceSettings.load()))

    def test_the_changelist_goes_straight_to_the_settings(self):
        """ A one-row changelist is a list with one link on it; skip the step. """
        response = self.client.get(reverse('admin:finance_financesettings_changelist'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('financesettings', response['Location'])


class ColumnAliasAdminTests(TestCase):
    """
    The canonical side is chosen from the importer's own names, so a Treasurer
    teaching it a renamed Workday column cannot point it at nothing.
    """

    def setUp(self):
        self.admin = ColumnAliasAdmin(ColumnAlias, site)
        self.user = get_user_model().objects.create_superuser(
            username='root5', email='root5@wpi.edu', password='x')
        self.request = type('R', (), {'user': self.user})()

    def test_the_canonical_field_offers_only_columns_the_importer_reads(self):
        field = self.admin.formfield_for_dbfield(
            ColumnAlias._meta.get_field('canonical'), self.request)
        offered = {value for value, label in field.choices if value}
        self.assertEqual(offered, set(COLUMN_ALIASES))

    def test_the_choices_are_shown_with_readable_labels(self):
        field = self.admin.formfield_for_dbfield(
            ColumnAlias._meta.get_field('canonical'), self.request)
        labels = dict(field.choices)
        self.assertEqual(labels['credit_minus_debit'], 'Credit Minus Debit')

    def test_other_fields_are_left_alone(self):
        field = self.admin.formfield_for_dbfield(
            ColumnAlias._meta.get_field('alias'), self.request)
        self.assertFalse(hasattr(field, 'choices') and field.choices)


class ServiceColorAdminTests(TestCase):
    def test_the_swatch_shows_the_configured_colour(self):
        from events.tests.generators import CategoryFactory
        colour = ServiceColor.objects.create(category=CategoryFactory(), color='#4E79A7')
        self.assertIn('#4E79A7', site._registry[ServiceColor].swatch(colour))
