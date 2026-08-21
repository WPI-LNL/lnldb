"""
The subledger's data model.

The whole app rests on one split, and it is worth stating plainly before
reading any further:

* :class:`WorkdayTransaction` is **the bank's record**. One row per line of
  a Workday journal export. It is written by the importer and by nothing
  else -- ``save()``, ``delete()`` and even the queryset's ``update()``
  refuse. If it is wrong, it is wrong in Workday, and the fix is to correct
  it there and re-import.

* :class:`ParsedTransaction` is **LNL's own account of that money**: what it
  was for, which budget it came out of, which project and event it belongs
  to. One bank line can carry several, because a single card charge
  routinely pays for several unrelated things.

Reconciling is the act of writing the second against the first until the
slices add up to the line exactly. Nothing in this module lets that
balance be approximate; see :func:`money` for why every figure that leaves
here is quantized to cents first.

Almost everything else is deliberately data rather than code. Spend
categories, fund sources, revenue sources, partition codes, CSV column
aliases and the suggestion rules all live in editable tables, because each
of them turned out to change on a schedule that has nothing to do with
deploys. What stays hard-coded is listed and justified above
:class:`TransactionStatus`.
"""
import datetime
import hashlib
import re
from decimal import ROUND_HALF_UP, Decimal

import reversion
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models, transaction
from django.db.models import Count, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.urls.base import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.text import slugify
from mptt.models import MPTTModel, TreeForeignKey

# ---------------------------------------------------------------------------
# Money
# ---------------------------------------------------------------------------

#: Every monetary figure in this app is cents, and nothing else.
CENTS = Decimal('0.01')
ZERO = Decimal('0.00')


def money(value):
    """
    A Decimal rounded to whole cents, half away from zero.

    Everything here is stored as ``DecimalField(decimal_places=2)``, so it is
    tempting to assume what comes back is already cents. It is not: SQLite
    quantizes a plain column read but *not* an aggregate, so ``Sum('amount')``
    returns fifteen significant digits and the trailing float noise with them
    -- ``Decimal('-2808.24000000000')`` for a column that only ever held
    ``-2808.24``. Subtracting two of those yields ``Decimal('0E-11')``, which
    is zero, prints as ``0E-11``, and reads to a Treasurer as a bug.

    So every total crosses back into cents here, at the point it leaves the
    database. Doing it in the display layer instead would leave the raw value
    in JSON payloads, form initial data and error messages, which is exactly
    where it was showing up.

    ``None`` and unparseable values become ``$0.00``: a total with nothing in
    it is zero, and callers were already spelling that ``or Decimal('0.00')``.
    """
    if value is None or value == '':
        return ZERO
    if not isinstance(value, Decimal):
        try:
            value = Decimal(str(value))
        except (ArithmeticError, TypeError, ValueError):
            return ZERO
    if not value.is_finite():
        return ZERO
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Fiscal year helpers
#
# WPI's fiscal year runs July 1 -> June 30. FY26 == 2025-07-01 .. 2026-06-30,
# i.e. the fiscal year is named for the calendar year it *ends* in. Which month
# it starts in is a FinanceSettings field, not a constant -- see below.
# ---------------------------------------------------------------------------

# Only the seed for FinanceSettings, applied once by its data migration. The live
# value is the database row.
DEFAULT_FISCAL_YEAR_START_MONTH = getattr(settings, 'LNL_FISCAL_YEAR_START_MONTH', 7)
DEFAULT_STUDENT_ORG_WORKDAY_FUND = getattr(settings, 'LNL_STUDENT_ORG_WORKDAY_FUND', 810)

# Seed values for the PartitionCode table, used once by the data migration.
# The live values are rows in that table, editable from the admin -- the codes
# and the worktag they live in have both already changed once, which is exactly
# why they are no longer constants.
#
# A line carrying one of these codes is *locked* to that side of the partition:
# 315-AG money can never be filed as Event Production and vice versa. Lines
# carrying neither are ambiguous and stay at the Treasurer's discretion.
DEFAULT_PARTITION_WORKTAG = 'student_organization'
DEFAULT_PARTITION_CODES = (
    # (code, is_projection, note)
    ('226-AG', False, 'Lens & Light Club — Event Production'),
    ('315-AG', True, 'Projection'),
)

# Joins Journal Line Memo and Header Memo into WorkdayTransaction.memo, and
# splits them back apart for rows imported before the two were kept separately.
MEMO_SEPARATOR = ' — '


# The worktags that take part in a bank line's identity, alongside the date,
# amount, payee, memo and Operational Transaction. Deliberately a fixed list
# rather than "every worktag": if Workday adds a column to the export, existing
# lines must keep the fingerprints they already have, or a re-import would look
# like a file full of new transactions.
#
# journal_line_memo is excluded because it is already inside `memo`; counting it
# twice would give rows imported before it was stored separately a different
# fingerprint from identical rows imported after.
FINGERPRINT_WORKTAGS = (
    'journal', 'fund', 'cost_center', 'ledger_account', 'spend_category',
    'revenue_category', 'activity', 'student_organization', 'program',
)


def worktag_value(worktags, key, default=''):
    """ Case/format tolerant lookup into a ``worktags_json`` dict. """
    if not worktags:
        return default
    if key in worktags:
        return worktags[key] or default
    target = key.replace('_', ' ').replace('-', ' ').lower()
    for stored, value in worktags.items():
        if stored.replace('_', ' ').replace('-', ' ').lower() == target:
            return value or default
    return default


def _identity_text(value):
    """ Normalise one identity component: blank-insensitive, case-insensitive. """
    if value is None:
        return ''
    return re.sub(r'\s+', ' ', str(value)).strip().lower()


def workday_fingerprint(accounting_date, net_amount, operational_transaction,
                        supplier, employee, memo, worktags):
    """
    A content hash of everything Workday tells us about one journal line.

    Operational Transaction is *not* unique in a real export -- a single
    supplier invoice routinely covers a dozen lines -- so it cannot be the
    duplicate guard on its own. Two lines are the same line only if every
    exported field agrees, and even then they may be two genuinely separate
    charges (two identical Spotify subscriptions in one month). The importer
    resolves that ambiguity with :attr:`WorkdayTransaction.fingerprint_ordinal`;
    this function's only job is to say what "the same line" means.

    Kept as a free function so the backfill migration and the live model share
    one implementation -- two copies that drifted would silently split a row's
    history in half.
    """
    parts = [
        accounting_date.isoformat() if hasattr(accounting_date, 'isoformat') else accounting_date,
        # Quantised so '19.99' and '19.990' cannot disagree.
        str(Decimal(net_amount or 0).quantize(Decimal('0.01'))),
        operational_transaction, supplier, employee, memo,
    ]
    parts.extend(worktag_value(worktags, key) for key in FINGERPRINT_WORKTAGS)
    # Unit separator: a control character no Workday field can contain, so
    # ('ab', 'c') and ('a', 'bc') cannot collide.
    joined = '\x1f'.join(_identity_text(part) for part in parts)
    return hashlib.sha256(joined.encode('utf-8')).hexdigest()


def org_code_matches(value, code):
    """
    True when a Workday worktag value denotes ``code``.

    The value arrives either bare ("315-AG") or with a trailing description
    ("226-AG Lens & Light Club"), so a prefix match is needed -- but a plain
    ``startswith`` would also match a hypothetical "315-AGX", hence the
    separator check.
    """
    value = (value or '').strip().upper()
    if not value:
        return False
    target = (code or '').strip().upper()
    if not target:
        return False
    if value == target:
        return True
    return any(value.startswith(target + sep) for sep in (' ', ':', '-', '\t'))


MONTH_CHOICES = tuple(
    (n, datetime.date(2000, n, 1).strftime('%B')) for n in range(1, 13))


class FinanceSettings(models.Model):
    """
    The handful of finance settings that are institutional policy rather than
    program logic. One row, edited from the admin.

    These were module constants read from ``settings.py``, which meant a
    fiscal-year change or a Workday renumber needed a developer and a deploy.
    Neither is a code change in any meaningful sense.
    """
    fiscal_year_start_month = models.PositiveSmallIntegerField(
        choices=MONTH_CHOICES, default=7, verbose_name="Fiscal year starts in",
        help_text="WPI's runs July–June, so FY26 is Jul 2025 – Jun 2026 and is named for "
                  "the year it ends in. Changing this re-files every transaction ever "
                  "recorded into different fiscal years, so change it only if the "
                  "institution genuinely moves its year.")
    student_org_workday_fund = models.PositiveIntegerField(
        default=810, verbose_name="Student organization fund",
        help_text="The Workday fund number that marks a client as a student organization "
                  "(810 for 810-FD). Everything else billing through Workday is treated as "
                  "a department. Drives the client-type breakdown on the dashboard.")
    fiscal_years_back = models.PositiveSmallIntegerField(
        default=6, verbose_name="Past years in the picker",
        help_text="How many previous fiscal years the filter bar offers.")
    fiscal_years_forward = models.PositiveSmallIntegerField(
        default=1, verbose_name="Future years in the picker",
        help_text="How many upcoming fiscal years to offer, for encumbrances and awards "
                  "booked ahead of time.")

    class Meta:
        verbose_name = "Finance Configuration"
        verbose_name_plural = "Finance Configuration"

    def __str__(self):
        return "Finance configuration"

    def save(self, *args, **kwargs):
        """ Force this onto row 1, whatever the caller thought it was doing. """
        # One row, always. A second would make "the configuration" ambiguous.
        self.pk = 1
        # ...so objects.create() on an already-configured site is an edit of
        # that row, not an insert that collides with it.
        kwargs.pop('force_insert', None)
        return super(FinanceSettings, self).save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """ Refuse: half the app reads these values on every request. """
        raise ValidationError(
            "The finance configuration cannot be deleted. Edit the values instead.")

    @classmethod
    def load(cls):
        """ The configuration row, created with defaults if it is missing. """
        return cls.objects.get_or_create(pk=1)[0]


