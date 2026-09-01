"""
The template filters and tags every finance page renders through.

These are small, but they run inside templates, where an exception is not a
traceback next to the mistake -- it is a blank page or a swallowed error in the
middle of a report. So each one is tested for the ordinary case *and* for the
rubbish it might be handed: ``None`` from an empty aggregate, a string that is
not a number, a zero denominator. Every one of them is written to degrade to
something printable rather than raise, and that is the property under test.
"""
import datetime
import os
from decimal import Decimal

from django.test import RequestFactory, TestCase, override_settings

from finance.models import ParsedTransaction, TransactionStatus, WorkdayTransaction
from finance.templatetags.finance_extras import (abs_value, asset, autocomplete_media,
                                                 burndown_bar, entry_badge, filter_url,
                                                 get_item, indent_px, money, money_class,
                                                 percent_of, sort_indicator, sort_url,
                                                 status_badge)
from finance.tests.util import category, fund


class MoneyFilterTests(TestCase):
    """ Accounting style: negatives in parentheses, as beside a Workday export. """

    def test_a_positive_amount(self):
        self.assertEqual(money(Decimal('1234.50')), '$1,234.50')

    def test_a_negative_amount_is_parenthesised(self):
        self.assertEqual(money(Decimal('-1234.50')), '($1,234.50)')

    def test_zero_is_not_negative(self):
        self.assertEqual(money(Decimal('0.00')), '$0.00')

    def test_the_sign_can_be_forced_for_a_delta(self):
        self.assertEqual(money(Decimal('12.00'), show_sign=True), '+$12.00')

    def test_it_always_shows_two_decimal_places(self):
        self.assertEqual(money(Decimal('5')), '$5.00')

    def test_float_noise_is_rounded_away(self):
        """ Belt and braces behind :func:`finance.models.money`. """
        self.assertEqual(money(Decimal('2808.24000000000')), '$2,808.24')

    def test_nothing_renders_as_a_dash_not_as_zero(self):
        """ An empty cell and a zero balance are different facts. """
        self.assertEqual(money(None), '—')
        self.assertEqual(money(''), '—')

    def test_something_unparseable_is_passed_through(self):
        """ Better to print the odd value than to blank the page around it. """
        self.assertEqual(money('not a number'), 'not a number')

    def test_a_plain_number_is_accepted(self):
        self.assertEqual(money(12), '$12.00')


class MoneyClassTests(TestCase):
    def test_the_colour_follows_the_sign(self):
        self.assertEqual(money_class(Decimal('1.00')), 'text-success')
        self.assertEqual(money_class(Decimal('-1.00')), 'text-danger')
        self.assertEqual(money_class(Decimal('0.00')), 'text-muted')

    def test_rubbish_gets_no_class_rather_than_an_exception(self):
        self.assertEqual(money_class('elephant'), '')
        self.assertEqual(money_class(None), '')


class AbsValueTests(TestCase):
    def test_it_drops_the_sign(self):
        self.assertEqual(abs_value(Decimal('-40.00')), Decimal('40.00'))

    def test_rubbish_is_passed_through(self):
        self.assertEqual(abs_value('elephant'), 'elephant')


class PercentOfTests(TestCase):
    def test_an_ordinary_share(self):
        self.assertEqual(percent_of(Decimal('25'), Decimal('100')), 25)

    def test_it_rounds_to_a_whole_percent(self):
        self.assertEqual(percent_of(Decimal('1'), Decimal('3')), 33)

    def test_a_zero_denominator_is_zero_not_a_crash(self):
        """ An empty period is the normal state of a fresh fiscal year. """
        self.assertEqual(percent_of(Decimal('25'), Decimal('0')), 0)

    def test_it_is_clamped_to_the_bar_it_draws(self):
        """ The result is a CSS width; over 100 would overflow its track. """
        self.assertEqual(percent_of(Decimal('250'), Decimal('100')), 100)
        self.assertEqual(percent_of(Decimal('-250'), Decimal('100')), 0)

    def test_rubbish_is_zero(self):
        self.assertEqual(percent_of('elephant', 'giraffe'), 0)


