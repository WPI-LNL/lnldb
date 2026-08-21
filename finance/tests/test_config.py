"""
The settings that moved out of code and into the admin.

Each test changes a row and asserts the behaviour follows, which is the whole
point of the exercise: a value nothing reads is not configuration.
"""
import datetime
from decimal import Decimal

from django.test import TestCase

from finance.importers import import_workday_export, normalise_header
from finance.models import (ColumnAlias, FinanceSettings, ServiceColor, WorkdayTransaction,
                            current_fiscal_year, fiscal_year_bounds, fiscal_year_choices,
                            fiscal_year_for, reset_finance_cache, student_org_workday_fund)


class FinanceSettingsTests(TestCase):
    def tearDown(self):
        # A rollback does not fire the signals that clear the cache.
        reset_finance_cache()

    def test_a_row_exists_out_of_the_box(self):
        self.assertEqual(FinanceSettings.load().fiscal_year_start_month, 7)

    def test_there_can_only_ever_be_one(self):
        FinanceSettings.objects.create(fiscal_year_start_month=3)
        self.assertEqual(FinanceSettings.objects.count(), 1)
        self.assertEqual(FinanceSettings.load().fiscal_year_start_month, 3)

    def test_it_cannot_be_deleted(self):
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            FinanceSettings.load().delete()

    def test_the_fiscal_year_follows_the_setting(self):
        july = datetime.date(2025, 7, 1)
        self.assertEqual(fiscal_year_for(july), 2026)

        config = FinanceSettings.load()
        config.fiscal_year_start_month = 9
        config.save()
        # July now falls before the year starts, so it belongs to the old one.
        self.assertEqual(fiscal_year_for(july), 2025)
        self.assertEqual(fiscal_year_bounds(2026),
                         (datetime.date(2025, 9, 1), datetime.date(2026, 8, 31)))

    def test_saving_clears_the_cache_by_itself(self):
        """ Without the signal an admin edit would do nothing until a restart. """
        self.assertEqual(fiscal_year_for(datetime.date(2025, 7, 1)), 2026)   # primes the cache
        config = FinanceSettings.load()
        config.fiscal_year_start_month = 8
        config.save()
        self.assertEqual(fiscal_year_for(datetime.date(2025, 7, 1)), 2025)

    def test_the_year_picker_width_follows_the_setting(self):
        config = FinanceSettings.load()
        config.fiscal_years_back = 2
        config.fiscal_years_forward = 0
        config.save()
        years = [fy for fy, _ in fiscal_year_choices()]
        self.assertEqual(years, [current_fiscal_year(), current_fiscal_year() - 1,
                                 current_fiscal_year() - 2])

    def test_the_student_org_fund_follows_the_setting(self):
        self.assertEqual(student_org_workday_fund(), 810)
        config = FinanceSettings.load()
        config.student_org_workday_fund = 999
        config.save()
        self.assertEqual(student_org_workday_fund(), 999)

    def test_client_type_follows_the_setting(self):
        from events.tests.generators import Event2019Factory, OrgFactory
        from finance.calculators import _client_type_of
        from finance.models import ClientType

        event = Event2019Factory.create(billing_org=OrgFactory.create(workday_fund=810))
        self.assertEqual(_client_type_of(event), ClientType.STUDENT_ORG)

        config = FinanceSettings.load()
        config.student_org_workday_fund = 811
        config.save()
        self.assertEqual(_client_type_of(event), ClientType.DEPARTMENT)


class ServiceColorTests(TestCase):
    def tearDown(self):
        reset_finance_cache()

    def test_a_colour_can_be_assigned_to_any_category(self):
        from events.tests.generators import CategoryFactory
        from finance.models import service_colors

        category = CategoryFactory.create(name='Video')
        self.assertNotIn('Video', service_colors())

        ServiceColor.objects.create(category=category, color='#123456')
        self.assertEqual(service_colors()['Video'], '#123456')

    def test_the_familiar_three_need_no_configuration(self):
        from finance.models import service_colors
        self.assertEqual(service_colors()['Sound'], '#4E79A7')

    def test_a_row_overrides_the_default(self):
        from events.tests.generators import CategoryFactory
        from finance.models import service_colors

        ServiceColor.objects.create(category=CategoryFactory.create(name='Sound'),
                                    color='#000000')
        self.assertEqual(service_colors()['Sound'], '#000000')

    def test_renaming_a_category_keeps_its_colour(self):
        """ The old dict was keyed by name, so a rename silently lost the colour. """
        from events.tests.generators import CategoryFactory
        from finance.models import service_colors

        category = CategoryFactory.create(name='Sound')
        ServiceColor.objects.create(category=category, color='#4E79A7')
        category.name = 'Audio'
        category.save()
        reset_finance_cache()
        self.assertEqual(service_colors()['Audio'], '#4E79A7')


HEADER = ("Accounting Date,Debit Amount,Credit Amount,Credit Minus Debit,Operational Transaction,"
          "Supplier,Employee,Journal,Journal Line Memo,Header Memo,Fund,Cost Center,"
          "Ledger Account,Spend Category,Revenue Category,Activity,Student Org Code,Program")
ROW = ('09/15/2025,1200.00,0.00,"(1,200.00)",OT-2001,B&H Photo,,JRN-88,Lighting order,,'
       '110-FD,CC-1,71100:Supplies,Supplies,,,315-AG Projection,Ops')


class ColumnAliasTests(TestCase):
    """ Workday relabelling a column should be a row, not a release. """

    def tearDown(self):
        reset_finance_cache()

    def _upload(self):
        import io
        return io.BytesIO((HEADER + "\n" + ROW + "\n").encode('utf-8'))

    def test_an_unknown_heading_is_not_recognised(self):
        self.assertEqual(normalise_header('Student Org Code'), 'student_org_code')

    def test_an_alias_teaches_the_importer(self):
        ColumnAlias.objects.create(canonical='student_organization', alias='Student Org Code')
        self.assertEqual(normalise_header('Student Org Code'), 'student_organization')

    def test_matching_ignores_case_and_punctuation(self):
        ColumnAlias.objects.create(canonical='student_organization', alias='Student Org Code')
        self.assertEqual(normalise_header('  STUDENT-ORG_CODE '), 'student_organization')

    def test_the_partition_default_works_through_an_alias(self):
        """ End to end: the renamed column still places the line. """
        import_workday_export(self._upload())
        txn = WorkdayTransaction.objects.get(operational_transaction='OT-2001')
        self.assertIsNone(txn.default_partition)   # column not understood yet

        WorkdayTransaction.objects.all().hard_delete()
        ColumnAlias.objects.create(canonical='student_organization', alias='Student Org Code')
        import_workday_export(self._upload())
        txn = WorkdayTransaction.objects.get(operational_transaction='OT-2001')
        self.assertEqual(txn.default_partition, 'projection')
        self.assertEqual(txn.net_amount, Decimal('-1200.00'))

    def test_the_built_in_spellings_still_work(self):
        self.assertEqual(normalise_header('Student Organization'), 'student_organization')
