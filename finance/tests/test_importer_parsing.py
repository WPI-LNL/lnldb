"""
The parsing layer of the importer, exercised directly.

Workday's export dialect drifts, and every helper here exists because a real
file broke on it: a UTF-8 BOM, negatives in parentheses, thousands separators,
non-breaking spaces in headers, tab separators, a report title above the table,
several worksheets in one workbook, and cells that arrive already typed.

These are unit tests on the functions rather than round trips through the view,
because the failure they guard against is silent. A misparsed number does not
raise; it imports a different amount, and nothing downstream can tell.
"""
import datetime
import io
from decimal import Decimal

from django.test import TestCase

from finance.importers import (ImportError_, ImportResult, RowResult, _decode, _find_header,
                               _text, build_memo, import_workday_export, normalise_header,
                               parse_date, parse_decimal, read_table)
from finance.models import ColumnAlias, WorkdayTransaction, reset_finance_cache
from finance.tests.test_importers import HEADER_CELLS, TYPED_EXPENSE, workbook


class TextCoercionTests(TestCase):
    """ One cell as trimmed text, whatever type it arrived as. """

    def test_a_string_is_trimmed(self):
        self.assertEqual(_text('  Supplies  '), 'Supplies')

    def test_a_non_breaking_space_is_an_ordinary_one(self):
        """ Workday pads headers with them; they are invisible and not equal. """
        self.assertEqual(_text('Spend\xa0Category'), 'Spend Category')

    def test_none_is_empty_rather_than_the_word_none(self):
        self.assertEqual(_text(None), '')

    def test_a_datetime_becomes_a_plain_date(self):
        self.assertEqual(_text(datetime.datetime(2025, 9, 15, 14, 30)), '2025-09-15')

    def test_a_date_becomes_its_iso_form(self):
        self.assertEqual(_text(datetime.date(2025, 9, 15)), '2025-09-15')

    def test_a_whole_float_loses_its_decimal_point(self):
        """
        Excel stores every number as a float, so an Operational Transaction of
        25070087 arrives as 25070087.0 -- and an id with a ``.0`` on the end
        matches nothing and silently splits a line's identity in two.
        """
        self.assertEqual(_text(25070087.0), '25070087')

    def test_a_fractional_float_keeps_its_value(self):
        self.assertEqual(_text(17.91), '17.91')

    def test_anything_else_is_stringified(self):
        self.assertEqual(_text(Decimal('12.50')), '12.50')


class HeaderNormalisationTests(TestCase):
    def test_case_and_spacing_are_ignored(self):
        self.assertEqual(normalise_header('  Credit Minus Debit '), 'credit_minus_debit')

    def test_a_byte_order_mark_is_stripped(self):
        """ Workday's CSV opens with one, invisibly renaming the first column. """
        self.assertEqual(normalise_header('﻿Accounting Date'), 'accounting_date')

    def test_punctuation_is_collapsed(self):
        self.assertEqual(normalise_header('Credit - Debit'), 'credit_minus_debit')

    def test_none_is_an_empty_header(self):
        self.assertEqual(normalise_header(None), '')

    def test_an_unknown_column_keeps_a_usable_name(self):
        self.assertEqual(normalise_header('Reconciliation Note'), 'reconciliation_note')

    def test_an_alias_added_in_the_admin_wins(self):
        """
        The point of the table: Workday relabelling a column is a row here
        rather than a deploy.
        """
        ColumnAlias.objects.create(canonical='student_organization',
                                   alias='Student Org Code')
        reset_finance_cache('column_aliases')
        self.addCleanup(reset_finance_cache, 'column_aliases')
        self.assertEqual(normalise_header('Student Org Code'), 'student_organization')