# ---------------------------------------------------------------------------
# Cached table reads
#
# A handful of settings and vocabularies are consulted on paths hot enough that
# a query each time would be silly -- fiscal_year_for() runs on every row of
# every page. They are read once, kept here, and dropped by a post_save signal
# (see finance/apps.py) the moment the admin changes one.
# ---------------------------------------------------------------------------

_CACHE = {}


def reset_finance_cache(*keys):
    """ Forget cached table reads. No arguments clears everything. """
    for key in (keys or list(_CACHE)):
        _CACHE.pop(key, None)


def _cached(key, build, default):
    """
    ``build()`` once, remembered under ``key``.

    A missing table is not an error: this module is imported before its own
    migrations have run, and ``manage.py migrate`` on an empty database would
    otherwise fail on the first fiscal-year calculation.
    """
    if key not in _CACHE:
        try:
            _CACHE[key] = build()
        except Exception:
            return default
    return _CACHE[key]


def finance_settings():
    """ The live :class:`FinanceSettings` row, or the defaults if there is none. """
    return _cached('config', lambda: FinanceSettings.load(), FinanceSettings(pk=1))


def fiscal_year_start_month():
    """
    The month a fiscal year begins, 1-12.

    Configurable rather than fixed at July: WPI has moved it before, and
    every date-to-year calculation in the app funnels through here.
    """
    return finance_settings().fiscal_year_start_month


def fiscal_year_for(date):
    """ Return the integer fiscal year containing ``date`` (FY26 -> 2026). """
    if date is None:
        return None
    return date.year + 1 if date.month >= fiscal_year_start_month() else date.year


def fiscal_year_bounds(fiscal_year):
    """ Return ``(first_day, last_day)`` inclusive for the given fiscal year. """
    first_month = fiscal_year_start_month()
    start = datetime.date(fiscal_year - 1, first_month, 1)
    if first_month == 1:
        end = datetime.date(fiscal_year - 1, 12, 31)
    else:
        end = datetime.date(fiscal_year, first_month, 1) - datetime.timedelta(days=1)
    return start, end


def current_fiscal_year():
    """ The fiscal year we are in today, in local time. """
    return fiscal_year_for(timezone.localdate())


def fiscal_year_choices(back=None, forward=None):
    """ Descending list of ``(fy, "FY26 (Jul 2025 - Jun 2026)")`` tuples for filters. """
    config = finance_settings()
    back = config.fiscal_years_back if back is None else back
    forward = config.fiscal_years_forward if forward is None else forward
    now = current_fiscal_year()
    out = []
    for fy in range(now + forward, now - back - 1, -1):
        start, end = fiscal_year_bounds(fy)
        out.append((fy, "FY%s (%s %s – %s %s)" % (
            str(fy)[-2:], start.strftime('%b'), start.year, end.strftime('%b'), end.year)))
    return out


# ---------------------------------------------------------------------------
# Enumerations
#
# Only two things stay hard-coded here, and both are code rather than data:
#
# * TransactionStatus is a state machine. ``settle()``, ``clean()`` and a
#   database CheckConstraint all branch on these two values, so adding a third
#   from the admin would change nothing without code to go with it.
# * ClientType is *derived* from the linked event's billing fund. It is never
#   stored or chosen, so there is nothing to configure.
#
# Everything a Treasurer might reasonably want to add or rename -- spend
# categories, fund sources, revenue sources, auto-suggest rules, the partition
# codes -- lives in the editable tables further down.
# ---------------------------------------------------------------------------

class TransactionStatus(models.TextChoices):
    """
    Whether an entry is money that has moved or money merely reserved.

    Pending covers encumbrances and slices of a split that is not finished
    yet; Settled means the entry is final. A bank line counts as reconciled
    only once every slice on it is Settled and they add up exactly.
    """
    PENDING = 'pending', 'Pending'
    SETTLED = 'settled', 'Settled'


class ClientType(models.TextChoices):
    """ Derived from the linked event's billing org; never entered by hand. """
    STUDENT_ORG = 'student_org', 'Student Organization'
    DEPARTMENT = 'department', 'Department'
    UNKNOWN = 'unknown', 'Unknown'


def event_passthrough_category():
    """
    The :class:`SpendCategory` for costs billed straight to an event, if one is
    flagged. ``None`` simply means the Treasurer picks a category as usual.
    """
    return _cached(
        'event_passthrough',
        lambda: SpendCategory.objects.filter(is_event_passthrough=True, is_active=True).first(),
        None)


def student_org_workday_fund():
    """
    The Workday fund that marks a client as a student organization (810-FD).

    A :class:`FinanceSettings` field rather than a constant: it is a number
    Workday assigns, and Workday renumbers things.
    """
    return finance_settings().student_org_workday_fund


# ---------------------------------------------------------------------------
# Editable vocabularies
#
# These replace what used to be TextChoices classes. They share a shape --
# a human name, a stable slug, a display order and an active flag -- so the
# admin, the forms and the URL filters can treat them identically.
#
# The slug is what appears in querystrings (``?category=consumables``) and what
# code refers to when it needs a specific row. Renaming a category is therefore
# free; changing its slug is the breaking move, so the admin marks it as such.
# ---------------------------------------------------------------------------

class VocabularyQuerySet(models.QuerySet):
    """ Adds :meth:`active` to every editable lookup table. """

    def active(self):
        """
        Only the terms still being offered for new records.

        Retired terms stay attached to the rows that already use them, which
        is the whole point of retiring rather than deleting -- last year's
        ledger still has to read correctly.
        """
        return self.filter(is_active=True)


class Vocabulary(models.Model):
    """ Shared behaviour for the small editable lookup tables. """
    name = models.CharField(max_length=96, unique=True)
    slug = models.SlugField(
        max_length=48, unique=True,
        help_text="Stable key used in links and by the importer. Safe to leave alone; "
                  "changing it will break saved links and bookmarks.")
    sort_order = models.PositiveIntegerField(
        default=0, help_text="Lower numbers appear first in dropdowns.")
    is_active = models.BooleanField(
        default=True,
        help_text="Uncheck to retire an option. Existing records keep it; it just "
                  "stops being offered for new ones.")

    objects = VocabularyQuerySet.as_manager()

    class Meta:
        abstract = True
        ordering = ('sort_order', 'name')

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        """ Derive the slug from the name the first time, then leave it alone. """
        if not self.slug:
            self.slug = slugify(self.name)[:48]
        return super(Vocabulary, self).save(*args, **kwargs)


class SpendCategory(Vocabulary):
    """ What LNL spent money on -- the categories on the dashboard pie. """
    color = models.CharField(
        max_length=7, default='#BAB0AC', verbose_name="Chart colour",
        validators=[RegexValidator(r'^#[0-9A-Fa-f]{6}$',
                                   "Use a six-digit hex colour such as #4E79A7.")],
        help_text="Used for this category everywhere it appears in a chart.")
    description = models.TextField(blank=True)
    is_event_passthrough = models.BooleanField(
        default=False, verbose_name="Use for costs billed to an event",
        help_text="The category to file an expense under when it names the event it was "
                  "incurred for -- a sub-rental hired for one show, passed straight "
                  "through. Filled in automatically so the Treasurer does not have to "
                  "pick a category that says nothing the linked event does not.")

    class Meta(Vocabulary.Meta):
        abstract = False
        verbose_name = "LNL Spend Category"
        verbose_name_plural = "LNL Spend Categories"


class FundSource(Vocabulary):
    """ Which pot of money paid for something. """
    description = models.TextField(blank=True)
    workday_fund_codes = models.CharField(
        max_length=192, blank=True, verbose_name="Workday fund codes",
        help_text="Comma-separated Fund codes from the export that mean this bucket and "
                  "only this bucket. A line whose Fund matches is filled in automatically, "
                  "so only list a code when it genuinely identifies this fund -- 810-FD is "
                  "on all of LNL's spending and says nothing about whose money it was. "
                  "Leave blank and this fund is never chosen for you.")
    requires_funding_request = models.BooleanField(
        default=False, verbose_name="Must name a funding request line",
        help_text="Money from a specific SGA funding request has to burn down one of that "
                  "request's lines, or the request's balance silently drifts. Turn this on "
                  "and an expense on this fund cannot be saved without an FR line -- and no "
                  "other fund is allowed to name one.")

    class Meta(Vocabulary.Meta):
        abstract = False
        verbose_name = "Fund Source"


def workday_fund_map():
    """
    ``{'220-FD': <FundSource>}`` -- which bucket each Workday Fund code means.

    Which code maps where is WPI's business, not ours, so it is typed into the
    admin rather than compiled in. Consulted once per queue row, hence cached.

    Only codes that identify one bucket on their own belong here. 810-FD is the
    agency fund the whole account sits in, so it appears on every LNL line and
    is deliberately mapped nowhere; see :func:`suggestions.suggest_fund_source`.
    """
    def build():
        out = {}
        for source in FundSource.objects.active().exclude(workday_fund_codes=''):
            for code in source.workday_fund_codes.split(','):
                code = code.strip().upper()
                # First fund to claim a code keeps it, so a typo in a later row
                # cannot silently re-point an established mapping.
                if code and code not in out:
                    out[code] = source
        return out
    return _cached('fund_codes', build, {})


