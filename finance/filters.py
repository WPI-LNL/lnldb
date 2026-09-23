"""
Shared plumbing for the persistent top bar (fiscal year + Event | Projection).

Every downstream view reads its filter state through :func:`get_filter_state`,
so the two controls behave identically on all five pages and survive
navigation via querystring.
"""
from django.db.models import Q

from finance.models import current_fiscal_year, fiscal_year_bounds, fiscal_year_choices

PARTITION_ALL = 'all'
PARTITION_EVENT = 'event'
PARTITION_PROJECTION = 'projection'
VALID_PARTITIONS = (PARTITION_ALL, PARTITION_EVENT, PARTITION_PROJECTION)

# Explicit sentinel for "no fiscal-year filter". Needed because an absent
# parameter means "fall back to the session", not "show every year".
ALL_YEARS = 'all'


class FilterState(object):
    """ The resolved state of the global filter bar for one request. """

    def __init__(self, fiscal_year, partition):
        """ Normalise a partition we do not recognise down to "all". """
        self.fiscal_year = fiscal_year
        self.partition = partition if partition in VALID_PARTITIONS else PARTITION_ALL

    @property
    def projection_flag(self):
        """ ``True`` = projection only, ``False`` = event only, ``None`` = both. """
        if self.partition == PARTITION_PROJECTION:
            return True
        if self.partition == PARTITION_EVENT:
            return False
        return None

    @property
    def bounds(self):
        """ The ``(start, end)`` dates of the selected year, or ``(None, None)``. """
        return fiscal_year_bounds(self.fiscal_year) if self.fiscal_year else (None, None)

    # Both filters are always written out in full, including when they hold
    # their default value. Omitting a default made "reset to All" look
    # identical to "expressed no opinion", so the remembered session value won
    # and the All / All-years buttons could never be selected.
    @property
    def querystring(self):
        """ Re-emit the current filter so links preserve it. """
        return 'fy=%s&partition=%s' % (self.fiscal_year or ALL_YEARS,
                                       self.partition or PARTITION_ALL)

    #: The only things ``url_with`` can override. Named so that passing
    #: anything else is caught rather than ignored.
    OVERRIDABLE = ('fiscal_year', 'partition')

    def url_with(self, **overrides):
        """
        Build a querystring with some filter values replaced.

        Unknown names raise rather than being dropped. Every caller is a
        template tag, where a quietly ignored keyword produces a link that
        looks right, goes somewhere, and changes nothing -- the hardest kind of
        bug to notice, because the page it lands on is a real page.
        """
        unknown = set(overrides) - set(self.OVERRIDABLE)
        if unknown:
            raise TypeError(
                "url_with() got unexpected filter name(s): %s. Valid names are %s."
                % (", ".join(sorted(unknown)), ", ".join(self.OVERRIDABLE)))
        fy = overrides.get('fiscal_year', self.fiscal_year)
        partition = overrides.get('partition', self.partition)
        return '?fy=%s&partition=%s' % (fy or ALL_YEARS, partition or PARTITION_ALL)

    def apply(self, queryset, date_field='effective_date'):
        """ Narrow a ParsedTransaction queryset to the current filter. """
        if self.fiscal_year:
            start, end = self.bounds
            queryset = queryset.filter(**{'%s__range' % date_field: (start, end)})
        flag = self.projection_flag
        if flag is not None:
            queryset = queryset.filter(is_projection=flag)
        return queryset

    def apply_to_workday(self, queryset):
        """
        Narrow a WorkdayTransaction queryset.

        A bank line has no side of its own -- only the account it came out of,
        which is what the queue is asking about, since nothing there has been
        filed yet. The codes and the worktag they live in come from the
        :class:`finance.models.PartitionCode` table; this used to hard-code
        ``315-AG`` and read it from Ledger Account, which is not the column real
        exports put it in, so the Projection filter matched nothing at all.
        """
        from finance.models import partition_codes

        if self.fiscal_year:
            start, end = self.bounds
            queryset = queryset.filter(accounting_date__range=(start, end))

        flag = self.projection_flag
        if flag is None:
            return queryset

        matches = Q(pk__in=[])
        for entry in partition_codes():
            if entry['is_projection']:
                matches |= Q(**{'worktags_json__%s__startswith' % entry['worktag']:
                                entry['code']})
        # "Event Production" deliberately means "not Projection" rather than
        # "carries the 226-AG code": a line with a blank or unfamiliar org code
        # would otherwise appear in neither view and go quietly unreconciled.
        #
        # Excluded by primary key rather than by negating the lookup, because a
        # JSON key lookup that finds no key is NULL rather than False, and
        # exclude() drops those rows too -- which would hide exactly the
        # untagged lines this branch exists to keep.
        if flag:
            return queryset.filter(matches)
        return queryset.exclude(pk__in=queryset.model.objects.filter(matches).values('pk'))


def get_filter_state(request):
    """
    Resolve the filter bar from the querystring, remembering the last choice in
    the session so the partition survives a jump between pages.
    """
    raw_fy = (request.GET.get('fy') or '').strip()
    if raw_fy == ALL_YEARS:
        fiscal_year = None
        request.session['finance_fy'] = ALL_YEARS
    elif raw_fy.isdigit():
        fiscal_year = int(raw_fy)
        request.session['finance_fy'] = fiscal_year
    else:
        remembered = request.session.get('finance_fy')
        if remembered == ALL_YEARS:
            fiscal_year = None
        elif isinstance(remembered, int):
            fiscal_year = remembered
        else:
            fiscal_year = current_fiscal_year()

    partition = request.GET.get('partition')
    if partition in VALID_PARTITIONS:
        request.session['finance_partition'] = partition
    else:
        partition = request.session.get('finance_partition', PARTITION_ALL)

    return FilterState(fiscal_year, partition)


def filter_context(request):
    """ Context every finance page needs for the top bar. """
    state = get_filter_state(request)
    return {
        'filter_state': state,
        'fiscal_year_options': fiscal_year_choices(),
        'current_fiscal_year': current_fiscal_year(),
        'partition_options': (
            (PARTITION_ALL, 'All'),
            (PARTITION_EVENT, 'Event Production'),
            (PARTITION_PROJECTION, 'Projection'),
        ),
    }
