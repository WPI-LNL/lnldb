import datetime
import io
from decimal import Decimal

from django.test import TestCase

from finance.importers import (ImportError_, build_memo, import_workday_export, normalise_header,
                               parse_date, parse_decimal)
from finance.models import WorkdayTransaction
from finance.tests.util import category, fund

HEADER = ("Accounting Date,Debit Amount,Credit Amount,Credit Minus Debit,Operational Transaction,"
          "Supplier,Employee,Journal,Journal Line Memo,Header Memo,Fund,Cost Center,"
          "Ledger Account,Spend Category,Revenue Category,Activity,Student Organization,Program")

EXPENSE_ROW = ('09/15/2025,1200.00,0.00,"(1,200.00)",OT-1001,B&H Photo,,JRN-88,'
               'Lighting order,September purchases,110-FD,CC-1234,71100:Supplies,Supplies,,,'
               '226-AG Lens & Light Club,Ops')

REVENUE_ROW = ('09/20/2025,0.00,500.00,"500.00",OT-1002,,Jane Doe,JRN-89,'
               'Event billing,Fall concert,810-FD,CC-1234,,,Event Revenue,Fall Concert,SO-42,Ops')

PROJECTION_ROW = ('09/25/2025,850.00,0.00,"(850.00)",OT-1003,Christie Digital,,JRN-90,'
                  'Projector lamp,,110-FD,CC-1234,74100:Repairs & Maintenance,Repair,,,'
                  '315-AG Projection,Film')

# Verbatim shapes from a real 226-AG export. See ImportIdentityTests.
#
# One supplier invoice, several lines -- the Operational Transaction repeats
# and only the amount and memo tell the lines apart.
INVOICE_LINE_1 = ('7/1/2025,17.91,0.00,(17.91),Supplier Invoice: 25070087-SINV,'
                  '"Amazon Capital Services, Inc.",,Operational Journal: WPI - 07/01/2025,'
                  'Gaff tape,,810-FD Agency,1125-CC Student Clubs,71100:Supplies,Supplies,,,'
                  '226-AG Lens & Light Club,920 Agencies')
INVOICE_LINE_2 = INVOICE_LINE_1.replace('17.91', '20.99').replace('Gaff tape', 'Spike tape')

# The same subscription billed twice in one month: every exported field agrees,
# and both charges are real.
SPOTIFY_ROW = ('8/8/2025,19.99,0.00,(19.99),Expense Report: 25080207-EXP,,Hannah Poirier,'
               'Operational Journal: WPI - 08/08/2025,Spotify Monthly Subscription,'
               'LNL Pcard Transactions,810-FD Agency,1125-CC Student Clubs,'
               '72000:Subscriptions & Memberships,Subscriptions & Memberships,,,'
               '226-AG Lens & Light Club,920 Agencies')

# A journal entry: no Operational Transaction at all.
JOURNAL_ENTRY_ROW = ('8/31/2025,176.26,0.00,(176.26),,,,'
                     '25090054-JE - Worcester Polytechnic Institute - WPI - 08/31/2025,'
                     '306711: 11x17 posters for LNL,,810-FD Agency,1125-CC Student Clubs,'
                     '71100:Supplies,Printing,,,226-AG Lens & Light Club,920 Agencies')


def upload(*rows, header=HEADER):
    return io.BytesIO(("\n".join([header] + list(rows)) + "\n").encode('utf-8'))


class HelperTests(TestCase):
    def test_header_normalisation(self):
        self.assertEqual(normalise_header('  Credit Minus Debit '), 'credit_minus_debit')
        self.assertEqual(normalise_header('Operational Transaction'), 'operational_transaction')
        self.assertEqual(normalise_header('﻿Accounting Date'), 'accounting_date')
        self.assertEqual(normalise_header('Cost Centre'), 'cost_center')

    def test_parenthesised_negatives(self):
        self.assertEqual(parse_decimal('(1,200.00)'), Decimal('-1200.00'))

    def test_currency_symbols_and_separators(self):
        self.assertEqual(parse_decimal('$1,200.00'), Decimal('1200.00'))
        self.assertEqual(parse_decimal('1200'), Decimal('1200.00'))
        self.assertEqual(parse_decimal('-1,200.00'), Decimal('-1200.00'))
        self.assertEqual(parse_decimal('1,200.00 USD'), Decimal('1200.00'))

    def test_blank_amounts(self):
        self.assertIsNone(parse_decimal(''))
        self.assertIsNone(parse_decimal(None))

    def test_date_formats(self):
        self.assertEqual(parse_date('09/15/2025'), datetime.date(2025, 9, 15))
        self.assertEqual(parse_date('2025-09-15'), datetime.date(2025, 9, 15))
        self.assertIsNone(parse_date('not a date'))

    def test_memo_concatenation(self):
        self.assertEqual(build_memo({'journal_line_memo': 'A', 'header_memo': 'B'}), 'A — B')
        self.assertEqual(build_memo({'journal_line_memo': 'A', 'header_memo': ''}), 'A')
        self.assertEqual(build_memo({'journal_line_memo': 'A', 'header_memo': 'A'}), 'A')


