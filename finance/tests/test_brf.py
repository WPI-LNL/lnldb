"""
The Budget Report Form: SGA's proof of spending for the year's budget, one
payment request a line item. What goes on it -- SGA money and group funds,
the last day of spending, the receipts, the lines nothing was spent on -- and
the page, the PDFs and the undergraduates typed on it.
"""
import datetime
import io
import shutil
import tempfile
import zipfile
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse
from pypdf import PdfReader

from finance.brf import gather, line_pdf, save_answers
from finance.models import (BudgetCategory, FRLineItem, FundingKind, FundingRequest,
                            ParsedTransaction, TransactionStatus, WorkdayTransaction)
from finance.reports import as_csv, budget_report_form
from finance.tests.test_frrf import attach, jpeg
from finance.tests.test_views import FinanceViewTestCase
from finance.tests.util import category, fund

MAIN = '226-AG Lens & Light Club'


def workday(op, amount, day, memo='Gaff tape, consumables, (4521)', supplier='B&H Photo',
            employee=''):
    """ A Workday line in FY27: a supplier invoice, or an expense report given ``employee``. """
    return WorkdayTransaction.objects.create(
        operational_transaction=op, accounting_date=datetime.date(2026, 10, day),
        net_amount=Decimal(amount), supplier='' if employee else supplier, employee=employee,
        memo=memo, worktags_json={'student_organization': MAIN, 'journal_line_memo': memo,
                                  'ledger_account': '71100:Supplies'})


class BudgetFormMixin(object):
    """
    The FY27 budget: 4521 Gaff tape under Consumables, 4541 Film rights,
    4523 Gel (approved, nothing spent) and 4560 Gobos (pending). Receipts are
    stored in a folder of their own for each test.
    """

    def setUp(self):
        super(BudgetFormMixin, self).setUp()
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, True)
        storage = override_settings(MEDIA_ROOT=media)
        storage.enable()
        self.addCleanup(storage.disable)
        self.budget = FundingRequest.objects.create(kind=FundingKind.BUDGET, fiscal_year=2027,
                                                    name='FY27 SGA Budget')
        consumables = BudgetCategory.objects.create(funding_request=self.budget,
                                                    name='Consumables', sort_order=0)
        self.gaff = FRLineItem.objects.create(
            funding_request=self.budget, name='Gaff tape', number='4521', category=consumables,
            amount_awarded=Decimal('500.00'), description='Tape for every show')
        self.film = FRLineItem.objects.create(
            funding_request=self.budget, name='Film rights', number='4541', is_projection=True,
            amount_awarded=Decimal('3000.00'))
        self.gel = FRLineItem.objects.create(
            funding_request=self.budget, name='Gel', number='4523', category=consumables,
            amount_awarded=Decimal('300.00'), sort_order=5)
        self.gobos = FRLineItem.objects.create(funding_request=self.budget, name='Gobos',
                                               number='4560')

    def spend(self, line, amount, txn, fund_slug='sga_budget', **kwargs):
        return ParsedTransaction.objects.create(
            parent_transaction=txn, amount=-Decimal(amount), effective_date=txn.accounting_date,
            status=TransactionStatus.SETTLED, fund_source=fund(fund_slug), fr_line_target=line,
            lnl_spend_category=category('consumables'), description=kwargs.pop('description',
                                                                               txn.memo),
            **kwargs)