class BurndownBarTests(TestCase):
    """ Green remaining, red spent, and an overspend that refuses to hide. """

    def test_a_partly_spent_award(self):
        html = burndown_bar(Decimal('250'), Decimal('1000'))
        self.assertIn('width:25%', html)
        self.assertIn('width:75%', html)

    def test_an_overspend_is_named_rather_than_clamped(self):
        """ A bar that silently stops at 100% hides the one case that matters. """
        html = burndown_bar(Decimal('1200'), Decimal('1000'))
        self.assertIn('Over by $200.00', html)
        self.assertIn('progress-bar-danger', html)

    def test_an_award_of_nothing_reads_as_fully_spent(self):
        html = burndown_bar(Decimal('10'), Decimal('0'))
        self.assertIn('progress-bar-danger', html)
        self.assertIn('width:100%', html)

    def test_a_fully_spent_award_is_all_red(self):
        html = burndown_bar(Decimal('1000'), Decimal('1000'))
        self.assertIn('width:100%', html)

    def test_rubbish_renders_nothing_rather_than_raising(self):
        self.assertEqual(burndown_bar('elephant', 'giraffe'), '')

    def test_the_amounts_are_escaped_into_the_markup(self):
        """ ``format_html`` throughout, so a value can never inject markup. """
        html = burndown_bar(Decimal('250'), Decimal('1000'))
        self.assertNotIn('<script', html)


class BadgeTests(TestCase):
    def setUp(self):
        self.txn = WorkdayTransaction.objects.create(
            operational_transaction='OT-T1', accounting_date=datetime.date(2025, 9, 15),
            net_amount=Decimal('-40.00'))

    def _entry(self, **kwargs):
        defaults = dict(parent_transaction=self.txn, amount=Decimal('-40.00'),
                        effective_date=self.txn.accounting_date,
                        fund_source=fund('sga_budget'),
                        lnl_spend_category=category('consumables'))
        defaults.update(kwargs)
        return ParsedTransaction.objects.create(**defaults)

    def test_each_entry_type_gets_its_own_word_and_colour(self):
        expense = self._entry()
        self.assertIn('Expense', entry_badge(expense))
        self.assertIn('label-default', entry_badge(expense))

        encumbrance = self._entry(parent_transaction=None)
        self.assertIn('Encumbrance', entry_badge(encumbrance))
        self.assertIn('label-warning', entry_badge(encumbrance))

        credit_txn = WorkdayTransaction.objects.create(
            operational_transaction='OT-T2', accounting_date=datetime.date(2025, 9, 20),
            net_amount=Decimal('40.00'))
        refund = self._entry(parent_transaction=credit_txn, amount=Decimal('40.00'),
                             refund_of=expense)
        self.assertIn('Refund', entry_badge(refund))
        self.assertIn('label-info', entry_badge(refund))

    def test_revenue_is_green(self):
        from finance.models import RevenueSource
        income_txn = WorkdayTransaction.objects.create(
            operational_transaction='OT-T3', accounting_date=datetime.date(2025, 9, 20),
            net_amount=Decimal('500.00'))
        income = ParsedTransaction.objects.create(
            parent_transaction=income_txn, amount=Decimal('500.00'),
            effective_date=income_txn.accounting_date,
            non_event_revenue_type=RevenueSource.objects.active().first())
        self.assertIn('Revenue', entry_badge(income))
        self.assertIn('label-success', entry_badge(income))

    def test_the_status_badge_distinguishes_settled_from_pending(self):
        entry = self._entry()
        self.assertIn('Pending', status_badge(entry))
        entry.status = TransactionStatus.SETTLED
        self.assertIn('Settled', status_badge(entry))