class ImportTests(TestCase):
    def test_imports_an_expense(self):
        result = import_workday_export(upload(EXPENSE_ROW), filename='sept.csv')
        self.assertEqual(result.created_count, 1)
        txn = WorkdayTransaction.objects.get(operational_transaction='OT-1001')
        self.assertEqual(txn.net_amount, Decimal('-1200.00'))
        self.assertEqual(txn.accounting_date, datetime.date(2025, 9, 15))
        self.assertEqual(txn.supplier, 'B&H Photo')
        self.assertEqual(txn.memo, 'Lighting order — September purchases')
        self.assertEqual(txn.source_file, 'sept.csv')

    def test_direction_comes_only_from_credit_minus_debit(self):
        """
        The row has Debit Amount 1200 and Credit Amount 0; both are ignored and
        the sign is taken solely from Credit Minus Debit.
        """
        import_workday_export(upload(EXPENSE_ROW))
        txn = WorkdayTransaction.objects.get(operational_transaction='OT-1001')
        self.assertEqual(txn.net_amount, Decimal('-1200.00'))
        self.assertNotIn('debit_amount', txn.worktags_json)
        self.assertNotIn('credit_amount', txn.worktags_json)

    def test_revenue_row_is_positive(self):
        import_workday_export(upload(REVENUE_ROW))
        txn = WorkdayTransaction.objects.get(operational_transaction='OT-1002')
        self.assertEqual(txn.net_amount, Decimal('500.00'))
        self.assertTrue(txn.is_revenue)
        self.assertEqual(txn.employee, 'Jane Doe')

    def test_worktags_are_captured(self):
        import_workday_export(upload(EXPENSE_ROW))
        txn = WorkdayTransaction.objects.get(operational_transaction='OT-1001')
        self.assertEqual(txn.worktags_json['ledger_account'], '71100:Supplies')
        self.assertEqual(txn.worktags_json['cost_center'], 'CC-1234')
        self.assertEqual(txn.worktags_json['spend_category'], 'Supplies')
        self.assertEqual(txn.worktags_json['fund'], '110-FD')
        self.assertEqual(txn.worktags_json['program'], 'Ops')
        self.assertEqual(txn.worktags_json['student_organization'], '226-AG Lens & Light Club')

    def test_projection_org_code_is_read_on_import(self):
        """ The partition comes from Student Organization, not Ledger Account. """
        import_workday_export(upload(PROJECTION_ROW))
        txn = WorkdayTransaction.objects.get(operational_transaction='OT-1003')
        self.assertEqual(txn.default_partition, 'projection')
        self.assertTrue(txn.crossing_requires_reason)

    def test_event_production_org_code_is_read_on_import(self):
        import_workday_export(upload(EXPENSE_ROW))
        txn = WorkdayTransaction.objects.get(operational_transaction='OT-1001')
        self.assertEqual(txn.default_partition, 'event')
        self.assertFalse(txn.defaults_to_projection)
        self.assertFalse(txn.crossing_requires_reason,
                         "buying Projection gear from the main account is ordinary")

    def test_journal_line_memo_is_kept_for_the_description(self):
        import_workday_export(upload(EXPENSE_ROW))
        txn = WorkdayTransaction.objects.get(operational_transaction='OT-1001')
        self.assertEqual(txn.journal_line_memo, 'Lighting order')
        # ...while `memo` still carries both halves for display.
        self.assertEqual(txn.memo, 'Lighting order — September purchases')

    def test_duplicate_import_is_skipped(self):
        import_workday_export(upload(EXPENSE_ROW, REVENUE_ROW))
        result = import_workday_export(upload(EXPENSE_ROW, REVENUE_ROW))
        self.assertEqual(result.created_count, 0)
        self.assertEqual(result.duplicate_count, 2)
        self.assertEqual(WorkdayTransaction.objects.count(), 2)

    def test_partial_reimport_adds_only_new_rows(self):
        import_workday_export(upload(EXPENSE_ROW))
        result = import_workday_export(upload(EXPENSE_ROW, REVENUE_ROW))
        self.assertEqual(result.created_count, 1)
        self.assertEqual(result.duplicate_count, 1)
        self.assertEqual(WorkdayTransaction.objects.count(), 2)

    def test_dry_run_writes_nothing(self):
        result = import_workday_export(upload(EXPENSE_ROW), dry_run=True)
        self.assertEqual(result.created_count, 1)
        self.assertEqual(WorkdayTransaction.objects.count(), 0)

    def test_utf8_bom_is_handled(self):
        payload = ("﻿" + HEADER + "\n" + EXPENSE_ROW + "\n").encode('utf-8-sig')
        result = import_workday_export(io.BytesIO(payload))
        self.assertEqual(result.created_count, 1)

    def test_blank_rows_are_ignored(self):
        result = import_workday_export(upload(EXPENSE_ROW, ',,,,,,,,,,,,,,,,,', REVENUE_ROW))
        self.assertEqual(result.created_count, 2)
        self.assertEqual(result.error_count, 0)

    def test_zero_amount_row_is_an_error(self):
        row = EXPENSE_ROW.replace('"(1,200.00)"', '0.00').replace('OT-1001', 'OT-ZERO')
        result = import_workday_export(upload(row))
        self.assertEqual(result.created_count, 0)
        self.assertEqual(result.error_count, 1)

    def test_unreadable_amount_is_reported_not_fatal(self):
        bad = EXPENSE_ROW.replace('"(1,200.00)"', 'N/A').replace('OT-1001', 'OT-BAD')
        result = import_workday_export(upload(bad, REVENUE_ROW))
        self.assertEqual(result.created_count, 1)
        self.assertEqual(result.error_count, 1)
        self.assertIn('Credit Minus Debit', result.errors[0].message)

    def test_journal_entry_line_without_an_operational_transaction_imports(self):
        """
        Every journal entry line in a real export has a blank Operational
        Transaction. Rejecting them cost 26 of 314 lines on the FY26 file.
        """
        result = import_workday_export(upload(JOURNAL_ENTRY_ROW))
        self.assertEqual(result.error_count, 0)
        self.assertEqual(result.created_count, 1)
        txn = WorkdayTransaction.objects.get(operational_transaction='')
        self.assertEqual(txn.net_amount, Decimal('-176.26'))
        # ...and it is still nameable on screen.
        self.assertEqual(txn.reference, '25090054-JE')

    def test_an_escaped_quote_in_a_memo_survives(self):
        """
        Regression: csv.Sniffer guessed doublequote=False on the real FY26
        export, so RFC-4180's "" escape stopped working and a memo reading
        'Planar 22" touchscreen' came back with a stray quote on the end. Two
        lines in 314, silently.
        """
        row = EXPENSE_ROW.replace('Lighting order',
                                  '"Planar 22"" touchscreen for DiGiCo Q225"')
        import_workday_export(upload(row))
        txn = WorkdayTransaction.objects.get(operational_transaction='OT-1001')
        self.assertEqual(txn.journal_line_memo, 'Planar 22" touchscreen for DiGiCo Q225')

    def test_tab_separated_files_still_work(self):
        """ Only the delimiter is sniffed now, so this has to keep working. """
        header = HEADER.replace(',', '\t')
        row = ('09/15/2025\t1200.00\t0.00\t-1200.00\tOT-1001\tB&H Photo\t\tJRN-88\t'
               'Lighting order\t\t110-FD\tCC-1234\t71100:Supplies\tSupplies\t\t\t'
               '226-AG Lens & Light Club\tOps')
        result = import_workday_export(upload(row, header=header))
        self.assertEqual(result.created_count, 1)
        self.assertEqual(WorkdayTransaction.objects.get().net_amount, Decimal('-1200.00'))

    def test_wrong_file_shape_raises(self):
        with self.assertRaises(ImportError_):
            import_workday_export(io.BytesIO(b"Name,Email\nfoo,bar\n"))

    def test_empty_file_raises(self):
        with self.assertRaises(ImportError_):
            import_workday_export(io.BytesIO(b""))

    def test_summary_counts(self):
        import_workday_export(upload(EXPENSE_ROW))
        result = import_workday_export(upload(EXPENSE_ROW, REVENUE_ROW))
        self.assertEqual(result.total, 2)
        self.assertIn('1 imported', result.summary())
        self.assertIn('1 skipped', result.summary())