class DecimalParsingTests(TestCase):
    """ Workday's money formatting, in every shape it has actually arrived in. """

    def test_a_plain_number(self):
        self.assertEqual(parse_decimal('1200'), Decimal('1200.00'))

    def test_thousands_separators_and_a_currency_symbol(self):
        self.assertEqual(parse_decimal('$1,200.00'), Decimal('1200.00'))

    def test_parentheses_mean_negative(self):
        """ Accounting notation, and the only marker on a debit line. """
        self.assertEqual(parse_decimal('(1,200.00)'), Decimal('-1200.00'))

    def test_a_leading_minus_also_means_negative(self):
        self.assertEqual(parse_decimal('-1,200.00'), Decimal('-1200.00'))

    def test_a_trailing_currency_code_is_ignored(self):
        self.assertEqual(parse_decimal('1,200.00 USD'), Decimal('1200.00'))

    def test_an_already_typed_number_needs_no_parsing(self):
        self.assertEqual(parse_decimal(1200), Decimal('1200.00'))
        self.assertEqual(parse_decimal(Decimal('1200')), Decimal('1200.00'))

    def test_a_float_goes_through_its_string_form(self):
        """ Otherwise 17.91 becomes 17.910000000000000142. """
        self.assertEqual(parse_decimal(17.91), Decimal('17.91'))

    def test_an_empty_cell_is_no_value_rather_than_zero(self):
        self.assertIsNone(parse_decimal(''))
        self.assertIsNone(parse_decimal('   '))
        self.assertIsNone(parse_decimal(None))

    def test_a_boolean_is_not_a_number(self):
        """ ``isinstance(True, int)`` is True in Python; it must not become 1.00. """
        self.assertIsNone(parse_decimal(True))

    def test_punctuation_alone_is_not_a_number(self):
        for value in ('-', '.', '-.', 'n/a'):
            self.assertIsNone(parse_decimal(value), value)


class DateParsingTests(TestCase):
    def test_the_formats_workday_writes(self):
        for value in ('09/15/2025', '2025-09-15', '09/15/25', 'Sep 15, 2025', '09-15-2025'):
            self.assertEqual(parse_date(value), datetime.date(2025, 9, 15), value)

    def test_a_timestamp_keeps_only_the_date(self):
        self.assertEqual(parse_date('09/15/2025 14:30:00'), datetime.date(2025, 9, 15))

    def test_an_already_typed_date_needs_no_parsing(self):
        self.assertEqual(parse_date(datetime.date(2025, 9, 15)), datetime.date(2025, 9, 15))
        self.assertEqual(parse_date(datetime.datetime(2025, 9, 15, 14, 30)),
                         datetime.date(2025, 9, 15))

    def test_an_empty_cell_is_no_date(self):
        self.assertIsNone(parse_date(''))
        self.assertIsNone(parse_date(None))

    def test_something_unreadable_is_no_date_rather_than_a_guess(self):
        """ A wrong date files money in the wrong fiscal year, silently. """
        self.assertIsNone(parse_date('the fifteenth'))


class MemoTests(TestCase):
    def test_the_two_memos_are_joined(self):
        self.assertEqual(
            build_memo({'journal_line_memo': 'Gaff tape', 'header_memo': 'September'}),
            'Gaff tape — September')

    def test_a_repeated_memo_is_not_said_twice(self):
        self.assertEqual(build_memo({'journal_line_memo': 'Gaff tape',
                                     'header_memo': 'Gaff tape'}), 'Gaff tape')

    def test_either_half_may_be_missing(self):
        self.assertEqual(build_memo({'journal_line_memo': 'Gaff tape'}), 'Gaff tape')
        self.assertEqual(build_memo({'header_memo': 'September'}), 'September')
        self.assertEqual(build_memo({}), '')


class DecodingTests(TestCase):
    """ Whatever encoding the file arrived in, the importer reads text. """

    def test_utf8_with_a_byte_order_mark(self):
        """ Workday's CSV opens with one, invisibly renaming the first column. """
        self.assertEqual(_decode(io.BytesIO(b'\xef\xbb\xbfAccounting Date')),
                         'Accounting Date')

    def test_plain_utf8(self):
        self.assertEqual(_decode(io.BytesIO('Café'.encode('utf-8'))), 'Café')

    def test_windows_codepage(self):
        """ What Excel writes on a Windows machine when asked for CSV. """
        self.assertEqual(_decode(io.BytesIO('Café'.encode('cp1252'))), 'Café')

    def test_a_string_is_passed_straight_through(self):
        self.assertEqual(_decode(io.StringIO('already text')), 'already text')

    def test_undecodable_bytes_do_not_stop_the_import(self):
        """ One bad byte must not cost the other three hundred lines. """
        text = _decode(io.BytesIO(b'Accounting Date\xff\xfe'))
        self.assertIn('Accounting Date', text)