class SmallHelperTests(TestCase):
    def test_get_item_reads_a_dictionary_in_a_template(self):
        self.assertEqual(get_item({'a': 1}, 'a'), 1)

    def test_get_item_on_a_missing_key_is_none(self):
        self.assertIsNone(get_item({'a': 1}, 'b'))

    def test_get_item_on_something_that_is_not_a_mapping_is_none(self):
        """ Templates silence exceptions, so this must not become a blank page. """
        self.assertIsNone(get_item(None, 'a'))
        self.assertIsNone(get_item('a string', 'a'))

    def test_indent_px_scales_the_tree_depth(self):
        self.assertEqual(indent_px(0), 0)
        self.assertEqual(indent_px(2), 36)

    def test_indent_px_on_rubbish_is_flat(self):
        self.assertEqual(indent_px(None), 0)
        self.assertEqual(indent_px('deep'), 0)


class AssetStampTests(TestCase):
    """
    The cache buster. A stamp that does not change when the file does is worse
    than none: a stale script looks exactly like a button that does nothing.
    """

    def test_in_development_it_follows_the_file(self):
        from django.contrib.staticfiles import finders
        with override_settings(DEBUG=True):
            url = asset('js/queue.js')
        mtime = int(os.path.getmtime(finders.find('js/queue.js')))
        self.assertEqual(url, '/static/js/queue.js?v=%s' % mtime)

    def test_in_production_it_is_the_release(self):
        """ Files only change when a deploy does, so no file is stat'd. """
        with override_settings(DEBUG=False, GIT_RELEASE='abc123'):
            self.assertEqual(asset('js/queue.js'), '/static/js/queue.js?v=abc123')

    def test_a_production_build_with_no_release_still_produces_a_url(self):
        with override_settings(DEBUG=False, GIT_RELEASE=''):
            self.assertEqual(asset('js/queue.js'), '/static/js/queue.js')

    def test_a_missing_file_still_produces_a_url(self):
        """ A broken <script> tag beats a 500 on the page that includes it. """
        with override_settings(DEBUG=True):
            self.assertEqual(asset('js/not-here.js'), '/static/js/not-here.js')


class FilterUrlTests(TestCase):
    """ The tags that rebuild the current URL for the filter bar and sorting. """

    def test_filter_url_without_a_filter_state_is_inert(self):
        """ Rendered on pages that have no filter bar; must not raise there. """
        self.assertEqual(filter_url({}), '?')

    def _state(self, query='?fy=2026&partition=projection'):
        from finance.filters import get_filter_state
        request = RequestFactory().get('/' + query)
        request.session = {}
        return get_filter_state(request)

    def test_filter_url_swaps_one_value_and_keeps_the_rest(self):
        url = filter_url({'filter_state': self._state()}, fiscal_year=2025)
        self.assertIn('fy=2025', url)
        self.assertIn('partition=projection', url)

    def test_filter_url_can_clear_the_year(self):
        """ "All years" is a value, not an absent one; see ``FilterState``. """
        url = filter_url({'filter_state': self._state()}, fiscal_year='')
        self.assertIn('fy=all', url)

    def test_an_unknown_filter_name_is_refused_rather_than_ignored(self):
        """
        ``fy=`` is the querystring name and ``fiscal_year=`` is the keyword. A
        template reaching for the wrong one used to render a link that looked
        right, went somewhere real, and changed nothing.
        """
        with self.assertRaises(TypeError) as caught:
            filter_url({'filter_state': self._state()}, fy=2025)
        self.assertIn('fiscal_year', str(caught.exception))

    def test_sort_url_toggles_direction_on_the_current_column(self):
        request = RequestFactory().get('/?sort=date&dir=desc')
        self.assertIn('dir=asc', sort_url({'request': request}, 'date'))

    def test_sort_url_starts_a_new_column_descending(self):
        """ Newest and largest first is what a ledger is read for. """
        request = RequestFactory().get('/?sort=date&dir=asc')
        self.assertIn('dir=desc', sort_url({'request': request}, 'amount'))

    def test_sort_url_drops_the_page_number(self):
        """ Page 4 of the old order is not page 4 of the new one. """
        request = RequestFactory().get('/?sort=date&dir=desc&page=4')
        self.assertNotIn('page=', sort_url({'request': request}, 'amount'))

    def test_the_arrow_appears_only_on_the_sorted_column(self):
        request = RequestFactory().get('/?sort=amount&dir=asc')
        self.assertIn('fin-sort-arrow', sort_indicator({'request': request}, 'amount'))
        self.assertEqual(sort_indicator({'request': request}, 'date'), '')

    def test_the_arrow_points_the_way_the_column_is_sorted(self):
        ascending = RequestFactory().get('/?sort=amount&dir=asc')
        descending = RequestFactory().get('/?sort=amount&dir=desc')
        self.assertIn('9650', sort_indicator({'request': ascending}, 'amount'))
        self.assertIn('9660', sort_indicator({'request': descending}, 'amount'))