class ImportIdentityTests(TestCase):
    """
    What counts as "the same line", against the shapes a real export contains.

    Operational Transaction was the duplicate guard until it turned out not to
    identify anything: on the FY26 226-AG export it discarded 131 of 314 lines
    as duplicates and errored on 26 more for having none at all.
    """

    def test_one_invoice_many_lines_all_import(self):
        result = import_workday_export(upload(INVOICE_LINE_1, INVOICE_LINE_2))
        self.assertEqual(result.created_count, 2)
        self.assertEqual(
            WorkdayTransaction.objects.filter(
                operational_transaction='Supplier Invoice: 25070087-SINV').count(), 2)

    def test_identical_lines_in_one_file_are_two_charges(self):
        """ Two identical subscription charges in a month really are two charges. """
        result = import_workday_export(upload(SPOTIFY_ROW, SPOTIFY_ROW))
        self.assertEqual(result.created_count, 2)
        self.assertEqual(result.duplicate_count, 0)
        stored = WorkdayTransaction.objects.all()
        self.assertEqual(len({t.row_fingerprint for t in stored}), 1)
        self.assertEqual(sorted(t.fingerprint_ordinal for t in stored), [1, 2])

    def test_identical_lines_in_a_second_file_are_a_re_upload(self):
        import_workday_export(upload(SPOTIFY_ROW, SPOTIFY_ROW))
        result = import_workday_export(upload(SPOTIFY_ROW, SPOTIFY_ROW))
        self.assertEqual(result.created_count, 0)
        self.assertEqual(result.duplicate_count, 2)
        self.assertEqual(WorkdayTransaction.objects.count(), 2)

    def test_a_later_export_tops_up_the_extra_occurrence(self):
        """
        The rule is "hold as many copies as the fullest export has shown", so a
        third charge in a wider export imports exactly once.
        """
        import_workday_export(upload(SPOTIFY_ROW, SPOTIFY_ROW))
        result = import_workday_export(upload(SPOTIFY_ROW, SPOTIFY_ROW, SPOTIFY_ROW))
        self.assertEqual(result.created_count, 1)
        self.assertEqual(result.duplicate_count, 2)
        self.assertEqual(
            sorted(WorkdayTransaction.objects.values_list('fingerprint_ordinal', flat=True)),
            [1, 2, 3])

    def test_order_within_the_file_does_not_matter(self):
        import_workday_export(upload(SPOTIFY_ROW))
        result = import_workday_export(upload(INVOICE_LINE_1, SPOTIFY_ROW, SPOTIFY_ROW))
        self.assertEqual(result.created_count, 2)   # the invoice line, and the second Spotify
        self.assertEqual(result.duplicate_count, 1)

    def test_a_differing_field_makes_a_different_line(self):
        """ Identity is the whole row, so one changed cell is a new transaction. """
        import_workday_export(upload(SPOTIFY_ROW))
        result = import_workday_export(upload(SPOTIFY_ROW.replace('19.99', '21.99')))
        self.assertEqual(result.created_count, 1)
        self.assertEqual(WorkdayTransaction.objects.count(), 2)

    def test_whitespace_and_case_do_not_split_a_line(self):
        import_workday_export(upload(SPOTIFY_ROW))
        noisy = SPOTIFY_ROW.replace('Spotify Monthly Subscription',
                                    'spotify  monthly   subscription ')
        result = import_workday_export(upload(noisy))
        self.assertEqual(result.created_count, 0)
        self.assertEqual(result.duplicate_count, 1)

    def test_journal_entries_are_deduplicated_without_a_reference(self):
        import_workday_export(upload(JOURNAL_ENTRY_ROW))
        result = import_workday_export(upload(JOURNAL_ENTRY_ROW))
        self.assertEqual(result.created_count, 0)
        self.assertEqual(WorkdayTransaction.objects.count(), 1)

    def test_two_different_journal_entries_both_import(self):
        other = JOURNAL_ENTRY_ROW.replace('306711: 11x17 posters for LNL',
                                          '306786: Posters V for Vendetta')
        result = import_workday_export(upload(JOURNAL_ENTRY_ROW, other))
        self.assertEqual(result.created_count, 2)

    def test_duplicate_message_says_how_many_are_held(self):
        import_workday_export(upload(SPOTIFY_ROW, SPOTIFY_ROW))
        result = import_workday_export(upload(SPOTIFY_ROW, SPOTIFY_ROW))
        self.assertIn('the ledger holds 2 identical lines',
                      [r.message for r in result.rows if r.status == 'duplicate'][-1])

    def test_dry_run_does_not_consume_occurrences(self):
        import_workday_export(upload(SPOTIFY_ROW, SPOTIFY_ROW), dry_run=True)
        result = import_workday_export(upload(SPOTIFY_ROW, SPOTIFY_ROW))
        self.assertEqual(result.created_count, 2)


