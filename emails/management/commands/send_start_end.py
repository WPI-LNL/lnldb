from django.core.management.base import BaseCommand

from emails.generators import generate_event_start_end_emails


class Command(BaseCommand):
    help = "Sends Emails for events starting RIGHT NOW"

    def handle(self, *args, **options):
        generate_event_start_end_emails()