class GatherTests(BudgetFormMixin, TestCase):

    def test_sga_money_group_funds_and_the_last_day(self):
        early = workday('Supplier Invoice: 26100010-SIN', '-120.00', 2)
        self.spend(self.gaff, '120.00', early)
        shared = workday('Expense Report: 26100900-EXP', '-260.00', 18, employee='Alex Coyle')
        self.spend(self.gaff, '200.00', shared)
        # The club's own money on the same Workday line is the group's funds.
        self.spend(None, '60.00', shared, fund_slug='legacy')
        form = gather(self.budget)
        gaff = form.line(self.gaff.pk)
        self.assertEqual(gaff.sga, Decimal('320.00'))
        self.assertEqual(gaff.group, Decimal('60.00'))
        self.assertEqual(gaff.total, Decimal('380.00'))
        self.assertEqual(gaff.last_date, datetime.date(2026, 10, 18))
        self.assertEqual([p.group for p in gaff.purchases], [Decimal('0.00'), Decimal('60.00')])
        self.assertEqual(form.sga, Decimal('320.00'))
        self.assertEqual(form.group, Decimal('60.00'))

    def test_group_funds_are_counted_once_when_a_workday_line_covers_two_budget_lines(self):
        txn = workday('Supplier Invoice: 26100011-SIN', '-400.00', 3)
        self.spend(self.gaff, '100.00', txn)
        self.spend(self.film, '200.00', txn)
        self.spend(None, '100.00', txn, fund_slug='legacy')
        form = gather(self.budget)
        self.assertEqual(form.group, Decimal('100.00'))

    def test_lines_come_in_the_budgets_order_and_unspent_ones_are_named(self):
        self.spend(self.film, '1500.00', workday('Supplier Invoice: 26100020-SIN', '-1500.00', 9))
        form = gather(self.budget)
        # Consumables first (Gaff tape, Gel), then the line in no category.
        self.assertEqual([item.line for item in form.lines],
                         [self.gaff, self.gel, self.film, self.gobos])
        # Approved and nothing spent; Gobos is pending, so it isn't in the budget yet.
        self.assertEqual([item.line for item in form.unspent], [self.gaff, self.gel])
        self.assertEqual([item.line for item in form.spent_lines], [self.film])

    def test_encumbrances_are_left_out_and_counted(self):
        ParsedTransaction.objects.create(amount=Decimal('-75.00'), fund_source=fund('sga_budget'),
                                         fr_line_target=self.gaff,
                                         lnl_spend_category=category('consumables'))
        form = gather(self.budget)
        self.assertEqual(form.encumbered, Decimal('75.00'))
        self.assertFalse(form.line(self.gaff.pk).purchases)

    def test_receipts_are_numbered_line_by_line_and_shared_ones_go_in_each(self):
        txn = workday('Supplier Invoice: 26100012-SIN', '-300.00', 4)
        tape = self.spend(self.gaff, '100.00', txn)
        self.spend(self.film, '200.00', txn)
        attach(tape, 'order.jpg', jpeg())
        second = workday('Supplier Invoice: 26100013-SIN', '-50.00', 6)
        other = self.spend(self.film, '50.00', second)
        attach(other, 'second.jpg', jpeg())
        form = gather(self.budget)
        self.assertEqual([r.number for r in form.line(self.gaff.pk).receipts], [1])
        self.assertEqual([r.number for r in form.line(self.film.pk).receipts], [1, 2])
        self.assertEqual(form.receipt_count, 2)

    def test_a_receipt_covering_money_charged_elsewhere_is_flagged(self):
        txn = workday('Supplier Invoice: 26100014-SIN', '-300.00', 4)
        tape = self.spend(self.gaff, '100.00', txn)
        attach(tape, 'order.jpg', jpeg())
        self.spend(None, '200.00', txn, fund_slug='sga_mandatory')
        purchase = gather(self.budget).line(self.gaff.pk).purchases[0]
        # The mandatory transfer carries forward, so it is the group's money.
        self.assertEqual(purchase.group, Decimal('200.00'))
        self.assertEqual(purchase.charged_elsewhere, Decimal('0.00'))

        other = workday('Supplier Invoice: 26100015-SIN', '-300.00', 5)
        film = self.spend(self.film, '100.00', other)
        attach(film, 'film.jpg', jpeg())
        self.spend(self.gaff, '200.00', other)
        purchase = gather(self.budget).line(self.film.pk).purchases[0]
        self.assertEqual(purchase.charged_elsewhere, Decimal('200.00'))


class ReportTests(BudgetFormMixin, TestCase):

    def test_warnings_name_what_sga_would_refuse(self):
        self.spend(self.film, '1500.00',
                   workday('Expense Report: 26100900-EXP', '-1500.00', 9, employee='Alex'))
        report = budget_report_form(self.budget)
        text = ' '.join(report.warnings)
        self.assertIn("SGA cuts a line with none from next year's budget: 4521 Gaff tape, 4523 Gel",
                      text)
        self.assertIn('1 purchase has no receipt', text)
        self.assertNotIn('paid', text)
        self.assertIn("1 line doesn't say how many undergraduates benefited", text)
        # The unspent lines come first, then each line with spending.
        self.assertEqual([section.title for section in report.sections],
                         ["Nothing spent yet: SGA cuts these lines from next year's budget",
                          '4541 · Film rights'])

    def test_the_csv_has_both_amounts(self):
        txn = workday('Supplier Invoice: 26100010-SIN', '-150.00', 2)
        self.spend(self.gaff, '100.00', txn)
        self.spend(None, '50.00', txn, fund_slug='legacy')
        text = as_csv(budget_report_form(self.budget))
        self.assertIn('SGA money', text)
        self.assertIn('Group funds', text)
        self.assertIn('100.00,50.00', text)


class PdfTests(BudgetFormMixin, TestCase):

    def test_a_lines_pdf_has_sgas_questions_then_its_receipts(self):
        entry = self.spend(self.gaff, '120.00', workday('Supplier Invoice: 26100010-SIN',
                                                        '-120.00', 2))
        attach(entry, 'order.jpg', jpeg())
        self.gaff.undergraduates = 85
        self.gaff.save()
        form = gather(self.budget)
        reader = PdfReader(io.BytesIO(line_pdf(form, form.line(self.gaff.pk))))
        self.assertEqual(len(reader.pages), 2)
        front = reader.pages[0].extract_text()
        for words in ('Budget Report Form', '4521', 'Gaff tape', 'Expense',
                      'Tape for every show', 'SGA money spent', 'Group funds spent', '85',
                      'October 2, 2026'):
            self.assertIn(words, front)
        for words in ('How paid', 'Transaction type', 'Invoice'):
            self.assertNotIn(words, front)
        self.assertIn('Receipt 1 of 1', reader.pages[1].extract_text())
        self.assertEqual(form.line(self.gaff.pk).filename, 'lnl-budget-fy27-4521.pdf')