class SuggestionTests(TestCase):
    def setUp(self):
        import_workday_export(upload(EXPENSE_ROW, PROJECTION_ROW, REVENUE_ROW))

    def test_spend_category_suggested_from_workday_worktag(self):
        from finance.suggestions import suggest_spend_category
        txn = WorkdayTransaction.objects.get(operational_transaction='OT-1001')
        suggestion = suggest_spend_category(txn)
        self.assertIsNotNone(suggestion)
        self.assertEqual(suggestion.value, category('consumables').pk)
        self.assertEqual(suggestion.confidence, 'high')

    def test_repair_category_suggested(self):
        from finance.suggestions import suggest_spend_category
        txn = WorkdayTransaction.objects.get(operational_transaction='OT-1003')
        self.assertEqual(suggest_spend_category(txn).value, category('repairs').pk)

    def test_810_is_not_read_as_sga_money(self):
        """
        810-FD is the fund every LNL line is spent out of, so it cannot say
        whether the money was the SGA standing budget, an award or legacy
        funds. Left blank rather than pre-filled with one of the three.
        """
        from finance.suggestions import suggest_fund_source
        txn = WorkdayTransaction.objects.get(operational_transaction='OT-1002')
        self.assertIsNone(suggest_fund_source(txn))

    def test_a_fund_code_that_does_identify_a_bucket_is_a_lookup(self):
        from finance.suggestions import suggest_fund_source
        txn = WorkdayTransaction.objects.create(
            operational_transaction='OT-GIFT', accounting_date=datetime.date(2025, 9, 1),
            net_amount=Decimal('-100.00'), worktags_json={'fund': '220-FD Gift'})
        suggestion = suggest_fund_source(txn)
        # The code is declared on the fund source in the admin and names that
        # fund alone, so reading it back off a line is a lookup, not an opinion.
        self.assertEqual(suggestion.value, fund('legacy').pk)
        self.assertEqual(suggestion.confidence, 'high')
        self.assertTrue(suggestion.is_lookup)

    def test_unrecognised_fund_is_left_blank_rather_than_guessed(self):
        from finance.suggestions import suggest_fund_source
        txn = WorkdayTransaction.objects.get(operational_transaction='OT-1001')
        self.assertIsNone(suggest_fund_source(txn))

    def test_project_tag_matched_from_memo(self):
        from finance.models import ProjectTag
        from finance.suggestions import suggest_project_tag
        tag = ProjectTag.objects.create(name='New Equipment List', code='NEL26')
        txn = WorkdayTransaction.objects.create(
            operational_transaction='OT-TAG', accounting_date=datetime.date(2025, 9, 1),
            net_amount=Decimal('-100.00'), memo='Fixtures for NEL26 build')
        suggestion = suggest_project_tag(txn)
        self.assertIsNotNone(suggestion)
        self.assertEqual(suggestion.value, tag.pk)

    def test_suggest_all_switches_on_direction(self):
        from finance.suggestions import suggest_all
        expense = WorkdayTransaction.objects.get(operational_transaction='OT-1001')
        self.assertEqual(suggest_all(expense)['kind'], 'expense')
        revenue = WorkdayTransaction.objects.create(
            operational_transaction='OT-REV', accounting_date=datetime.date(2025, 9, 1),
            net_amount=Decimal('500.00'))
        self.assertEqual(suggest_all(revenue)['kind'], 'revenue')