class TableReadingTests(TestCase):
    """ Both formats reduced to the same rows-of-cells shape. """

    def _csv(self, body, name='journal.csv'):
        return read_table(io.BytesIO(body.encode('utf-8')), name)

    def test_a_comma_separated_file(self):
        header, rows = self._csv('Accounting Date,Credit Minus Debit,Operational Transaction\n'
                                 '09/15/2025,(40.00),OT-1\n')
        self.assertEqual(len(header), 3)
        self.assertEqual(len(rows), 1)

    def test_a_tab_separated_file(self):
        """ Workday hands these out too, without changing the extension. """
        header, rows = self._csv(
            'Accounting Date\tCredit Minus Debit\tOperational Transaction\n'
            '09/15/2025\t(40.00)\tOT-1\n')
        self.assertEqual(len(header), 3)

    def test_a_report_title_above_the_table_is_skipped(self):
        """ Workday's export-to-Excel puts the report name and filters on top. """
        header, rows = self._csv(
            'Find Journal Lines\n'
            'Company: WPI\n'
            '\n'
            'Accounting Date,Credit Minus Debit,Operational Transaction\n'
            '09/15/2025,(40.00),OT-1\n')
        self.assertEqual(header[0], 'Accounting Date')
        self.assertEqual(len(rows), 1)

    def test_line_numbers_count_as_a_text_editor_does(self):
        """ So "line 5" in a warning is line 5 when somebody opens the file. """
        header, rows = self._csv(
            'Find Journal Lines\n'
            'Accounting Date,Credit Minus Debit,Operational Transaction\n'
            '09/15/2025,(40.00),OT-1\n')
        self.assertEqual(rows[0][0], 3)

    def test_an_embedded_newline_inside_a_quoted_memo_stays_one_row(self):
        header, rows = self._csv(
            'Accounting Date,Credit Minus Debit,Operational Transaction,Journal Line Memo\n'
            '09/15/2025,(40.00),OT-1,"first line\nsecond line"\n')
        self.assertEqual(len(rows), 1)

    def test_a_quoted_double_quote_survives(self):
        """
        Only the delimiter is sniffed, never the whole dialect: the sniffer
        guessed ``doublequote=False`` on the real FY26 export and a memo
        reading ``Planar 22" touchscreen`` came back with a stray quote.
        """
        header, rows = self._csv(
            'Accounting Date,Credit Minus Debit,Operational Transaction,Journal Line Memo\n'
            '09/15/2025,(40.00),OT-1,"Planar 22"" touchscreen"\n')
        self.assertIn('Planar 22" touchscreen', rows[0][1])

    def test_an_empty_file_says_so(self):
        with self.assertRaises(ImportError_) as caught:
            self._csv('')
        self.assertIn('empty', str(caught.exception))

    def test_a_file_with_no_header_row_says_what_it_looked_at(self):
        """ Naming the row it found beats "row 1 was a title". """
        with self.assertRaises(ImportError_) as caught:
            self._csv('Name,Email\nfoo,bar\n')
        self.assertIn('Name', str(caught.exception))

    def test_no_rows_at_all_is_reported(self):
        with self.assertRaises(ImportError_) as caught:
            _find_header([])
        self.assertIn('no rows', str(caught.exception))

    def test_format_is_decided_by_the_bytes_not_the_name(self):
        """ A workbook saved as .csv is a common and otherwise silent mistake. """
        book = workbook([HEADER_CELLS, TYPED_EXPENSE])
        header, rows = read_table(book, 'journal.csv')
        self.assertEqual(header[0], 'Accounting Date')

    def test_a_file_named_xlsx_that_is_not_one_is_refused_clearly(self):
        with self.assertRaises(ImportError_) as caught:
            read_table(io.BytesIO(b'Accounting Date,x\n1,2\n'), 'journal.xlsx')
        self.assertIn('not a valid Excel workbook', str(caught.exception))

    def test_an_unopenable_workbook_is_reported_not_raised_raw(self):
        with self.assertRaises(ImportError_) as caught:
            read_table(io.BytesIO(b'PK\x03\x04 corrupted'), 'journal.xlsx')
        self.assertIn('could not be opened', str(caught.exception))