class SaveAnswersTests(BudgetFormMixin, FinanceViewTestCase):
    """ The undergraduates each line served, typed on the form's page. """

    def post(self, data, budget=None):
        return self.client.post(reverse('finance:budget-report-save',
                                        args=[(budget or self.budget).pk]), data)

    def test_the_treasurer_enters_undergraduates(self):
        self.grant('view_subledger', 'manage_fundingrequest')
        response = self.post({'undergraduates-%s' % self.gaff.pk: '120'})
        self.assertRedirects(response, reverse('finance:report', args=['budget-report-form'])
                             + '?budget=%s' % self.budget.pk, fetch_redirect_response=False)
        self.gaff.refresh_from_db()
        self.assertEqual(self.gaff.undergraduates, 120)

    def test_it_takes_permission_to_manage_funding_requests(self):
        self.grant('view_subledger', 'edit_subledger')
        self.assertEqual(self.post({'undergraduates-%s' % self.gaff.pk: '120'}).status_code, 403)
        self.gaff.refresh_from_db()
        self.assertIsNone(self.gaff.undergraduates)

    def test_a_bad_count_is_refused_and_the_rest_saved(self):
        saved, problems = save_answers(gather(self.budget), {
            'undergraduates-%s' % self.gaff.pk: 'lots',
            'undergraduates-%s' % self.film.pk: '40'})
        self.assertEqual((saved, len(problems)), (1, 1))
        self.film.refresh_from_db()
        self.assertEqual(self.film.undergraduates, 40)

    def test_lines_of_another_budget_are_not_touched(self):
        self.grant('view_subledger', 'manage_fundingrequest')
        other = FundingRequest.objects.create(kind=FundingKind.BUDGET, fiscal_year=2026,
                                              name='FY26 SGA Budget')
        self.post({'undergraduates-%s' % self.gaff.pk: '120'}, budget=other)
        self.gaff.refresh_from_db()
        self.assertIsNone(self.gaff.undergraduates)


class PageTests(BudgetFormMixin, FinanceViewTestCase):

    def setUp(self):
        super(PageTests, self).setUp()
        self.grant('view_subledger', 'edit_subledger', 'manage_fundingrequest')
        entry = self.spend(self.gaff, '120.00', workday('Supplier Invoice: 26100010-SIN',
                                                        '-120.00', 2))
        attach(entry, 'order.jpg', jpeg())
        self.url = reverse('finance:report', args=['budget-report-form'])

    def test_listed_on_the_reports_tab(self):
        self.assertContains(self.client.get(reverse('finance:reports')), 'Budget Report Form')

    def test_the_page_asks_sgas_questions(self):
        response = self.client.get(self.url + '?budget=%s' % self.budget.pk)
        self.assertContains(response, 'Save answers')
        self.assertContains(response, 'name="undergraduates-%s"' % self.gaff.pk)
        self.assertNotContains(response, 'How paid')
        self.assertContains(response, '4523')
        self.assertNotContains(response, 'format=zip')

    def test_the_budgets_page_links_here(self):
        self.grant('view_fundingrequest')
        response = self.client.get(reverse('finance:fr-detail', args=[self.budget.pk]))
        self.assertContains(response, 'budget-report-form/?budget=%s' % self.budget.pk)

    def test_the_pdfs_need_permission_to_see_receipts(self):
        query = '?budget=%s&format=pdf&line=%s' % (self.budget.pk, self.gaff.pk)
        self.assertEqual(self.client.get(self.url + query).status_code, 403)
        self.grant('view_subledger_receipts')
        response = self.client.get(self.url + query)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn('lnl-budget-fy27-4521.pdf', response['Content-Disposition'])

    def test_the_zip_has_one_pdf_a_line_with_spending(self):
        self.grant('view_subledger_receipts')
        page = self.client.get(self.url + '?budget=%s' % self.budget.pk)
        self.assertContains(page, 'format=zip')
        response = self.client.get(self.url + '?budget=%s&format=zip' % self.budget.pk)
        self.assertEqual(response['Content-Type'], 'application/zip')
        names = zipfile.ZipFile(io.BytesIO(response.content)).namelist()
        self.assertEqual(names, ['lnl-budget-fy27-4521.pdf'])

    def test_a_line_of_another_budget_is_not_found(self):
        self.grant('view_subledger_receipts')
        query = '?budget=%s&format=pdf&line=999999' % self.budget.pk
        self.assertEqual(self.client.get(self.url + query).status_code, 404)

    def test_the_filter_years_budget_is_chosen(self):
        response = self.client.get(self.url + '?fy=2027')
        self.assertEqual(response.context['budget'], self.budget)

    def test_no_budget_says_so(self):
        ParsedTransaction.objects.all().delete()
        FundingRequest.objects.all().delete()
        response = self.client.get(self.url)
        self.assertContains(response, 'There is no budget yet')