def understate_dimensions(buffer, ref='A1:A1'):
    """
    Rewrite a workbook's declared ``<dimension>`` so it lies about the table.

    This is what Workday's exporter does, and it is invisible in Excel because
    Excel ignores the element and reads the cells. openpyxl in read-only mode
    believes it. See :meth:`XlsxDimensionTests`.
    """
    import re
    import zipfile

    source = zipfile.ZipFile(buffer)
    out = io.BytesIO()
    target = zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED)
    for item in source.infolist():
        data = source.read(item.filename)
        if item.filename.startswith('xl/worksheets/sheet'):
            text = data.decode('utf-8')
            if '<dimension' in text:
                text = re.sub(r'<dimension[^/]*/>', '<dimension ref="%s"/>' % ref, text)
            else:
                text = text.replace('<sheetData>', '<dimension ref="%s"/><sheetData>' % ref)
            data = text.encode('utf-8')
        target.writestr(item, data)
    target.close()
    out.seek(0)
    return out


def workbook(rows, sheet_title='Sheet1', extra_sheets=()):
    """ An .xlsx in memory. ``rows`` are written as-is, so types are preserved. """
    from openpyxl import Workbook

    book = Workbook()
    sheet = book.active
    sheet.title = sheet_title
    for row in rows:
        sheet.append(list(row))
    for title, other_rows in extra_sheets:
        other = book.create_sheet(title)
        for row in other_rows:
            other.append(list(row))
    buffer = io.BytesIO()
    book.save(buffer)
    buffer.seek(0)
    return buffer


HEADER_CELLS = HEADER.split(',')
# The same expense as EXPENSE_ROW, but typed the way a spreadsheet holds it:
# a real date object and real numbers rather than formatted text.
TYPED_EXPENSE = [
    datetime.date(2025, 9, 15), 1200.0, 0.0, -1200.0, 'OT-1001', 'B&H Photo', '', 'JRN-88',
    'Lighting order', 'September purchases', '110-FD', 'CC-1234', '71100:Supplies', 'Supplies',
    '', '', '226-AG Lens & Light Club', 'Ops',
]


class XlsxDimensionTests(TestCase):
    """
    A workbook that understates its own size still imports.

    A read-only worksheet trusts the ``<dimension>`` element in the sheet XML
    and clips every row to that width. Workday's exporter writes one that
    understates the table, so every row arrived one cell wide, the header read
    simply "Accounting Date", and the importer insisted a perfectly good export
    was not one. Excel never showed a thing, because Excel ignores the element
    and reads the cells.
    """

    def _bad(self, ref='A1:A1'):
        return understate_dimensions(workbook([HEADER_CELLS, TYPED_EXPENSE]), ref=ref)

    def test_it_imports_despite_a_dimension_of_one_cell(self):
        result = import_workday_export(self._bad(), filename='journal.xlsx')
        self.assertEqual(result.error_count, 0)
        self.assertEqual(result.created_count, 1)
        txn = WorkdayTransaction.objects.get(operational_transaction='OT-1001')
        self.assertEqual(txn.net_amount, Decimal('-1200.00'))

    def test_every_column_survives_not_just_the_first(self):
        """ The symptom was truncation, so check the far end of the row. """
        import_workday_export(self._bad(), filename='journal.xlsx')
        txn = WorkdayTransaction.objects.get(operational_transaction='OT-1001')
        self.assertEqual(txn.worktags_json['program'], 'Ops')
        self.assertEqual(txn.worktags_json['student_organization'], '226-AG Lens & Light Club')

    def test_a_dimension_that_understates_only_the_row_count_is_fine_too(self):
        result = import_workday_export(self._bad(ref='A1:R1'), filename='journal.xlsx')
        self.assertEqual(result.created_count, 1)

    def test_an_honest_dimension_is_unaffected(self):
        result = import_workday_export(workbook([HEADER_CELLS, TYPED_EXPENSE]),
                                       filename='journal.xlsx')
        self.assertEqual(result.created_count, 1)