class WorkbookSheetTests(TestCase):
    """ A workbook may carry more than one sheet; the journal has to be found. """

    def test_the_sheet_holding_the_journal_wins(self):
        book = workbook(
            [['Summary'], ['Total', 1234]], sheet_title='Summary',
            extra_sheets=[('Journal', [HEADER_CELLS, TYPED_EXPENSE])])
        result = import_workday_export(book, filename='journal.xlsx')
        self.assertEqual(result.created_count, 1)

    def test_a_workbook_with_no_data_says_so(self):
        book = workbook([])
        with self.assertRaises(ImportError_) as caught:
            read_table(book, 'journal.xlsx')
        self.assertIn('no data', str(caught.exception))

    def test_a_workbook_with_data_but_no_journal_reports_the_likeliest_row(self):
        book = workbook([['Name', 'Email'], ['foo', 'bar']])
        with self.assertRaises(ImportError_) as caught:
            read_table(book, 'journal.xlsx')
        self.assertIn('Name', str(caught.exception))


class RequiredColumnTests(TestCase):
    def test_a_missing_required_column_names_it_and_what_was_found(self):
        body = ('Accounting Date,Credit Minus Debit\n09/15/2025,(40.00)\n')
        with self.assertRaises(ImportError_) as caught:
            import_workday_export(io.BytesIO(body.encode('utf-8')), filename='journal.csv')
        message = str(caught.exception)
        self.assertIn('Operational Transaction', message)
        self.assertIn('Accounting Date', message)

    def test_a_short_row_is_padded_rather_than_raising(self):
        """ Workday truncates trailing empty cells; that is not a broken row. """
        body = ('Accounting Date,Credit Minus Debit,Operational Transaction,Supplier\n'
                '09/15/2025,(40.00),OT-SHORT\n')
        result = import_workday_export(io.BytesIO(body.encode('utf-8')),
                                       filename='journal.csv')
        self.assertEqual(result.created_count, 1)
        self.assertEqual(
            WorkdayTransaction.objects.get(operational_transaction='OT-SHORT').supplier, '')


class ImportResultTests(TestCase):
    """ The tally an import reports back. """

    def test_it_counts_each_outcome(self):
        result = ImportResult(filename='journal.csv')
        result.add(RowResult(2, RowResult.CREATED))
        result.add(RowResult(3, RowResult.DUPLICATE, 'already on file'))
        result.add(RowResult(4, RowResult.ERROR, 'unreadable'))
        self.assertEqual((result.created_count, result.duplicate_count, result.error_count),
                         (1, 1, 1))
        self.assertEqual(result.total, 3)

    def test_a_file_with_an_error_is_not_ok(self):
        result = ImportResult()
        result.add(RowResult(2, RowResult.CREATED))
        self.assertTrue(result.ok)
        result.add(RowResult(3, RowResult.ERROR, 'unreadable'))
        self.assertFalse(result.ok)

    def test_the_summary_names_all_three_numbers(self):
        result = ImportResult()
        result.add(RowResult(2, RowResult.CREATED))
        self.assertEqual(result.summary(), '1 imported, 0 skipped as duplicates, 0 errors')

    def test_only_error_rows_are_listed_as_errors(self):
        result = ImportResult()
        result.add(RowResult(2, RowResult.CREATED))
        bad = RowResult(3, RowResult.ERROR, 'unreadable')
        result.add(bad)
        self.assertEqual(result.errors, [bad])
