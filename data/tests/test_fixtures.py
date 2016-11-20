from django.test import TestCase
from django.core import management
from glob import glob
from six import StringIO


class FixtureTestCase(TestCase):
    def test_all(self):
        null = StringIO()
        for fixture_file in glob("fixtures/*.json"):
            management.call_command('loaddata', fixture_file, stdout=null)