class XlsxImportTests(TestCase):
    """
    Workday hands out both formats, so both have to land in the same ledger.
    """

    def test_an_xlsx_imports(self):
        result = import_workday_export(workbook([HEADER_CELLS, TYPED_EXPENSE]),
                                       filename='journal.xlsx')
        self.assertEqual(result.error_count, 0)
        self.assertEqual(result.created_count, 1)
        txn = WorkdayTransaction.objects.get(operational_transaction='OT-1001')
        self.assertEqual(txn.net_amount, Decimal('-1200.00'))
        self.assertEqual(txn.accounting_date, datetime.date(2025, 9, 15))
        self.assertEqual(txn.supplier, 'B&H Photo')
        self.assertEqual(txn.memo, 'Lighting order — September purchases')
        self.assertEqual(txn.worktags_json['ledger_account'], '71100:Supplies')
        self.assertEqual(txn.source_file, 'journal.xlsx')

    def test_a_typed_date_needs_no_parsing(self):
        import_workday_export(workbook([HEADER_CELLS, TYPED_EXPENSE]))
        self.assertEqual(WorkdayTransaction.objects.get().accounting_date,
                         datetime.date(2025, 9, 15))

    def test_a_float_amount_does_not_pick_up_binary_noise(self):
        row = list(TYPED_EXPENSE)
        row[3] = -17.91                      # 17.91 has no exact float representation
        import_workday_export(workbook([HEADER_CELLS, row]))
        self.assertEqual(WorkdayTransaction.objects.get().net_amount, Decimal('-17.91'))

    def test_a_numeric_reference_does_not_gain_a_decimal_point(self):
        """ Excel stores every number as a float, so 25070087 must not become '25070087.0'. """
        row = list(TYPED_EXPENSE)
        row[4] = 25070087.0
        import_workday_export(workbook([HEADER_CELLS, row]))
        self.assertEqual(WorkdayTransaction.objects.get().operational_transaction, '25070087')

    def test_the_partition_default_applies_the_same(self):
        row = list(TYPED_EXPENSE)
        row[16] = '315-AG Projection'
        import_workday_export(workbook([HEADER_CELLS, row]))
        self.assertEqual(WorkdayTransaction.objects.get().default_partition, 'projection')

    def test_a_report_title_above_the_table_is_skipped(self):
        """ Workday's export-to-Excel puts the report name and its filters on top. """
        rows = [
            ['Find Journal Lines - Worcester Polytechnic Institute'],
            ['Company: WPI', 'Period: FY26'],
            [],
            HEADER_CELLS,
            TYPED_EXPENSE,
        ]
        result = import_workday_export(workbook(rows))
        self.assertEqual(result.created_count, 1)
        self.assertEqual(result.error_count, 0)

    def test_the_sheet_holding_the_table_is_found(self):
        """ A workbook may carry a summary tab before the data. """
        book = workbook(
            [['Summary'], ['Total', 1234]],
            sheet_title='Summary',
            extra_sheets=[('Journal Lines', [HEADER_CELLS, TYPED_EXPENSE])])
        result = import_workday_export(book)
        self.assertEqual(result.created_count, 1)

    def test_blank_trailing_rows_are_ignored(self):
        rows = [HEADER_CELLS, TYPED_EXPENSE, [], [None] * 18, []]
        result = import_workday_export(workbook(rows))
        self.assertEqual(result.created_count, 1)
        self.assertEqual(result.error_count, 0)

    def test_a_workbook_without_the_columns_is_refused(self):
        with self.assertRaises(ImportError_) as ctx:
            import_workday_export(workbook([['Name', 'Email'], ['foo', 'bar']]))
        self.assertIn("doesn't look like a Workday journal export", str(ctx.exception))

    def test_something_renamed_to_xlsx_is_refused_clearly(self):
        with self.assertRaises(ImportError_) as ctx:
            import_workday_export(io.BytesIO(b'not a workbook'), filename='journal.xlsx')
        self.assertIn('not a valid Excel workbook', str(ctx.exception))

    def test_a_workbook_named_csv_is_still_read(self):
        """ Dispatch is on the bytes, so a mislabelled upload still works. """
        result = import_workday_export(workbook([HEADER_CELLS, TYPED_EXPENSE]),
                                       filename='journal.csv')
        self.assertEqual(result.created_count, 1)

    def test_the_two_formats_produce_identical_rows(self):
        import_workday_export(upload(EXPENSE_ROW))
        from_csv = WorkdayTransaction.objects.get()
        WorkdayTransaction.objects.all().hard_delete()

        import_workday_export(workbook([HEADER_CELLS, TYPED_EXPENSE]))
        from_xlsx = WorkdayTransaction.objects.get()

        for field in ('accounting_date', 'net_amount', 'operational_transaction', 'supplier',
                      'employee', 'memo', 'worktags_json', 'row_fingerprint'):
            self.assertEqual(getattr(from_csv, field), getattr(from_xlsx, field), field)

    def test_the_same_export_in_the_other_format_is_a_duplicate(self):
        """
        The fingerprint is computed from the values, not the file, so uploading
        the CSV and then the workbook does not double the ledger.
        """
        import_workday_export(upload(EXPENSE_ROW))
        result = import_workday_export(workbook([HEADER_CELLS, TYPED_EXPENSE]))
        self.assertEqual(result.created_count, 0)
        self.assertEqual(result.duplicate_count, 1)
        self.assertEqual(WorkdayTransaction.objects.count(), 1)

    def test_dry_run_writes_nothing_from_a_workbook(self):
        result = import_workday_export(workbook([HEADER_CELLS, TYPED_EXPENSE]), dry_run=True)
        self.assertEqual(result.created_count, 1)
        self.assertEqual(WorkdayTransaction.objects.count(), 0)


