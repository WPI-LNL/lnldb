"""
Email the Treasurer the weekly billing digest.

It lists, from :func:`finance.billing.digest`:

* bills the client has not answered within the days set in Finance
  Configuration (14 to start), so the Treasurer can email them again;
* ISDs still waiting for the client's approval after the days set there (21
  to start);
* events paid, or needing no bill, that are still open, to close from the
  Billing page.

It only reminds. Emailing a client again stays a button on the Billing page,
because the Treasurer confirms every worktag personally. When all three lists
are empty it sends nothing.

The server runs it once a week from cron, as it runs ``send_start_end``; see
*Looking after the app* in the finance reference. By hand::

    python manage.py billing_digest                    # email the Treasurer
    python manage.py billing_digest --to me@wpi.edu    # email someone else
    python manage.py billing_digest --dry-run          # print it, send nothing
"""
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from emails.generators import DefaultLNLEmailGenerator
from finance.billing import digest

#: The digest's lists, and how the subject line counts each.
LISTS = (
    ('waiting_on_client', "waiting on the client"),
    ('waiting_on_approval', "waiting on approval"),
    ('to_close', "to close"),
)


def subject_for(found):
    """ "Billing digest: 2 waiting on the client, 3 to close", leaving out the empty lists. """
    counts = ["%s %s" % (len(found[key]), words) for key, words in LISTS if found[key]]
    return "Billing digest: %s" % ", ".join(counts)


class Command(BaseCommand):
    help = "Email the Treasurer the bills that have waited too long, and the events ready to close."

    def add_arguments(self, parser):
        parser.add_argument('--to', action='append', metavar='ADDRESS',
                            help="Send it here instead of to the Treasurer (%s). Give it more than once for "
                                 "more than one address." % settings.EMAIL_TARGET_T)
        parser.add_argument('--dry-run', action='store_true', help="Print the email instead of sending it.")

    def handle(self, *args, **options):
        found = digest()
        if not any(found[key] for key, _ in LISTS):
            self.stdout.write("Nothing has waited too long and nothing is ready to close, so no digest was sent.")
            return
        subject = subject_for(found)
        to = options['to'] or [settings.EMAIL_TARGET_T]
        context = dict(found, today=timezone.localdate())
        email = DefaultLNLEmailGenerator(subject=subject, to_emails=to, context=context,
                                         template_basename='finance/emails/billing_digest')
        if options['dry_run']:
            self.stdout.write("To: %s\nSubject: %s\n\n%s" % (", ".join(to), subject, email.email.body))
            return
        email.send()
        self.stdout.write("Sent the billing digest to %s. %s." % (", ".join(to), subject))
