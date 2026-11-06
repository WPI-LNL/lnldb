"""
Rules of the finance pages' look that a new template could break without any
page failing, checked against the templates themselves. See Page layout in
docs/reference/finance.rst.
"""
import io
import os
import re

from django.conf import settings
from django.test import SimpleTestCase

TEMPLATES = os.path.join(str(settings.TEMPLATES[0]['DIRS'][0]), 'finance')


def templates():
    """ ``(path relative to finance/, its text)`` for every finance page. """
    for folder, _, names in os.walk(TEMPLATES):
        for name in names:
            if name.endswith('.html'):
                path = os.path.join(folder, name)
                with io.open(path, encoding='utf-8') as source:
                    yield os.path.relpath(path, TEMPLATES).replace(os.sep, '/'), source.read()


class RemovingARowTests(SimpleTestCase):
    """ Everything that removes a row is an X, never a box to tick. """

    def test_no_delete_box_is_drawn_outside_the_x(self):
        allowed = {'partials/_row_remove.html', 'partials/_budget_category_row.html'}
        drawn = {path for path, text in templates() if re.search(r'\.DELETE\s*}}', text)}
        self.assertEqual(drawn - allowed, set())

    def test_no_column_is_headed_del(self):
        for path, text in templates():
            self.assertNotIn('>Del<', text, path)

    def test_every_x_in_a_table_is_the_same_x(self):
        for path, text in templates():
            for button in re.findall(r'<(?:button|a)\b[^>]*>\s*&times;', text):
                self.assertIn('fin-x', button, path)


class HeaderTests(SimpleTestCase):
    """ The line under a title is for facts, not for saying what the page is. """

    TABS = ('dashboard', 'ledger', 'queue', 'event_pnl', 'billing', 'projects', 'funding_list',
            'multibillings')

    def test_a_tab_does_not_describe_itself(self):
        pages = dict(templates())
        for tab in self.TABS:
            self.assertNotIn('block fin_sub', pages['%s.html' % tab], tab)


class ColourTests(SimpleTestCase):
    """ A burndown takes the charts' colours from finance.css, not Bootstrap's. """

    def test_no_page_asks_for_bootstraps_bar_colours(self):
        for path, text in templates():
            self.assertNotIn('progress-bar-danger', text, path)
            self.assertNotIn('progress-bar-success', text, path)

    def test_a_projection_tag_says_projection(self):
        for path, text in templates():
            for word in re.findall(r'fin-tag is-projection">([^<]*)<', text):
                self.assertEqual(word, 'Projection', path)