class TypedCellTests(TestCase):
    """ parse_* accept what a spreadsheet hands back, not just text. """

    def test_native_numbers(self):
        self.assertEqual(parse_decimal(1200), Decimal('1200.00'))
        self.assertEqual(parse_decimal(-17.91), Decimal('-17.91'))
        self.assertEqual(parse_decimal(Decimal('3.5')), Decimal('3.50'))

    def test_a_boolean_is_not_a_number(self):
        self.assertIsNone(parse_decimal(True))

    def test_native_dates(self):
        self.assertEqual(parse_date(datetime.datetime(2025, 9, 15, 13, 30)),
                         datetime.date(2025, 9, 15))
        self.assertEqual(parse_date(datetime.date(2025, 9, 15)), datetime.date(2025, 9, 15))


class MisalignedRowTests(TestCase):
    """
    A row that did not split where the header did must not import.

    Drawn from a live incident. A memo reading  Stereo 1/4" cables for PCDI
    kits, Maintenance and Repair, (A.27.16)  met a CSV dialect that had guessed
    ``doublequote=False``, so it split at its own commas: the memo tail landed
    in Fund, and Fund, Cost Center, Ledger Account and Spend Category each
    shifted one column right while Student Organization and Program fell off
    the end. The row imported without complaint, was reconciled a fortnight
    later, and then imported *again* from the next export -- correctly parsed
    that time, so a different fingerprint, so not a duplicate.

    The dialect bug is fixed in :func:`_read_csv`. These tests cover the guard
    that makes the *class* of failure loud, whatever causes it next.
    """

    #: The same line, quoted the way the old dialect left it: two cells too wide.
    MISALIGNED = ('7/1/2025,17.91,0.00,(17.91),Supplier Invoice: 25070087-SINV,'
                  '"Amazon Capital Services, Inc.",,Operational Journal: WPI - 07/01/2025,'
                  'Stereo 1/4" cables for PCDI kits, Maintenance and Repair, (A.27.16)",,'
                  '810-FD Agency,1125-CC Student Clubs,71100:Supplies,Supplies,,,'
                  '226-AG Lens & Light Club,920 Agencies')

    def test_a_row_wider_than_the_header_is_an_error(self):
        result = import_workday_export(upload(self.MISALIGNED))
        self.assertEqual(result.created_count, 0)
        self.assertEqual(result.error_count, 1)
        self.assertEqual(WorkdayTransaction.objects.count(), 0)

    def test_the_error_says_what_overflowed(self):
        result = import_workday_export(upload(self.MISALIGNED))
        message = result.errors[0].message
        self.assertIn('more value', message)
        self.assertIn('920 Agencies', message)

    def test_one_bad_row_does_not_stop_the_rest_of_the_file(self):
        result = import_workday_export(upload(EXPENSE_ROW, self.MISALIGNED, REVENUE_ROW))
        self.assertEqual(result.created_count, 2)
        self.assertEqual(result.error_count, 1)

    def test_a_quoted_memo_with_commas_and_quotes_still_imports(self):
        """ The guard must not catch the well-formed version of the same line. """
        good = ('7/1/2025,17.91,0.00,(17.91),Supplier Invoice: 25070087-SINV,'
                '"Amazon Capital Services, Inc.",,Operational Journal: WPI - 07/01/2025,'
                '"Stereo 1/4"" cables for PCDI kits, Maintenance and Repair, (A.27.16)",,'
                '810-FD Agency,1125-CC Student Clubs,71100:Supplies,Supplies,,,'
                '226-AG Lens & Light Club,920 Agencies')
        result = import_workday_export(upload(good))
        self.assertEqual(result.created_count, 1, result.errors and result.errors[0].message)
        txn = WorkdayTransaction.objects.get()
        self.assertEqual(txn.worktags_json['fund'], '810-FD Agency')
        self.assertEqual(txn.worktags_json['cost_center'], '1125-CC Student Clubs')
        self.assertEqual(txn.worktags_json['student_organization'], '226-AG Lens & Light Club')
        self.assertIn('Maintenance and Repair', txn.memo)

    def test_trailing_empty_cells_are_not_an_overflow(self):
        """ A stray delimiter at the end of a line is ordinary, not corruption. """
        result = import_workday_export(upload(EXPENSE_ROW + ',,,'))
        self.assertEqual(result.created_count, 1)