def fund_source_for_workday_fund(value):
    """
    The fund bucket a Workday Fund worktag names, or ``None``.

    Workday writes the code with its description attached ("810-FD Agency"), so
    a configured code matches when it is the leading token or is contained in
    the value -- the code itself is what identifies it.
    """
    haystack = (value or '').strip().upper()
    if not haystack:
        return None
    for code, source in workday_fund_map().items():
        if haystack == code or haystack.startswith(code + ' ') or code in haystack:
            return source
    return None


class RevenueSource(Vocabulary):
    """ Where non-event revenue came from (SGA baseline, alumni gifts...). """
    description = models.TextField(blank=True)

    class Meta(Vocabulary.Meta):
        abstract = False
        verbose_name = "Non-Event Revenue Source"


class PartitionCode(models.Model):
    """
    The organisation codes that say which side of the Event Production /
    Projection partition a Workday line belongs to *by default*.

    These were constants until the column they live in turned out to differ
    from what the spec implied, which is precisely why they belong in a table:
    a ledger renumber or a new sub-organisation should not need a deploy.

    They were also a hard lock, and that was wrong. Which account paid for
    something and which activity it was for are different questions. LNL buys
    Projection equipment out of the main 226-AG account whenever SGA funds it
    through a funding request, because the reimbursement comes back into 226-AG;
    the money is 226-AG money and the expense is a Projection expense, both at
    once. A lock made that unrecordable, so the correct entry was impossible and
    the wrong one was mandatory.

    What survives is the asymmetry. 315-AG is funded by SGA directly for
    Projection, so money on it leaving the Projection side is the direction that
    would breach the isolation the university cares about; that crossing has to
    be explained in writing. The other direction is ordinary business and only
    gets a warning.
    """
    code = models.CharField(
        max_length=32, unique=True,
        help_text="The organisation code as Workday writes it, e.g. 226-AG. "
                  "A trailing description in the export is ignored when matching.")
    is_projection = models.BooleanField(
        default=False, verbose_name="Projection side",
        help_text="Checked: money on this code is Projection spending unless told "
                  "otherwise. Unchecked: Event Production unless told otherwise. This is "
                  "the starting position, not a rule -- see the field below.")
    crossing_requires_reason = models.BooleanField(
        default=False, verbose_name="Filing it the other way needs an explanation",
        help_text="Off: moving money off this side is allowed and merely shows a warning, "
                  "which is right for the main account -- a Projection purchase paid out of "
                  "it and reimbursed by SGA is normal. On: it is still allowed, but the "
                  "entry cannot be saved without saying why. Turn this on for the account "
                  "SGA funds for Projection directly.")
    worktag = models.CharField(
        max_length=48, default='student_organization',
        help_text="Which Workday worktag carries this code. Real exports put it in "
                  "Student Organization, not Ledger Account.")
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ('code',)
        verbose_name = "Partition Code"

    def __str__(self):
        return "%s → %s%s" % (
            self.code, 'Projection' if self.is_projection else 'Event Production',
            ' (crossing needs a reason)' if self.crossing_requires_reason else '')


def reset_partition_cache():
    """ Kept as its own name because tests that create codes call it directly. """
    reset_finance_cache('codes')


def partition_codes():
    """
    The partition codes as plain dicts, cached.

    They are consulted on every save and once per row on the queue, so the
    handful of codes is held in memory rather than queried each time.
    """
    return _cached(
        'codes',
        lambda: [{'code': p.code, 'is_projection': p.is_projection, 'worktag': p.worktag,
                  'crossing_requires_reason': p.crossing_requires_reason}
                 for p in PartitionCode.objects.all()],
        [])


def partition_worktag_keys():
    """ Which worktags to look in, in the order the codes name them. """
    keys = []
    for entry in partition_codes():
        if entry['worktag'] not in keys:
            keys.append(entry['worktag'])
    return keys or [DEFAULT_PARTITION_WORKTAG]


class ServiceColor(models.Model):
    """
    The colour a service category is drawn in on the dashboard.

    Points at the events app's own ``Category`` rather than storing its name,
    so renaming "Sound" does not silently turn that slice grey. A category with
    no row here falls back to the qualitative ramp, which is why adding a new
    service is not a code change either -- assigning it a colour is optional.
    """
    category = models.OneToOneField('events.Category', on_delete=models.CASCADE,
                                    related_name='finance_color')
    color = models.CharField(
        max_length=7, verbose_name="Chart colour",
        validators=[RegexValidator(r'^#[0-9A-Fa-f]{6}$', "Use a hex colour such as #4E79A7.")],
        help_text="Hex, e.g. #4E79A7.")

    class Meta:
        ordering = ('category__name',)
        verbose_name = "Service Colour"

    def __str__(self):
        return "%s → %s" % (self.category, self.color)


# LNL's three long-standing service lines, so a fresh install draws them in
# their familiar colours without anyone configuring anything. Any ServiceColor
# row wins over this, and a category not named here simply takes the next
# colour off the qualitative ramp.
DEFAULT_SERVICE_COLORS = {
    'Lighting': '#EDC948',
    'Sound': '#4E79A7',
    'Projection': '#B07AA1',
}


def service_colors():
    """ ``{category name: hex}``: the defaults, overridden by any admin rows. """
    def build():
        colors = dict(DEFAULT_SERVICE_COLORS)
        colors.update({row.category.name: row.color
                       for row in ServiceColor.objects.select_related('category')})
        return colors

    return _cached('service_colors', build, dict(DEFAULT_SERVICE_COLORS))


class ColumnAlias(models.Model):
    """
    An extra spelling of a Workday CSV column.

    :data:`finance.importers.COLUMN_ALIASES` holds the spellings we have
    actually seen, and stays in code because the canonical names on the left of
    it are referenced throughout the importer. What is *not* code is Workday
    deciding to relabel a column -- when that happens the fix is a row here
    rather than a deploy.
    """
    canonical = models.CharField(
        max_length=64, verbose_name="Importer field",
        help_text="The name the importer knows the column by, e.g. student_organization. "
                  "Pick from the list on the Workday transaction admin if unsure.")
    alias = models.CharField(
        max_length=128, unique=True, verbose_name="Header in the export",
        help_text="The column heading as Workday now writes it. Case, punctuation and "
                  "extra spaces are ignored when matching.")
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ('canonical', 'alias')
        verbose_name = "CSV Column Alias"
        verbose_name_plural = "CSV Column Aliases"

    def __str__(self):
        return "%s → %s" % (self.alias, self.canonical)


def column_aliases():
    """ ``{normalised alias: canonical}`` from the table, cached. """
    return _cached(
        'column_aliases',
        lambda: {re.sub(r'[^a-z0-9]+', ' ', row.alias.lower()).strip(): row.canonical
                 for row in ColumnAlias.objects.all()},
        {})