class AutocompleteMediaTests(TestCase):
    """
    The scripts that make the "Link to Event" box do anything at all.

    django-ajax-selects renders a plain text input plus a hidden field of data
    attributes; ``ajax_select.js`` is what turns that into an autocomplete. The
    finance pages could not run it to completion, so the box accepted typing
    and searched nothing -- and looked entirely normal while doing so. There is
    no visible symptom to assert on, which is exactly why the assets have to be
    asserted on directly.

    Two properties matter and they pull in opposite directions: the scripts
    must all be here, and the stylesheets must not be. See
    :func:`~finance.templatetags.finance_extras.autocomplete_media`.
    """

    def test_it_includes_the_ajax_select_script(self):
        self.assertIn('ajax_select/js/ajax_select.js', str(autocomplete_media()))

    def test_it_includes_the_bundled_jquery_ui_script(self):
        """ ajax_select.js needs a jQuery UI on the instance it is handed. """
        self.assertIn('jquery-ui', str(autocomplete_media()))

    def test_it_includes_the_jquery_namespacing_shim(self):
        """
        ``jquery.init.js`` is what keeps the bundled jQuery out of the way.

        It calls ``jQuery.noConflict(true)``, restoring the jQuery 1.10 that
        ``base.html`` loaded and that every finance script is written against.
        Without it the finance pages would get jQuery 3 under ``$`` and the
        ledger, queue and split scripts would break.
        """
        self.assertIn('admin/js/jquery.init.js', str(autocomplete_media()))

    def test_it_renders_as_script_tags(self):
        markup = str(autocomplete_media())
        self.assertIn('<script', markup)

    def test_it_emits_no_stylesheets_at_all(self):
        """
        The regression guard for the flickering dropdown.

        ``ajax_select``'s media carries a complete jQuery UI **1.13.2** theme,
        but the widget on the page is jQuery UI **1.10.3** -- the copy
        ``base.html`` loads and hands to ``window.$``. Serving 1.13's
        stylesheet over 1.10's markup styles a menu that is not the menu being
        rendered: 1.13 wraps each row in ``.ui-menu-item-wrapper`` and drops the
        ``.ui-menu-item a`` rules 1.10 depends on, and the results list came out
        misaligned and flickered as it opened.

        ``base.html`` already provides a matching 1.10.2 theme and
        ``ajax_select.css``, so there is nothing to add here -- only a
        mismatched theme to keep out.
        """
        markup = str(autocomplete_media())
        self.assertNotIn('<link', markup)
        self.assertNotIn('.css', markup)

    def test_it_does_not_serve_a_second_jquery_ui_theme(self):
        """ Named explicitly, because this is the file that caused the flicker. """
        self.assertNotIn('jquery-ui.min.css', str(autocomplete_media()))
