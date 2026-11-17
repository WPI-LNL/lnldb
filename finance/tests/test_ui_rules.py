"""
Rules of the finance pages' look that a new template could break without any
page failing, checked against the templates themselves. See Page layout in
docs/reference/finance.rst.
"""
import functools
import io
import os
import re

from django.conf import settings
from django.test import SimpleTestCase

TEMPLATES = os.path.join(str(settings.TEMPLATES[0]['DIRS'][0]), 'finance')

#: A button or link whose text is an X, however it is written: the entity, the
#: character, its number, or a letter X on its own, perhaps inside a span.
AN_X = re.compile(r'<(?:button|a)\b[^>]*>\s*(?:<span\b[^>]*>\s*)*'
                  r'(?:&times;|&#0*215;|&#x0*d7;|×|x(?=\s*<))', re.IGNORECASE)

#: A tag coloured as Projection, whatever else is in its class, and its words.
A_PROJECTION_TAG = re.compile(
    r'class="[^"]*\bfin-tag\b[^"]*\bis-projection\b[^"]*"[^>]*>([^<]*)<')


@functools.lru_cache(maxsize=None)
def templates():
    """
    ``(path relative to finance/, its text)`` for every finance page, read once
    for the whole module.
    """
    found = []
    for folder, _, names in os.walk(TEMPLATES):
        for name in names:
            if name.endswith('.html'):
                path = os.path.join(folder, name)
                with io.open(path, encoding='utf-8') as source:
                    found.append((os.path.relpath(path, TEMPLATES).replace(os.sep, '/'),
                                  source.read()))
    return tuple(found)


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
            for button in AN_X.findall(text):
                self.assertIn('fin-x', button, path)

    def test_the_x_rule_sees_every_way_of_writing_an_x(self):
        for text in ('<button class="btn btn-link text-danger">&times;</button>',
                     '<button class="btn btn-link">×</button>',
                     '<a href="#" class="text-danger">&#215;</a>',
                     '<button class="close"><span aria-hidden="true">&times;</span></button>',
                     '<button type="button">X</button>'):
            self.assertTrue(AN_X.search(text), text)
        self.assertIsNone(AN_X.search('<a href="#">xlsx</a>'))


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

    #: The queue's tag names the account a line was paid from, 226-AG or
    #: 315-AG, and is coloured for the side that account starts it on.
    ACCOUNT_TAGS = {('queue.html', '{{ row.txn.partition_code_label }}')}

    def test_no_page_asks_for_bootstraps_bar_colours(self):
        for path, text in templates():
            self.assertNotIn('progress-bar-danger', text, path)
            self.assertNotIn('progress-bar-success', text, path)

    def test_a_projection_tag_says_projection(self):
        for path, text in templates():
            for words in A_PROJECTION_TAG.findall(text):
                if (path, words.strip()) not in self.ACCOUNT_TAGS:
                    self.assertEqual(words.strip(), 'Projection', path)

    def test_the_projection_rule_sees_a_tag_with_more_classes(self):
        self.assertEqual(
            A_PROJECTION_TAG.findall('<span class="fin-tag is-projection fin-ml-4">PROJ</span>'),
            ['PROJ'])