class SuggestionRule(models.Model):
    """
    One "if the Workday line looks like this, suggest that category" rule.

    These were three hard-coded tables -- GL account prefixes, supplier names
    and memo keywords. All three were really WPI's chart of accounts and LNL's
    vendor list, which change without any code changing, so they live here now.

    Rules are tried in ``priority`` order and the first match wins, which is why
    a specific rule ("chain motor") must outrank a general one ("repair").
    """
    LEDGER_ACCOUNT = 'ledger_account'
    SPEND_CATEGORY = 'spend_category'
    SUPPLIER = 'supplier'
    MEMO = 'memo'

    FIELD_CHOICES = (
        (LEDGER_ACCOUNT, 'Workday ledger account'),
        (SPEND_CATEGORY, "Workday's own spend category"),
        (SUPPLIER, 'Supplier or employee name'),
        (MEMO, 'Memo text'),
    )

    # How the pattern is compared. This used to be implied by the column
    # — ledger accounts matched their start, everything else matched
    # anywhere — which left "the finest code Workday gives us" and "a word
    # that happens to appear in some prose" indistinguishable to whatever
    # consumed the result. Saying it out loud is what lets a match be trusted
    # enough to fill a box in rather than merely offer a chip to click.
    EXACT = 'exact'
    STARTS = 'starts'
    CONTAINS = 'contains'
    WORD = 'word'

    MODE_CHOICES = (
        (EXACT, 'Is exactly — the whole value, e.g. "Rent - Equipment"'),
        (STARTS, 'Starts with — e.g. the account number 71100'),
        (CONTAINS, 'Contains — a guess about wording'),
        (WORD, 'Contains the whole word — a guess about wording'),
    )

    # A code Workday assigned is a fact about the line; a word found inside
    # prose is an inference about it. Only the first is filled in for the
    # Treasurer; the second is offered for them to accept.
    LOOKUP_MODES = (EXACT, STARTS)

    CONFIDENCE_CHOICES = (
        ('high', 'High — pre-select it confidently'),
        ('medium', 'Medium'),
        ('low', 'Low — offer it as a guess'),
    )

    match_field = models.CharField(
        max_length=24, choices=FIELD_CHOICES, default=SPEND_CATEGORY,
        help_text="Which part of the imported line to look at.")
    match_mode = models.CharField(
        max_length=12, choices=MODE_CHOICES, default=EXACT, verbose_name="Match how",
        help_text="Exact and starts-with count as lookups: what they find is filled into "
                  "the reconciliation form, because the export itself said it. Contains "
                  "counts as a guess and is only ever offered as a chip to click.")
    pattern = models.CharField(
        max_length=128,
        help_text="Text to look for. Case-insensitive; surrounding spaces are ignored.")
    spend_category = models.ForeignKey(
        SpendCategory, on_delete=models.CASCADE, related_name='suggestion_rules',
        help_text="The category to suggest when this rule matches.")
    confidence = models.CharField(max_length=8, choices=CONFIDENCE_CHOICES, default='high')
    priority = models.PositiveIntegerField(
        default=100,
        help_text="Lower numbers are checked first. Put specific rules above general ones.")
    is_active = models.BooleanField(default=True)
    notes = models.CharField(max_length=192, blank=True)

    objects = VocabularyQuerySet.as_manager()

    class Meta:
        ordering = ('priority', 'pk')
        verbose_name = "Spend Category Suggestion Rule"

    def __str__(self):
        return "%s %s %r → %s" % (
            self.get_match_field_display(),
            self.get_match_mode_display().split(' ')[0].lower(),
            self.pattern, self.spend_category)

    @property
    def is_lookup(self):
        """
        Whether a match is evidence rather than inference.

        An exact or starts-with hit on a code means the export itself said so,
        and that is what earns the right to fill the form in. A "contains" hit
        is a guess about English, so it stays a suggestion to click.
        """
        return self.match_mode in self.LOOKUP_MODES

    def subject(self, transaction):
        """ The text on ``transaction`` that this rule examines. """
        if self.match_field == self.LEDGER_ACCOUNT:
            return transaction.ledger_account or ''
        if self.match_field == self.SPEND_CATEGORY:
            return transaction.worktag('spend_category') or ''
        if self.match_field == self.SUPPLIER:
            return transaction.payee or ''
        return transaction.memo or ''

    def matches(self, transaction):
        """ True when this rule applies to the given :class:`WorkdayTransaction`. """
        pattern = (self.pattern or '').strip().lower()
        if not pattern:
            return False
        subject = self.subject(transaction).strip().lower()
        if not subject:
            return False

        if self.match_mode == self.EXACT:
            return subject == pattern
        if self.match_mode == self.STARTS:
            return subject.startswith(pattern)
        if self.match_mode == self.WORD:
            # Whole-word so "gel" doesn't fire on "Angela".
            return re.search(r'\b%s' % re.escape(pattern), subject) is not None
        return pattern in subject


# ---------------------------------------------------------------------------
# Project tags
# ---------------------------------------------------------------------------

@reversion.register()
class ProjectTag(MPTTModel):
    """
    A self-referential grouping used to answer "what did this thing really cost
    us, across every fiscal year and funding source?"

    Parent nodes are projects (``NEL26``); children are the individual assets
    bought under them (``D60 Lustrs``).
    """
    glyphicon = 'tags'

    name = models.CharField(max_length=128)
    code = models.SlugField(
        max_length=32, unique=True,
        help_text="Short unique key used on reports, e.g. NEL26 or D60-LUSTR")
    parent = TreeForeignKey('self', on_delete=models.PROTECT, null=True, blank=True,
                            related_name='children', verbose_name="Parent project",
                            help_text="Leave blank to create a top-level project")
    description = models.TextField(blank=True)
    is_projection = models.BooleanField(
        default=False, verbose_name="Projection project",
        help_text="Projects belonging to the Projection partition")
    archived = models.BooleanField(default=False)

    created_on = models.DateTimeField(auto_now_add=True)

    class MPTTMeta:
        order_insertion_by = ['name']

    class Meta:
        verbose_name = "Project Tag"
        # Django supplies add/change/delete/view_projecttag automatically.
        permissions = (
            ('manage_projecttag', 'Create and edit project tags'),
        )

    def __str__(self):
        return "%s (%s)" % (self.name, self.code)

    @property
    def indented_label(self):
        """
        Option label for every project picker, nested by depth.

        Non-breaking spaces because HTML collapses ordinary leading whitespace
        inside ``<option>``. Kept on the model so the forms and the raw ledger
        filter cannot drift apart::

            NEL26 — New Equipment List 2026
                └ D60-LUSTR — D60 Lustr Fixtures
        """
        depth = getattr(self, 'level', 0) or 0
        indent = ' ' * (4 * depth)
        marker = '└ ' if depth else ''
        return '%s%s%s — %s' % (indent, marker, self.code, self.name)

    def get_absolute_url(self):
        """ This tag's branch of the project explorer. """
        return reverse('finance:projects-detail', args=[self.pk])

    # -- rollups ------------------------------------------------------------
    # NB: ``self.transactions`` is the reverse manager for slices tagged
    # *directly* to this node. The rollup below deliberately has its own name so
    # it doesn't shadow it.
    def rollup_transactions(self, include_descendants=True):
        """ All allocation slices tagged to this node (and optionally below it). """
        if not include_descendants:
            return ParsedTransaction.objects.filter(project_tag=self)

        # MPTT caches tree_id/lft/rght on the instance, and they go stale the
        # moment anything else in the forest is written -- adding an unrelated
        # root is enough. Walking stale bounds returns the wrong descendants and
        # silently reports the wrong cost, so re-read them first. One small
        # query is a fair price for a figure people make purchasing decisions on.
        node = self
        if self.pk is not None:
            try:
                node = type(self)._default_manager.get(pk=self.pk)
            except type(self).DoesNotExist:
                node = self

        nodes = node.get_descendants(include_self=True)
        return ParsedTransaction.objects.filter(project_tag__in=nodes)

    def total_cost(self, include_descendants=True, fiscal_year=None):
        """
        The "true fully-loaded cost" of this node: expenses net of refunds,
        expressed as a positive number.
        """
        qs = self.rollup_transactions(include_descendants)
        if fiscal_year:
            start, end = fiscal_year_bounds(fiscal_year)
            qs = qs.filter(effective_date__range=(start, end))
        return -money(qs.aggregate(t=Sum('amount'))['t'])


# ---------------------------------------------------------------------------
# Funding requests (out-of-cycle SGA capital grants)
# ---------------------------------------------------------------------------

@reversion.register(follow=['line_items'])
class FundingRequest(models.Model):
    """ An out-of-cycle SGA funding request. The parent of a set of line items. """
    glyphicon = 'inbox'

    name = models.CharField(max_length=192)
    reference = models.CharField(max_length=64, blank=True, verbose_name="SGA reference #")
    fiscal_year = models.PositiveIntegerField(default=current_fiscal_year, db_index=True)
    date_submitted = models.DateField(null=True, blank=True)
    date_approved = models.DateField(null=True, blank=True)
    is_projection = models.BooleanField(default=False, verbose_name="Projection request")
    closed = models.BooleanField(
        default=False, help_text="Closed requests are hidden from the dashboard burndown")
    notes = models.TextField(blank=True)

    created_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-fiscal_year', 'name')
        verbose_name = "Funding Request"
        # Django supplies add/change/delete/view_fundingrequest automatically.
        permissions = (
            ('manage_fundingrequest', 'Create and edit funding requests'),
        )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        """ This request's detail page, line items and all. """
        return reverse('finance:fr-detail', args=[self.pk])

    @property
    def total_awarded(self):
        """ Everything SGA granted across this request's lines. """
        return money(self.line_items.aggregate(t=Sum('amount_awarded'))['t'])

    @property
    def total_spent(self):
        """ Positive figure. Refunds against these lines reduce it automatically. """
        return -money(ParsedTransaction.objects.filter(
            fr_line_target__funding_request=self).aggregate(t=Sum('amount'))['t'])

    @property
    def total_remaining(self):
        """ Award less spend. Negative means the request is overspent. """
        return self.total_awarded - self.total_spent

    @property
    def percent_spent(self):
        """
        Spend as a 0-100 integer, for the burndown bar.

        Clamped, so an overspend reads as a full bar; the overage itself is
        reported separately rather than as a percentage over 100.
        """
        awarded = self.total_awarded
        if not awarded:
            return 0
        return max(0, min(100, int(round(self.total_spent / awarded * 100))))

    @property
    def is_overspent(self):
        """ Whether this request has been charged more than it was awarded. """
        return self.total_remaining < 0


class FRLineItemQuerySet(models.QuerySet):
    """ Annotations for the funding request pickers and burndown bars. """

    def with_spend(self):
        """ Pre-compute what each line has spent, for pickers that show it. """
        return self.annotate(_allocated_total=Coalesce(
            Sum('allocations__amount'),
            Value(Decimal('0.00')),
            output_field=models.DecimalField(max_digits=12, decimal_places=2)))