class NearDuplicateTests(TestCase):
    """
    The warning for a line that is new by fingerprint but looks already held.

    The fingerprint is exact, so any drift in how a line is *read* -- a column
    Workday renamed, a memo edited upstream, a parser fixed -- reads as a fresh
    charge. That is the correct thing for the ledger to do and the wrong thing
    to do silently, so these rows import and are flagged.
    """

    def _drifted(self):
        """ The same charge with one worktag read differently. """
        return INVOICE_LINE_1.replace('920 Agencies', '921 Agencies')

    def test_a_line_differing_only_in_worktags_is_flagged(self):
        import_workday_export(upload(INVOICE_LINE_1))
        result = import_workday_export(upload(self._drifted()))
        self.assertEqual(result.created_count, 1)
        self.assertEqual(len(result.suspects), 1)

    def test_the_warning_names_the_row_it_resembles(self):
        import_workday_export(upload(INVOICE_LINE_1))
        held = WorkdayTransaction.objects.get()
        result = import_workday_export(upload(self._drifted()))
        self.assertIn('#%s' % held.pk, result.suspects[0].warning)

    def test_an_exact_duplicate_is_not_flagged(self):
        """ It is skipped, not warned about -- the ordinary case stays quiet. """
        import_workday_export(upload(INVOICE_LINE_1))
        result = import_workday_export(upload(INVOICE_LINE_1))
        self.assertEqual(result.suspects, [])

    def test_a_deliberate_second_identical_charge_is_not_flagged(self):
        """ Two Spotify charges share a fingerprint, so they are not a near miss. """
        result = import_workday_export(upload(SPOTIFY_ROW, SPOTIFY_ROW))
        self.assertEqual(result.created_count, 2)
        self.assertEqual(result.suspects, [])

    def test_two_lines_of_one_invoice_are_not_flagged(self):
        result = import_workday_export(upload(INVOICE_LINE_1, INVOICE_LINE_2))
        self.assertEqual(result.created_count, 2)
        self.assertEqual(result.suspects, [])

    def test_journal_entries_sharing_a_date_and_amount_are_not_flagged(self):
        """
        A journal line names neither document nor person, so date-and-amount is
        all there is to match on -- and one real October journal in this ledger
        holds four separate $100 projector rentals. Matching on that would cry
        wolf on every one of them.
        """
        other = JOURNAL_ENTRY_ROW.replace('306711: 11x17 posters for LNL',
                                          '306786: Posters V for Vendetta')
        result = import_workday_export(upload(JOURNAL_ENTRY_ROW, other))
        self.assertEqual(result.created_count, 2)
        self.assertEqual(result.suspects, [])

    def test_a_flagged_row_still_imports(self):
        """ A warning, never a block: it may genuinely be a second charge. """
        import_workday_export(upload(INVOICE_LINE_1))
        import_workday_export(upload(self._drifted()))
        self.assertEqual(WorkdayTransaction.objects.count(), 2)


class OrdinalNumberingTests(TestCase):
    """
    Occurrence numbers come from the highest one on file, not from the count.

    They disagree the moment ``hard_delete()`` removes anything but the last
    copy of a line, and numbering from the count then hands a new row a number
    a surviving row already holds -- which the unique constraint rejects,
    aborting the whole import inside its atomic block.
    """

    def test_re_import_after_deleting_the_first_occurrence(self):
        import_workday_export(upload(SPOTIFY_ROW, SPOTIFY_ROW))
        WorkdayTransaction.objects.filter(fingerprint_ordinal=1).hard_delete()

        result = import_workday_export(upload(SPOTIFY_ROW, SPOTIFY_ROW))

        self.assertEqual(result.created_count, 1)
        self.assertEqual(result.duplicate_count, 1)
        self.assertEqual(
            sorted(WorkdayTransaction.objects.values_list('fingerprint_ordinal', flat=True)),
            [2, 3])

    def test_a_one_off_insert_takes_the_next_free_occurrence(self):
        import_workday_export(upload(SPOTIFY_ROW, SPOTIFY_ROW))
        WorkdayTransaction.objects.filter(fingerprint_ordinal=1).hard_delete()
        held = WorkdayTransaction.objects.get()

        extra = WorkdayTransaction(
            operational_transaction=held.operational_transaction,
            accounting_date=held.accounting_date, net_amount=held.net_amount,
            supplier=held.supplier, employee=held.employee, memo=held.memo,
            worktags_json=held.worktags_json)
        extra.save()

        self.assertEqual(extra.row_fingerprint, held.row_fingerprint)
        self.assertEqual(extra.fingerprint_ordinal, 3)