@reversion.register(follow=['funding_request'])
class FRLineItem(models.Model):
    """
    A single budgeted line inside a funding request. Balances are live.

    Registered with reversion in its own right: :class:`FundingRequest` follows
    ``line_items``, and reversion refuses to serialise a followed model it does
    not know about. Following the parent back means editing one line records the
    whole request, so a version can be restored as a complete set.
    """
    funding_request = models.ForeignKey(FundingRequest, on_delete=models.CASCADE,
                                        related_name='line_items')
    name = models.CharField(max_length=192)
    description = models.TextField(
        blank=True,
        help_text="What this line covers, in the words used on the SGA request")
    amount_awarded = models.DecimalField(max_digits=10, decimal_places=2,
                                         validators=[MinValueValidator(Decimal('0.00'))])
    lnl_spend_category = models.ForeignKey(
        SpendCategory, on_delete=models.PROTECT, null=True, blank=True,
        related_name='fr_line_items', verbose_name="Expected spend category")
    project_tag = models.ForeignKey(ProjectTag, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='fr_line_items')
    sort_order = models.PositiveIntegerField(default=0)

    objects = FRLineItemQuerySet.as_manager()

    class Meta:
        ordering = ('sort_order', 'pk')
        verbose_name = "Funding Request Line Item"

    def __str__(self):
        return "%s – %s" % (self.funding_request.name, self.name)

    @property
    def spent(self):
        """
        Positive figure. Expenses are stored negative and refunds positive, so a
        return credit mathematically restores this line's balance for free.

        Uses :meth:`FRLineItemQuerySet.with_spend` if the row was loaded through
        it: the allocation picker puts this figure on every option, which would
        otherwise be a query per line per form per row of the queue.
        """
        annotated = getattr(self, '_allocated_total', None)
        if annotated is not None:
            return -money(annotated)
        return -money(self.allocations.aggregate(t=Sum('amount'))['t'])

    @property
    def remaining(self):
        """ What is left on this line. Negative means it is overspent. """
        return self.amount_awarded - self.spent

    @property
    def percent_spent(self):
        """ Spend on this line as a clamped 0-100 integer. """
        if not self.amount_awarded:
            return 0
        return max(0, min(100, int(round(self.spent / self.amount_awarded * 100))))

    @property
    def is_overspent(self):
        """ Whether more has been charged here than was awarded. """
        return self.remaining < 0

    @property
    def overspent_by(self):
        """ How far over, as a positive figure; zero when within the award. """
        return -self.remaining if self.is_overspent else Decimal('0.00')

    @property
    def picker_label(self):
        """
        How this line reads in an allocation dropdown.

        The fiscal year and the remaining balance are both on the label because
        both are things you can get wrong without noticing: charging FY26 money
        to an FY25 request, or pushing a line past its award.
        """
        fr = self.funding_request
        name = "%s %s" % (fr.reference, fr.name) if fr.reference else fr.name
        remaining = self.remaining
        if remaining < 0:
            balance = "OVER by $%s" % (-remaining)
        else:
            balance = "$%s left" % remaining
        return "FY%s · %s · %s — %s" % (fr.fiscal_year, name, self.name, balance)


# ---------------------------------------------------------------------------
# Table A: the immutable bank truth
# ---------------------------------------------------------------------------

class WorkdayTransactionQuerySet(models.QuerySet):
    """
    Closes the back door in the immutability guarantee.

    ``Model.delete()`` and ``Model.save()`` are overridden below, but Django's
    queryset ``.delete()`` and ``.update()`` never call them -- so without this
    a single ``objects.filter(...).update(...)`` could silently rewrite the
    bank's record of events.
    """
    def delete(self):
        """ Refuse. :meth:`hard_delete` is the deliberate way to do this. """
        raise ValidationError(
            "WorkdayTransaction rows are immutable. Use .hard_delete() if you genuinely "
            "need to undo a bad import.")

    def update(self, **kwargs):
        """ Refuse: a bulk update would bypass every guard on the model. """
        raise ValidationError(
            "WorkdayTransaction rows are immutable. Correct the record in Workday and "
            "re-import, or adjust the allocation slices instead.")

    def hard_delete(self):
        """
        Deliberate escape hatch for backing out a bad import. Cascades to the
        allocation slices, so it really does undo the whole thing.
        """
        return super(WorkdayTransactionQuerySet, self).delete()

    def with_allocation(self):
        """
        Annotate the reconciliation state in SQL.

        Without this, asking each row whether it is reconciled costs three
        queries apiece (an aggregate and two exists checks), because aggregates
        ignore ``prefetch_related``. On a few hundred bank lines that alone was
        several hundred queries per dashboard render.
        """
        return self.annotate(
            _allocated=Coalesce(
                Sum('slices__amount'),
                Value(Decimal('0.00')),
                output_field=models.DecimalField(max_digits=12, decimal_places=2)),
            _slice_count=Count('slices'),
            _pending_count=Count('slices', filter=Q(slices__status=TransactionStatus.PENDING)),
        )

    def unreconciled(self):
        """
        Bank lines that still need a human: no slices at all, slices that don't
        add up to the bank amount, or slices left Pending.
        """
        return self.with_allocation().exclude(
            Q(_slice_count__gt=0) & Q(_pending_count=0) & Q(_allocated=models.F('net_amount')))

    def reconciled(self):
        """ The exact complement of :meth:`unreconciled`: done, and balanced. """
        return self.with_allocation().filter(
            Q(_slice_count__gt=0) & Q(_pending_count=0) & Q(_allocated=models.F('net_amount')))


WorkdayTransactionManager = models.Manager.from_queryset(WorkdayTransactionQuerySet)


class WorkdayTransaction(models.Model):
    """
    A single line from a Workday journal export. Written *only* by the CSV
    importer and read-only forever after -- this is the bank's version of
    events, and the subledger is not allowed to rewrite history.

    Mutable interpretation lives on :class:`ParsedTransaction`.
    """
    glyphicon = 'university'

    operational_transaction = models.CharField(
        max_length=128, blank=True, db_index=True, verbose_name="Operational Transaction",
        help_text="Workday's reference for the document this line belongs to. One invoice "
                  "covers many lines, and journal entries carry none at all, so this is a "
                  "grouping label -- not an identifier.")
    accounting_date = models.DateField(db_index=True)
    net_amount = models.DecimalField(
        max_digits=12, decimal_places=2, verbose_name="Net amount",
        help_text="Workday 'Credit Minus Debit'. Positive = revenue, negative = expense.")

    supplier = models.CharField(max_length=255, blank=True)
    employee = models.CharField(max_length=255, blank=True)
    memo = models.TextField(blank=True, help_text="Journal Line Memo + Header Memo, concatenated")

    worktags_json = models.JSONField(
        default=dict, blank=True, verbose_name="Workday worktags",
        help_text="Remaining Workday columns (fund, cost center, ledger account, "
                  "spend category, program...) kept verbatim for auto-suggest and audit")

    # -- identity -----------------------------------------------------------
    # See workday_fingerprint() for what goes into the hash, and
    # finance.importers for how the ordinal is assigned.
    row_fingerprint = models.CharField(
        max_length=64, blank=True, db_index=True, editable=False,
        verbose_name="Row fingerprint",
        help_text="Content hash of the exported line: date, amount, payee, memo and worktags")
    fingerprint_ordinal = models.PositiveIntegerField(
        default=1, editable=False, verbose_name="Occurrence",
        help_text="Which occurrence of an otherwise identical line this is. Two genuinely "
                  "separate charges that Workday exports identically are occurrence 1 and 2.")

    # Import provenance
    imported_on = models.DateTimeField(auto_now_add=True)
    imported_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name='workday_imports')
    source_file = models.CharField(max_length=255, blank=True)

    objects = WorkdayTransactionManager()

    class Meta:
        ordering = ('-accounting_date', '-pk')
        verbose_name = "Workday Transaction"
        permissions = (
            ('import_workdaytransaction', 'Import Workday CSV exports'),
        )
        constraints = (
            # The duplicate guard, at the level that actually holds: a given
            # line may exist as occurrence 1, 2, 3... but each occurrence only
            # once, so re-uploading a file cannot double the ledger even if two
            # people upload it at the same moment.
            models.UniqueConstraint(
                fields=('row_fingerprint', 'fingerprint_ordinal'),
                name='finance_workday_line_occurrence_once'),
        )

    def __str__(self):
        return "%s – %s (%s)" % (self.reference, self.description, self.net_amount)

    def get_absolute_url(self):
        """ The detail page for this bank line and its slices. """
        return reverse('finance:txn-detail', args=[self.pk])

    # -- identity -----------------------------------------------------------
    def compute_fingerprint(self):
        """
        The content hash that decides whether this row is already in the ledger.

        Derived from the fields Workday itself fills in, never from anything
        LNL adds afterwards, so re-importing an overlapping export recognises
        rows it has already seen. See :func:`workday_fingerprint`.
        """
        return workday_fingerprint(
            self.accounting_date, self.net_amount, self.operational_transaction,
            self.supplier, self.employee, self.memo, self.worktags_json)

    def assign_identity(self, ordinal=None):
        """
        Fill in the fingerprint, and the occurrence number if not supplied.

        The importer works out ordinals for a whole file at once, because it
        alone can tell "this file lists the charge twice" from "this file is a
        re-upload". A one-off insert (the admin, a test, a shell) has no such
        context, so it simply takes the next free occurrence.
        """
        self.row_fingerprint = self.compute_fingerprint()
        if ordinal is not None:
            self.fingerprint_ordinal = ordinal
        else:
            self.fingerprint_ordinal = 1 + WorkdayTransaction.objects.filter(
                row_fingerprint=self.row_fingerprint).count()
        return self

    # -- immutability -------------------------------------------------------
    def save(self, *args, **kwargs):
        """ Allow the initial insert; refuse every subsequent write. """
        if self.pk is not None and not kwargs.pop('_allow_update', False):
            raise ValidationError(
                "WorkdayTransaction rows are immutable. Correct the record in Workday and "
                "re-import, or adjust the allocation slices instead.")
        if not self.row_fingerprint:
            self.assign_identity()
        return super(WorkdayTransaction, self).save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """ Refuse. Delete the slices instead, or use the queryset escape hatch. """
        raise ValidationError(
            "WorkdayTransaction rows are immutable and cannot be deleted. Delete the "
            "allocation slices if you need to re-do the reconciliation.")

    # -- convenience --------------------------------------------------------
    @property
    def description(self):
        """
        The best short label this row can offer.

        Who was paid, failing that the start of the memo, failing that an
        honest admission -- a Workday line is not guaranteed to carry either.
        """
        return self.payee or (self.memo[:60] if self.memo else "(no description)")

    @property
    def document_type(self):
        """
        What kind of Workday document this line came off.

        The Operational Transaction reads "Internal Service Delivery:
        25090179-ISD" or "Expense Report: 25061136-EXP", so the part before the
        colon names the document. Journal entry lines have no Operational
        Transaction at all and are identified by having a journal instead.
        """
        reference = (self.operational_transaction or '').strip()
        if ':' in reference:
            return reference.split(':', 1)[0].strip()
        if reference:
            return reference
        return "Journal Entry" if self.journal_reference else ''

    @property
    def payee(self):
        """
        Who the money went to or came from, as far as the export says.

        Internal Service Deliveries -- LNL billing a department, catering,
        campus shipping -- carry neither a Supplier nor an Employee, because
        both sides are WPI. Falling through to "(no payee)" told the Treasurer
        nothing; naming the document type at least says what kind of movement
        it is, and the memo carries the rest.
        """
        named = self.supplier or self.employee
        if named:
            return named
        return self.document_type or ''

    @property
    def fiscal_year(self):
        """ The fiscal year Workday posted this line in. """
        return fiscal_year_for(self.accounting_date)

    @property
    def is_revenue(self):
        """ Money in. The sign is the bank's, and is not ours to argue with. """
        return self.net_amount > 0

    def worktag(self, key, default=''):
        """ Case/format tolerant lookup into ``worktags_json``. """
        return worktag_value(self.worktags_json, key, default)

    @property
    def journal_reference(self):
        """
        The journal's own number, e.g. ``25090054-JE``.

        Workday exports the journal as a sentence -- "25090054-JE - Worcester
        Polytechnic Institute - WPI - 08/31/2025" -- and only the first field
        identifies anything.
        """
        journal = self.worktag('journal')
        return journal.split(' - ')[0].strip() if journal else ''

    @property
    def reference(self):
        """
        What to call this line on screen.

        Journal entry lines carry no Operational Transaction at all, so falling
        back to the journal number keeps every row nameable.
        """
        return self.operational_transaction or self.journal_reference or "(no reference)"

    @property
    def ledger_account(self):
        """ Workday's GL account, e.g. ``71100:Supplies``. """
        return self.worktag('ledger_account')

    @property
    def partition_worktag(self):
        """
        The org code Workday assigned, e.g. ``226-AG Lens & Light Club``.

        Which worktag holds it is configured per :class:`PartitionCode`, so a
        deployment that files these somewhere other than Student Organization
        needs no code change.
        """
        for worktag in partition_worktag_keys():
            value = self.worktag(worktag)
            if value:
                return value
        return ''

    @property
    def journal_line_memo(self):
        """
        The CSV's Journal Line Memo on its own.

        Newer imports keep it as its own worktag. Rows imported before that
        only have the concatenated ``memo``, so fall back to the part before
        the separator that :func:`finance.importers.build_memo` joins on.
        """
        stored = self.worktag('journal_line_memo')
        if stored:
            return stored
        return (self.memo or '').split(MEMO_SEPARATOR)[0].strip()

    @property
    def matched_partition_code(self):
        """
        The :class:`PartitionCode` row this line falls under, if any.

        Which account the money came out of. It decides where a slice of this
        line starts, and nothing more -- see :class:`PartitionCode` for why it
        stopped being a lock.
        """
        for entry in partition_codes():
            if org_code_matches(self.worktag(entry['worktag']), entry['code']):
                return entry
        return None

    @property
    def default_partition(self):
        """ ``'projection'``, ``'event'``, or ``None`` when the code says nothing. """
        match = self.matched_partition_code
        if match is None:
            return None
        return 'projection' if match['is_projection'] else 'event'

    @property
    def defaults_to_projection(self):
        """
        Whether this line starts life on the Projection side.

        A starting position only -- the org code the money left says where it
        probably belongs, and the Treasurer has the final say.
        """
        match = self.matched_partition_code
        return bool(match and match['is_projection'])

    @property
    def crossing_requires_reason(self):
        """
        Whether filing this line on the other side has to be justified.

        True for the account SGA funds for Projection directly: money leaving
        that side is the direction that would breach the isolation rule.
        """
        match = self.matched_partition_code
        return bool(match and match.get('crossing_requires_reason'))

    @property
    def partition_code_label(self):
        """ The org code itself, for messages and badges. """
        match = self.matched_partition_code
        return match['code'] if match else ''

    # -- reconciliation -----------------------------------------------------
    # Each of these prefers the annotation left by ``with_allocation()`` and
    # falls back to its own query, so a single object still behaves correctly
    # while a listing costs one query for the whole page.
    @property
    def allocated_amount(self):
        """ How much of this line has been written up as ledger entries. """
        cached = getattr(self, '_allocated', None)
        if cached is not None:
            return money(cached)
        return money(self.slices.aggregate(t=Sum('amount'))['t'])

    @property
    def unallocated_amount(self):
        """ What's left to carve up. Zero means the line is ready to settle. """
        return money(self.net_amount) - self.allocated_amount

    @property
    def is_fully_allocated(self):
        """ Whether the slices account for the line to the cent. """
        return self.unallocated_amount == ZERO

    @property
    def slice_count(self):
        """ How many ledger entries have been written against this line. """
        cached = getattr(self, '_slice_count', None)
        if cached is not None:
            return cached
        return self.slices.count()

    @property
    def pending_slice_count(self):
        """ How many of those entries are not settled yet. """
        cached = getattr(self, '_pending_count', None)
        if cached is not None:
            return cached
        return self.slices.exclude(status=TransactionStatus.SETTLED).count()

    @property
    def is_reconciled(self):
        """
        Whether this line is finished with.

        All three conditions are required: something was written against it,
        nothing is still pending, and the amounts balance exactly.
        """
        return (self.slice_count > 0
                and self.pending_slice_count == 0
                and self.is_fully_allocated)

    @property
    def is_split(self):
        """ Whether this one charge was carved up into several entries. """
        return self.slice_count > 1

    @transaction.atomic
    def settle(self):
        """ Mark every slice settled. Refuses unless the split balances exactly. """
        if not self.slices.exists():
            raise ValidationError("Cannot settle a transaction with no allocation slices.")
        if not self.is_fully_allocated:
            raise ValidationError(
                "Cannot settle: allocations total %s but the bank line is %s (%s unallocated)."
                % (self.allocated_amount, self.net_amount, self.unallocated_amount))
        self.slices.update(status=TransactionStatus.SETTLED)


# ---------------------------------------------------------------------------
# Table B: the mutable allocation slice
# ---------------------------------------------------------------------------

class ParsedTransactionQuerySet(models.QuerySet):
    """ The filters behind the global filter bar and the ledger page. """

    def for_fiscal_year(self, fiscal_year):
        """ Entries dated inside one fiscal year; a falsy year means all of them. """
        if not fiscal_year:
            return self
        start, end = fiscal_year_bounds(fiscal_year)
        return self.filter(effective_date__range=(start, end))

    def partition(self, is_projection):
        """ The Event | Projection partition switch. ``None`` means no filter. """
        if is_projection is None:
            return self
        return self.filter(is_projection=is_projection)

    def revenue(self):
        """
        Money genuinely coming in.

        Refunds are excluded despite being positive: a credit back on a
        purchase is a reduction in spending, not income, and counting it as
        income would overstate both sides of the dashboard at once.
        """
        return self.filter(amount__gt=0, refund_of__isnull=True)

    def expenses(self):
        """ Spending, including the refunds that offset it. """
        return self.filter(Q(amount__lt=0) | Q(refund_of__isnull=False))


@reversion.register()
class ParsedTransaction(models.Model):
    """
    One allocation slice of internal meaning. Many slices may point at a single
    :class:`WorkdayTransaction` (the split-purchase case), or at none at all
    (an encumbrance logged before the bank feed catches up).

    Three shapes, distinguished by :attr:`entry_type`:

    * **Revenue**  -- ``amount > 0``, routes to an Event or a non-event source.
    * **Expense**  -- ``amount < 0``, routes to a fund/spend category/FR line.
    * **Refund**   -- ``amount > 0`` *and* ``refund_of`` set. A return credit.
      It carries expense routing, not revenue routing, so that crediting money
      back restores the budget line it originally came out of.
    """
    glyphicon = 'list-alt'

    parent_transaction = models.ForeignKey(
        WorkdayTransaction, on_delete=models.CASCADE, null=True, blank=True, related_name='slices',
        help_text="The bank line this slice belongs to. Blank while this is a pending encumbrance.")

    amount = models.DecimalField(
        max_digits=12, decimal_places=2,
        help_text="Positive = money in, negative = money out. Must be non-zero.")
    status = models.CharField(max_length=16, choices=TransactionStatus.choices,
                              default=TransactionStatus.PENDING, db_index=True)
    is_projection = models.BooleanField(
        default=False, db_index=True, verbose_name="Projection partition",
        help_text="Which activity the money was for, which is not always which account paid. "
                  "Starts from the org code on the bank line and from the funding request, "
                  "and can be changed.")

    # Denormalised so the ledger can sort/filter by date without joining, and so
    # encumbrances (which have no bank line yet) still land in a fiscal year.
    effective_date = models.DateField(db_index=True, default=timezone.localdate)

    description = models.CharField(max_length=255, blank=True)
    audit_explanation = models.TextField(
        blank=True, help_text="Why this money moved. Shown to auditors.")
    receipt_file = models.FileField(upload_to='finance/receipts/%Y/%m/', null=True, blank=True,
                                    verbose_name="Receipt")

    # -- Revenue routing (mutually exclusive with expense routing) ----------
    linked_event = models.ForeignKey('events.BaseEvent', on_delete=models.PROTECT,
                                     null=True, blank=True, related_name='subledger_entries',
                                     verbose_name="Linked event")
    non_event_revenue_type = models.ForeignKey(
        RevenueSource, on_delete=models.PROTECT, null=True, blank=True,
        related_name='entries', verbose_name="Non-event revenue type")

    # -- Expense routing (mutually exclusive with revenue routing) ----------
    # PROTECT rather than CASCADE: retiring a category from the admin must not
    # be able to silently delete the money filed under it.
    fund_source = models.ForeignKey(FundSource, on_delete=models.PROTECT, null=True, blank=True,
                                    related_name='entries')
    lnl_spend_category = models.ForeignKey(
        SpendCategory, on_delete=models.PROTECT, null=True, blank=True,
        related_name='entries', verbose_name="LNL spend category")
    fr_line_target = models.ForeignKey(FRLineItem, on_delete=models.PROTECT, null=True, blank=True,
                                       related_name='allocations', verbose_name="Funding request line")

    # -- Refunds ------------------------------------------------------------
    refund_of = models.ForeignKey('self', on_delete=models.PROTECT, null=True, blank=True,
                                  related_name='refunds', verbose_name="Refund of",
                                  help_text="The original purchase this credit reverses")

    project_tag = models.ForeignKey(ProjectTag, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='transactions')

    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                                   blank=True, related_name='subledger_entries')

    objects = ParsedTransactionQuerySet.as_manager()

    # Field groups reused by the forms, the ledger column picker and the tests.
    #
    # linked_event belongs to neither side. On revenue it means "this is what
    # the event earned"; on an expense it means "this cost was incurred for
    # that event" -- a sub-rental billed straight through, where LNL hires a
    # console for one show and the cost is that show's, not the club's. The
    # sign of the amount already distinguishes the two readings.
    REVENUE_FIELDS = ('non_event_revenue_type',)
    EXPENSE_FIELDS = ('fund_source', 'lnl_spend_category', 'fr_line_target')
    SHARED_FIELDS = ('linked_event',)

    class Meta:
        ordering = ('-effective_date', '-pk')
        verbose_name = "Subledger Entry"
        verbose_name_plural = "Subledger Entries"
        permissions = (
            ('view_subledger', 'View the financial subledger'),
            ('edit_subledger', 'Create and edit subledger entries'),
            ('settle_subledger', 'Reconcile and settle transactions'),
            ('view_subledger_receipts', 'View uploaded receipts'),
        )
        constraints = [
            # A zero-amount slice is always a data-entry mistake.
            models.CheckConstraint(check=~Q(amount=0), name='finance_slice_amount_nonzero'),
            # Encumbrances have no bank line yet, so they cannot be settled.
            models.CheckConstraint(
                check=Q(parent_transaction__isnull=False) | Q(status='pending'),
                name='finance_encumbrance_must_be_pending'),
            # Expenses and refunds may not be classified as non-event revenue.
            # linked_event is deliberately absent: an expense may name the event
            # it was incurred for. See SHARED_FIELDS above.
            models.CheckConstraint(
                check=(Q(amount__gt=0, refund_of__isnull=True)
                       | Q(non_event_revenue_type__isnull=True)),
                name='finance_no_revenue_routing_on_expense'),
            # Revenue may not carry expense routing.
            models.CheckConstraint(
                check=(Q(amount__lt=0)
                       | Q(refund_of__isnull=False)
                       | Q(fund_source__isnull=True, lnl_spend_category__isnull=True,
                           fr_line_target__isnull=True)),
                name='finance_no_expense_routing_on_revenue'),
            # A refund credits money back; it can never be negative.
            models.CheckConstraint(
                check=Q(refund_of__isnull=True) | Q(amount__gt=0),
                name='finance_refund_must_be_positive'),
        ]

    def __str__(self):
        return "%s %s" % (self.get_entry_type_display(), money(self.amount))

    def get_absolute_url(self):
        """ This entry's own page, with its audit trail. """
        return reverse('finance:entry-detail', args=[self.pk])

    @property
    def picker_label(self):
        """
        How this line reads in a dropdown that offers other people's rows.

        ``__str__`` is "Expense -129.00", which is what the Refund-of picker
        used to show: thirty options, all of them the word Expense and a
        number, with nothing to say which purchase each one was. Picking the
        right one meant opening the ledger in another tab.

        So the label carries what actually identifies a purchase to the person
        choosing -- when it was, who was paid, what it was for, and how much of
        it is still refundable, since a partly-credited line is the single
        easiest one to pick by mistake.
        """
        parts = []
        if self.effective_date:
            parts.append(date_format(self.effective_date, 'M j'))
        who = self.payee_label
        if who:
            parts.append(who)
        what = (self.description or '').strip()
        # The payee is often repeated verbatim as the description; saying it
        # twice in one option costs the width the amount needs.
        if what and what.lower() != who.lower():
            parts.append(what)

        gross = abs(money(self.amount))
        left = self.refundable_remaining
        if self.amount is None or self.amount >= 0 or left == gross:
            tail = "$%s" % gross
        elif left:
            tail = "$%s — $%s left to refund" % (gross, left)
        else:
            tail = "$%s — fully refunded" % gross

        parts.append(tail)
        return " · ".join(parts)

    @property
    def payee_label(self):
        """ Who the money went to, from the bank line when there is one. """
        parent = self.parent_transaction
        if parent is not None and parent.payee:
            return parent.payee
        return ''

    @property
    def refundable_remaining(self):
        """
        How much of this expense has not been credited back yet.

        Positive, and zero once the whole thing has been returned. Mirrors the
        rule enforced in :meth:`clean`: refunds may not exceed the original.

        Uses the ``_credited`` annotation when the row was loaded through the
        refund picker's queryset. Every option in that dropdown asks this
        question, and without the annotation a list of forty purchases is forty
        extra aggregates -- the same trap :meth:`FRLineItem.spent` avoids.
        """
        if self.amount is None or self.amount >= 0:
            return ZERO
        annotated = getattr(self, '_credited', None)
        if annotated is not None:
            already = money(annotated)
        elif self.pk:
            already = money(self.refunds.aggregate(t=Sum('amount'))['t'])
        else:
            already = ZERO
        return max(ZERO, -money(self.amount) - already)

    # -- classification -----------------------------------------------------
    REVENUE, EXPENSE, REFUND, ENCUMBRANCE = 'revenue', 'expense', 'refund', 'encumbrance'

    @property
    def entry_type(self):
        """
        What this row *is*, in the words the ledger uses for it.

        An encumbrance is money reserved for a purchase that has not happened
        yet, and it is not interchangeable with an expense: no money has left
        the account, there is no bank line behind it, and it disappears again
        when the real charge arrives. Calling it an Expense in the Type column
        made the two impossible to tell apart in the one view where the whole
        point is telling rows apart.

        It is deliberately checked before the sign, because an encumbrance is
        always negative and would otherwise read as an ordinary expense.
        """
        if self.refund_of_id is not None:
            return self.REFUND
        if self.parent_transaction_id is None:
            return self.ENCUMBRANCE
        return self.REVENUE if (self.amount or 0) > 0 else self.EXPENSE

    ENTRY_TYPE_LABELS = {
        REVENUE: 'Revenue',
        EXPENSE: 'Expense',
        REFUND: 'Refund',
        ENCUMBRANCE: 'Encumbrance',
    }

    def get_entry_type_display(self):
        """
        The human label for :attr:`entry_type`.

        Written out by hand rather than generated, because ``entry_type`` is
        derived from the amount and the links rather than stored in a field
        with choices, so Django's own ``get_FOO_display`` does not exist here.
        """
        return self.ENTRY_TYPE_LABELS[self.entry_type]

    @property
    def is_revenue(self):
        """ Money in, as opposed to spending, a refund or an encumbrance. """
        return self.entry_type == self.REVENUE

    @property
    def is_expense(self):
        """
        Everything that is not money coming in.

        Refunds are contra-expenses and encumbrances are expenses that have not
        happened yet; both carry expense routing, so both answer yes. Only the
        Type column distinguishes them, and it does that through
        :attr:`entry_type`.
        """
        return self.entry_type != self.REVENUE

    @property
    def is_encumbrance(self):
        """ Money reserved for a purchase that has not reached Workday yet. """
        return self.entry_type == self.ENCUMBRANCE

    @property
    def fiscal_year(self):
        """
        The fiscal year this entry falls in.

        Taken from ``effective_date``, which for a slice of a bank line is the
        date of the purchase rather than the date somebody got round to
        filing it.
        """
        return fiscal_year_for(self.effective_date)

    # -- inherited event metadata (zero double data entry) ------------------
    @property
    def client_type(self):
        """
        Student Org vs Department, inherited from the linked event's billing
        org rather than re-keyed by the Treasurer.
        """
        event = self.linked_event
        if event is None:
            return ClientType.UNKNOWN
        fund = getattr(event, 'workday_fund', None)  # Event2019 carries its own
        if fund is None:
            org = event.billing_org or event.org.first()
            fund = getattr(org, 'workday_fund', None) if org else None
        if fund is None:
            return ClientType.UNKNOWN
        return (ClientType.STUDENT_ORG if fund == student_org_workday_fund()
                else ClientType.DEPARTMENT)

    @property
    def client_type_display(self):
        """ :attr:`client_type` as the words a person would read. """
        return ClientType(self.client_type).label

    @property
    def event_services(self):
        """ The service breakdown (Lighting, Sound, ...) inherited from the event. """
        event = self.linked_event
        if event is None:
            return []
        # Event2019 keeps services in ServiceInstance rows...
        instances = getattr(event, 'serviceinstance_set', None)
        if instances is not None:
            names = list(instances.values_list('service__category__name', flat=True))
            if names:
                return sorted(set(n for n in names if n))
        # ...while the legacy Event model has direct FKs.
        legacy = []
        for attr, label in (('lighting', 'Lighting'), ('sound', 'Sound'), ('projection', 'Projection')):
            if getattr(event, attr, None) is not None:
                legacy.append(label)
        return legacy

    @property
    def event_services_display(self):
        """ The inherited service list as one comma-separated string. """
        return ", ".join(self.event_services)

    # -- validation ---------------------------------------------------------
    def _normalise_blanks(self):
        """
        Collapse '' to None on the routing links so the DB constraints read
        cleanly. These are foreign keys now, so a blank arrives as an empty
        ``*_id`` rather than an empty string, but both are worth catching.
        """
        for field in ('non_event_revenue_type', 'fund_source', 'lnl_spend_category'):
            if getattr(self, '%s_id' % field, None) == '':
                setattr(self, '%s_id' % field, None)

    def clean(self):
        """
        Enforce the rules that keep the ledger auditable.

        Errors are collected per field and raised together rather than one at
        a time, so a half-filled form comes back with everything wrong with it
        marked at once. The amount is the exception: with no amount there is
        no direction, and every rule below depends on knowing the direction.

        The rules themselves are numbered in the comments, and the important
        one is that revenue routing and expense routing are mutually
        exclusive. Matching database constraints back all of this up, because
        bulk actions and shell writes never call ``full_clean()``.
        """
        self._normalise_blanks()
        errors = {}

        if self.amount is None or self.amount == 0:
            errors['amount'] = "Amount must be non-zero."
            raise ValidationError(errors)

        # -- Rule 2: revenue and expense routing are mutually exclusive -----
        if self.entry_type == self.REVENUE:
            for field in self.EXPENSE_FIELDS:
                if getattr(self, field) is not None:
                    errors[field] = "Revenue entries cannot carry expense routing."
            if self.linked_event is None and self.non_event_revenue_type is None:
                errors['linked_event'] = (
                    "Revenue must link to an Event, or be classified as non-event revenue.")
            if self.linked_event is not None and self.non_event_revenue_type is not None:
                errors['non_event_revenue_type'] = (
                    "Pick either a linked Event or a non-event revenue type, not both.")
        else:
            for field in self.REVENUE_FIELDS:
                if getattr(self, field) is not None:
                    errors[field] = "Expense entries cannot carry revenue routing."

        # -- Rule 3: refunds must point at a real expense ------------------
        if self.refund_of_id is not None:
            original = self.refund_of
            if original.pk == self.pk:
                errors['refund_of'] = "A transaction cannot be a refund of itself."
            elif not original.is_expense:
                errors['refund_of'] = "Refunds may only reverse an expense line."
            else:
                # You cannot get more money back than you spent. Anything beyond
                # the original is revenue, and belongs on its own line.
                already = money(original.refunds.exclude(pk=self.pk).aggregate(
                    t=Sum('amount'))['t'])
                refundable = -original.amount - already
                if self.amount > refundable:
                    errors['amount'] = (
                        "That is more than is left to refund. The original expense was $%s and "
                        "$%s has already been credited back, leaving $%s."
                        % (-original.amount, already, refundable))

        # -- Funding request lines -----------------------------------------
        # A fund flagged requires_funding_request is money awarded for a named
        # purpose, so it has to burn down one of that request's lines; every
        # other fund is forbidden from naming one, or an FR's balance would
        # change without any award behind it.
        if self.entry_type != self.REVENUE:
            fund = self.fund_source
            line = self.fr_line_target
            if fund is not None and fund.requires_funding_request and line is None:
                errors['fr_line_target'] = (
                    "%s money has to be charged to a specific funding request line." % fund)
            elif line is not None and (fund is None or not fund.requires_funding_request):
                errors['fr_line_target'] = (
                    "Only a fund that draws on a funding request may name an FR line. "
                    "Either change the fund, or clear this.")

        # -- The partition -------------------------------------------------
        # An SGA award was heard as either a Projection request or an Event
        # Production one, and that decision is more specific than the account
        # the money happened to leave from. So the award settles the side
        # rather than arguing with it: buying Projection gear out of 226-AG on
        # a Projection funding request is the normal way LNL does it.
        self._apply_partition_default()
        self._adopt_partition_from_funding_request()

        parent = self.parent_transaction
        if parent is not None and self.crosses_partition and parent.crossing_requires_reason:
            if not (self.audit_explanation or '').strip():
                errors['audit_explanation'] = (
                    "This is %s money being filed as %s spending. That is allowed, but say "
                    "why here -- %s is funded by SGA for Projection, so money leaving that "
                    "side has to be explained." % (
                        parent.partition_code_label,
                        "Projection" if self.is_projection else "Event Production",
                        parent.partition_code_label))

        # -- Rule 1: a split must balance exactly before anything settles ---
        if self.status == TransactionStatus.SETTLED:
            if parent is None:
                errors['status'] = (
                    "An encumbrance cannot be settled until it is matched to an imported "
                    "Workday transaction.")
            else:
                siblings = money(parent.slices.exclude(pk=self.pk).aggregate(
                    t=Sum('amount'))['t'])
                allocated = siblings + money(self.amount)
                if allocated != money(parent.net_amount):
                    errors['status'] = (
                        "Allocations total %s but the bank line is %s. Settle only once the "
                        "unallocated remainder is exactly $0.00."
                        % (allocated, money(parent.net_amount)))

        if errors:
            raise ValidationError(errors)

    def __init__(self, *args, **kwargs):
        """
        Remember whether anyone actually chose a side.

        ``is_projection`` is a plain boolean, so "Event Production" and "nobody
        said" look identical on the instance. Rows loaded from the database
        arrive positionally with every field filled, and are stated by
        definition; a caller passing the keyword has stated it too. Everything
        else gets the org code's answer -- see :meth:`_apply_partition_default`.
        """
        self._partition_was_stated = bool(args) or 'is_projection' in kwargs
        super(ParsedTransaction, self).__init__(*args, **kwargs)

    def state_partition(self):
        """
        Mark the side as deliberately chosen.

        Called by any form that puts the tick box in front of a human. A form
        that does not render it -- the split modal, which has no room for a
        column nobody usually changes -- deliberately does not call this, so
        its slices inherit the account's side instead.
        """
        self._partition_was_stated = True

    def _apply_partition_default(self):
        """ Start an unanswered new entry on the side its account belongs to. """
        if not self._state.adding or getattr(self, '_partition_was_stated', True):
            return
        if self.parent_transaction_id is None:
            return
        default = self.parent_transaction.default_partition
        if default is not None:
            self.is_projection = (default == 'projection')

    def save(self, *args, **kwargs):
        """
        Settle the partition and the date before writing.

        This runs on every write, including the ones that skip validation
        entirely -- bulk actions, the shell, data migrations -- which is
        exactly why the partition rules are applied here and not only in
        ``clean()``. See the comment below for which of the two sources of a
        partition is allowed to override a deliberate answer, and which is not.
        """
        self._normalise_blanks()
        self._apply_partition_default()
        # A funding request names its side explicitly, so it is applied here as
        # well as in clean() -- bulk actions and shell writes skip full_clean(),
        # and an award silently paid from the wrong partition corrupts two
        # burndowns at once. The org code, by contrast, is only ever a starting
        # position: overwriting a deliberate answer with it is the bug this
        # replaced.
        self._adopt_partition_from_funding_request()
        if self.parent_transaction_id is not None and not self.effective_date:
            self.effective_date = self.parent_transaction.accounting_date
        return super(ParsedTransaction, self).save(*args, **kwargs)

    def _adopt_partition_from_funding_request(self):
        """ Take the side from the funding request line, when there is one. """
        if self.fr_line_target_id is None:
            return
        request = self.fr_line_target.funding_request
        self.is_projection = request.is_projection

    @property
    def crosses_partition(self):
        """
        True when this entry sits on the opposite side from the account it was
        paid out of. Legitimate and common; worth showing on screen.
        """
        parent = self.parent_transaction if self.parent_transaction_id else None
        if parent is None:
            return False
        default = parent.default_partition
        if default is None:
            return False
        return (default == 'projection') != bool(self.is_projection)

    @property
    def partition_note(self):
        """ One sentence for the badge, or ``''`` when nothing crossed. """
        if not self.crosses_partition:
            return ''
        return ("Paid out of %s but filed as %s spending."
                % (self.parent_transaction.partition_code_label,
                   "Projection" if self.is_projection else "Event Production"))
