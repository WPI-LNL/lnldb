"""
Every form the finance pages put in front of a Treasurer.

The organising idea is Poka-Yoke: wherever a rule can be enforced by the
form not *having* a field, it is enforced that way rather than by
validating one. :class:`BaseAllocationForm` removes expense routing from a
revenue form outright, so a revenue entry cannot carry a fund source even
if the client-side JS is bypassed -- which matters, because the database
has a constraint saying the same thing and a stray value would surface as
an IntegrityError rather than a field error.

The custom fields at the top exist for a related reason. A dropdown is a
place to make a quiet mistake, so each one is labelled with whatever makes
the wrong option obviously wrong -- the year a funding request belongs to,
how much of a line is left, which purchase a refund is against.
"""
from decimal import Decimal

from ajax_select.fields import AutoCompleteSelectField
from crispy_forms.helper import FormHelper
from django import forms
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.db.models import DecimalField, F, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.forms.models import BaseInlineFormSet, inlineformset_factory
from django.utils.formats import date_format
from mptt.forms import TreeNodeChoiceField

from finance.importers import CSV_EXTENSIONS, XLSX_EXTENSIONS
from finance.models import (FRLineItem, FundingRequest, FundSource, ParsedTransaction,
                            ProjectTag, RevenueSource, SpendCategory, TransactionStatus,
                            WorkdayTransaction, current_fiscal_year,
                            event_passthrough_category, fiscal_year_bounds,
                            fiscal_year_choices, fiscal_year_for)
from finance.suggestions import lookups_for_form, suggest_all


class ProjectTagChoiceField(TreeNodeChoiceField):
    """
    A project picker whose options are nested by depth, so a sub-project is
    never mistaken for a top-level one::

        NEL26 — New Equipment List 2026
            └ D60-LUSTR — D60 Lustr Fixtures

    MPTT's default manager already orders by tree position, so children render
    directly beneath their parent.
    """

    def __init__(self, *args, **kwargs):
        """ Default to the live tags, optional, labelled "Project". """
        kwargs.setdefault('queryset', ProjectTag.objects.filter(archived=False))
        kwargs.setdefault('required', False)
        kwargs.setdefault('label', "Project")
        super(ProjectTagChoiceField, self).__init__(*args, **kwargs)

    def label_from_instance(self, obj):
        """ Render one option at its depth in the tree. """
        # Overrides TreeNodeChoiceField's dashes; the model owns the format so
        # the raw <select> in the ledger filter stays identical.
        return obj.indented_label


class FRLineSelect(forms.Select):
    """
    Carries each line's expected routing onto its ``<option>``.

    A funding request line was written for a purpose -- "Consumables",
    "Software Licenses" -- and that purpose was already recorded when the award
    was entered. Re-typing it on every transaction charged to the line is
    exactly the double data entry this module exists to avoid, so the browser
    fills it in from here.
    """

    def create_option(self, name, value, *args, **kwargs):
        """ Attach the line's category and project tag as data attributes. """
        option = super(FRLineSelect, self).create_option(name, value, *args, **kwargs)
        line = getattr(value, 'instance', None)
        if line is not None:
            if line.lnl_spend_category_id:
                option['attrs']['data-spend-category'] = str(line.lnl_spend_category_id)
            if line.project_tag_id:
                option['attrs']['data-project-tag'] = str(line.project_tag_id)
        return option


class FRLineChoiceField(forms.ModelChoiceField):
    """
    Funding request lines, labelled with the two things you can silently get
    wrong: the fiscal year the request belongs to, and how much of the line is
    left. See :attr:`finance.models.FRLineItem.picker_label`.
    """
    widget = FRLineSelect

    def __init__(self, *args, **kwargs):
        """
        Start empty; the form narrows this to the relevant year itself.

        An unfiltered default would offer every line ever awarded, which is
        the mistake :meth:`BaseAllocationForm._narrow_fr_lines` exists to
        prevent.
        """
        kwargs.setdefault('queryset', FRLineItem.objects.none())
        kwargs.setdefault('required', False)
        kwargs.setdefault('label', "Funding request line")
        super(FRLineChoiceField, self).__init__(*args, **kwargs)

    def label_from_instance(self, obj):
        """ Label the line with its year and remaining balance. """
        return obj.picker_label


class RefundTargetChoiceField(forms.ModelChoiceField):
    """
    The "Refund of" picker.

    Its options are other people's purchases, and a ``ParsedTransaction``
    stringifies as "Expense -129.00" -- so this dropdown was thirty rows of the
    word Expense and a number, with nothing to say which purchase each one was.
    See :attr:`finance.models.ParsedTransaction.picker_label` for what it says
    instead.
    """

    def __init__(self, *args, **kwargs):
        """
        Start empty, and say plainly what leaving it blank means.

        The form fills the queryset in from
        :meth:`BaseAllocationForm._refundable_queryset`, which is what keeps
        already-fully-refunded purchases out of it.
        """
        kwargs.setdefault('queryset', ParsedTransaction.objects.none())
        kwargs.setdefault('required', False)
        kwargs.setdefault('label', "Refund of")
        kwargs.setdefault('empty_label', "Not a refund — this is money coming in")
        super(RefundTargetChoiceField, self).__init__(*args, **kwargs)

    def label_from_instance(self, obj):
        """ Label the option with the purchase, not the word "Expense". """
        return obj.picker_label


class FundSourceSelect(forms.Select):
    """
    Tags each option with whether that fund needs a funding request line, so
    the browser can show or hide the FR picker without a round trip. The
    server re-checks regardless; this only saves the Treasurer from being
    offered a field that cannot legally be filled in.
    """

    def create_option(self, name, value, *args, **kwargs):
        """ Flag the funds that need a funding request line. """
        option = super(FundSourceSelect, self).create_option(name, value, *args, **kwargs)
        fund = getattr(value, 'instance', None)
        if fund is not None and getattr(fund, 'requires_funding_request', False):
            option['attrs']['data-requires-fr'] = '1'
        return option


# ---------------------------------------------------------------------------
# Global filter bar
# ---------------------------------------------------------------------------

PARTITION_CHOICES = (
    ('all', 'All'),
    ('event', 'Event Production'),
    ('projection', 'Projection'),
)


class FilterBarForm(forms.Form):
    """ The persistent top bar: fiscal year + Event | Projection partition. """
    fiscal_year = forms.ChoiceField(required=False, label="Fiscal Year")
    partition = forms.ChoiceField(choices=PARTITION_CHOICES, required=False, initial='all')

    def __init__(self, *args, **kwargs):
        """
        Build the year list at instantiation, not at import.

        The choices depend on what is in the ledger and on the fiscal year
        start month, both of which change while the process is running.
        """
        super(FilterBarForm, self).__init__(*args, **kwargs)
        choices = [('', 'All years')] + [(str(fy), label) for fy, label in fiscal_year_choices()]
        self.fields['fiscal_year'].choices = choices

    @property
    def partition_flag(self):
        """ ``True`` = projection only, ``False`` = event only, ``None`` = both. """
        value = self.cleaned_data.get('partition') if self.is_valid() else None
        if value == 'projection':
            return True
        if value == 'event':
            return False
        return None

    @property
    def selected_fiscal_year(self):
        """ The chosen year as an int, or ``None`` for "all years". """
        if not self.is_valid():
            return None
        raw = self.cleaned_data.get('fiscal_year')
        return int(raw) if raw else None


# ---------------------------------------------------------------------------
# CSV ingestion
# ---------------------------------------------------------------------------

class WorkdayCSVUploadForm(forms.Form):
    """
    The file picker at the top of the ingestion queue.

    Validation here is only what can be judged from the file itself --
    extension and size. Whether the contents are really a journal export is
    the importer's call, and it can say something far more useful about a
    file that is not.
    """
    csv_file = forms.FileField(
        label="Workday journal export",
        help_text="Drag a .csv or .xlsx straight out of Workday. Re-uploading the same file "
                  "is safe — lines already imported are skipped.",
        widget=forms.ClearableFileInput(attrs={
            'accept': ('.csv,.tsv,.txt,.xlsx,.xlsm,text/csv,'
                       'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
            'class': 'hidden-file-input'}))
    dry_run = forms.BooleanField(
        required=False, initial=False, label="Preview only",
        help_text="Parse and report without writing anything to the database.")

    def __init__(self, *args, **kwargs):
        """ Render without a ``<form>`` tag; the template supplies one. """
        super(WorkdayCSVUploadForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        # base_finance.html emits the autocomplete scripts once for the whole
        # app, so crispy must not emit them again: its copy also carries a
        # jQuery UI 1.13 theme, and the widget here runs on jQuery UI 1.10.
        # Two themes over one widget is what made the dropdown flicker.
        self.helper.include_media = False

    def clean_csv_file(self):
        """
        Reject anything that is obviously not a journal export.

        The size cap is a sanity check rather than a real limit: a year of
        journal lines is a few hundred kilobytes, so 15 MB means somebody
        picked the wrong file.
        """
        f = self.cleaned_data['csv_file']
        name = (f.name or '').lower()
        if not name.endswith(CSV_EXTENSIONS + XLSX_EXTENSIONS):
            raise ValidationError(
                "That is neither a CSV nor an .xlsx workbook. Export the journal from Workday "
                "in either format. (Old .xls files need saving as .xlsx first.)")
        if f.size > 15 * 1024 * 1024:
            raise ValidationError("That file is larger than 15 MB — is it really a journal export?")
        return f


# ---------------------------------------------------------------------------
# Allocation slices
# ---------------------------------------------------------------------------

class BaseAllocationForm(forms.ModelForm):
    """
    Shared behaviour for editing a :class:`ParsedTransaction`.

    The Poka-Yoke rule -- revenue routing and expense routing are mutually
    exclusive -- is enforced by *removing* the irrelevant fields from the form
    entirely, so a revenue form is structurally incapable of submitting a fund
    source even if the client-side JS is bypassed.

    ``linked_event`` is the exception, and appears on both: revenue earned by
    an event, and costs incurred for one.
    """
    linked_event = AutoCompleteSelectField('Events', required=False, label="Linked event",
                                           help_text="Search by event name or client")
    project_tag = ProjectTagChoiceField()
    fr_line_target = FRLineChoiceField()

    # Ticking this widens the FR picker to other years. It is not a model
    # field: charging across fiscal years is legal, it just has to be meant.
    allow_cross_year_fr = forms.BooleanField(
        required=False, label="Charge a different fiscal year",
        help_text="Only tick this if the spending really belongs to another year's request.")

    # Required on every expense-side form. Left off revenue forms entirely,
    # because a DB constraint forbids revenue from carrying expense routing.
    REQUIRED_ON_EXPENSES = ()

    class Meta:
        model = ParsedTransaction
        fields = ('amount', 'effective_date', 'description', 'linked_event',
                  'non_event_revenue_type', 'fund_source', 'lnl_spend_category',
                  'fr_line_target', 'project_tag', 'is_projection', 'refund_of',
                  'audit_explanation', 'receipt_file')
        widgets = {
            'effective_date': forms.DateInput(attrs={'type': 'date'}),
            'audit_explanation': forms.Textarea(attrs={'rows': 3}),
            'description': forms.TextInput(attrs={'placeholder': 'Short label for the ledger'}),
        }
        # Through ``field_classes`` rather than declared on the class, because a
        # declared field is added to every subclass whatever its ``Meta.fields``
        # says -- and three of the subclasses here leave ``refund_of`` out on
        # purpose. The queue's routing-only form accepting a refund target would
        # be exactly the mutual exclusion this class exists to make structural.
        field_classes = {'refund_of': RefundTargetChoiceField}

    def __init__(self, *args, **kwargs):
        """
        Build the form, then narrow it down to the fields this entry may use.

        Order matters in the block below and the steps are not
        interchangeable: the direction rules delete fields, so everything
        that reads or fills a field has to run after them. Prefilling is last
        of all, so it can only ever touch a field that survived.
        """
        self.parent_transaction = kwargs.pop('parent_transaction', None)
        # Precomputed by callers that render many rows, so the queue works out
        # each line's routing once instead of once per form.
        self._suggestions = kwargs.pop('suggestions', None)
        #: ``{field name: Suggestion}`` for whatever was filled in from the
        #: export, so templates can say so beside the box. Never a guess.
        self.autofilled = {}
        super(BaseAllocationForm, self).__init__(*args, **kwargs)

        if self.parent_transaction is None and self.instance.pk:
            self.parent_transaction = self.instance.parent_transaction

        # Subclasses narrow Meta.fields, so every lookup here is optional.
        self._narrow('refund_of', self._refundable_queryset())
        # Retired vocabulary rows stay on existing records but stop being
        # offered for new ones -- that is what the admin's "active" flag means.
        self._narrow('lnl_spend_category', SpendCategory.objects.active())
        self._narrow('fund_source', FundSource.objects.active())
        self._narrow('non_event_revenue_type', RevenueSource.objects.active())

        fund = self.fields.get('fund_source')
        if fund is not None:
            fund.widget = FundSourceSelect(attrs={'class': 'fin-fund-source'})
            fund.widget.choices = fund.choices

        self._style_widgets()
        self._narrow_fr_lines()
        self._apply_direction_rules()
        self._apply_partition_default()
        self._apply_required_fields()
        self._seed_description()
        # Last, so it only ever fills fields that survived the steps above.
        self._prefill_from_workday()

    def _style_widgets(self):
        """
        Put ``form-control`` on every text-like widget.

        Django renders a bare ``<select>``, crispy adds the class itself, and
        django-ajax-selects does its own thing, so the same three fields came
        out looking like three different form libraries depending on which page
        they were on. Checkboxes and file inputs are left alone: Bootstrap's
        ``form-control`` is wrong for both.
        """
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, (forms.CheckboxInput, forms.FileInput,
                                   forms.RadioSelect, forms.HiddenInput)):
                continue
            existing = widget.attrs.get('class', '')
            if 'form-control' not in existing.split():
                widget.attrs['class'] = (existing + ' form-control').strip()

    # -- fiscal year --------------------------------------------------------
    def _entry_fiscal_year(self):
        """
        The year this slice belongs to: its own date, else the bank line's.

        Used to decide which funding requests are the obvious ones to offer.
        """
        for date in (self.instance.effective_date if self.instance.pk else None,
                     getattr(self.parent_transaction, 'accounting_date', None)):
            if date:
                return fiscal_year_for(date)
        return current_fiscal_year()

    def _cross_year_requested(self):
        """
        Whether the "charge another year" box is ticked.

        Read straight from the raw data rather than from ``cleaned_data``,
        because this runs during ``__init__`` to decide which funding request
        lines to even offer -- long before validation.
        """
        if self.data:
            return bool(self.data.get(self.add_prefix('allow_cross_year_fr')))
        return bool(self.initial.get('allow_cross_year_fr'))

    def _narrow_fr_lines(self):
        """
        Offer this year's funding requests, on this side of the partition.

        Charging an FY25 transaction to an FY26 request is legitimate now and
        then -- an invoice lands late, an award is carried over -- but it is far
        more often a mistake, and one that quietly corrupts two years' burndown
        at once. So the other years are behind a tick box rather than sitting in
        the same dropdown one scroll away.
        """
        field = self.fields.get('fr_line_target')
        if field is None:
            return

        lines = (FRLineItem.objects
                 .filter(funding_request__closed=False)
                 .select_related('funding_request')
                 .with_spend()
                 .order_by('funding_request__fiscal_year', 'funding_request__name',
                           'sort_order', 'pk'))

        fiscal_year = self._entry_fiscal_year()

        # A submitted form keeps the full list so that picking another year
        # fails in clean() with an explanation, rather than as a bare "select a
        # valid choice". The narrowing below is about what gets *offered*.
        if self.is_bound or self._cross_year_requested():
            field.queryset = lines
            field.help_text = ("Every open funding request is listed — check the year on the "
                               "line you pick.")
            return

        same_year = lines.filter(funding_request__fiscal_year=fiscal_year)
        # Whatever is already saved stays selectable, or editing an entry that
        # was deliberately charged across years would silently drop its line.
        current = self.instance.fr_line_target_id if self.instance.pk else None
        if current and not same_year.filter(pk=current).exists():
            field.queryset = lines.filter(
                Q(funding_request__fiscal_year=fiscal_year) | Q(pk=current))
            self.initial.setdefault('allow_cross_year_fr', True)
            field.help_text = "This entry is deliberately charged to another fiscal year."
        else:
            field.queryset = same_year
            field.help_text = "FY%s requests. Tick the box below to use another year." % fiscal_year

    def _refundable_queryset(self):
        """
        Expenses this could be a refund of.

        Restricted to the same fiscal year: a credit note lands within weeks of
        the purchase, so an older match is nearly always the wrong row picked
        out of a long list.

        Three kinds of row are left out because choosing them could only ever
        fail validation, and an option that cannot be picked is worse than no
        option -- it reads as a bug in the ledger rather than a rule:

        * encumbrances, where no money has left the account to come back;
        * this entry itself, which cannot be its own refund;
        * anything already credited back in full.

        ``parent_transaction`` is selected because every label reads the
        payee off it, and a dropdown of forty purchases is otherwise forty
        queries.
        """
        start, end = fiscal_year_bounds(self._entry_fiscal_year())
        qs = (ParsedTransaction.objects
              .filter(amount__lt=0, parent_transaction__isnull=False,
                      effective_date__range=(start, end))
              .select_related('parent_transaction')
              .annotate(_credited=Coalesce(
                  Sum('refunds__amount'), Value(Decimal('0.00')),
                  output_field=DecimalField(max_digits=12, decimal_places=2)))
              .exclude(_credited__gte=F('amount') * Value(-1))
              .order_by('-effective_date', '-pk'))
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        return qs

    def _apply_required_fields(self):
        """ Mark the expense-side fields mandatory, if this form renders them. """
        if self._direction() == 'revenue':
            return
        for name in self.REQUIRED_ON_EXPENSES:
            field = self.fields.get(name)
            if field is not None:
                field.required = True

    # -- filling in from the export -----------------------------------------
    def suggestions(self):
        """ The routing this bank line implies, worked out once per form. """
        if self._suggestions is None and self.parent_transaction is not None:
            self._suggestions = suggest_all(self.parent_transaction)
        return self._suggestions or {}

    def _prefill_from_workday(self):
        """
        Select what the export already tells us, so reconciling is confirming.

        Only *lookups* land here: an LNL category the Treasurer mapped to a
        Workday account or spend category, a funding request whose number the
        memo quotes, a project code appearing verbatim, a fund whose Workday
        code is configured on it. Anything we merely inferred -- which event a
        deposit belongs to, a word noticed in a memo -- stays a chip to click,
        because a pre-selected dropdown gets accepted without being read, and
        that is precisely the wrong thing to do with a guess.

        Skipped entirely for a bound form (the Treasurer's own submission wins)
        and for a saved entry (it already has answers).
        """
        if self.is_bound or self.instance.pk or self.parent_transaction is None:
            return

        for name, suggestion in lookups_for_form(self.suggestions()).items():
            field = self.fields.get(name)
            # Absent because this direction has no such field, or because the
            # subclass does not render it.
            if field is None or self.initial.get(name):
                continue
            if not self._offers(field, suggestion.value):
                continue
            self.initial[name] = suggestion.value
            self.autofilled[name] = suggestion

    @staticmethod
    def _offers(field, value):
        """
        Whether ``field`` can actually be set to ``value``.

        A funding request line from another fiscal year is deliberately not in
        the picker, and pre-filling a value the dropdown does not contain would
        render as an empty box that silently disagrees with the badge next to
        it. So the suggestion is dropped and its chip is left to be clicked,
        which is the path that also asks for the cross-year tick box.
        """
        queryset = getattr(field, 'queryset', None)
        if queryset is None:
            return True
        return queryset.filter(pk=value).exists()

    def _seed_description(self):
        """
        Pre-fill Description from the CSV's Journal Line Memo.

        Only for a brand-new slice, so it never overwrites what the Treasurer
        already typed.
        """
        field = self.fields.get('description')
        if field is None or self.instance.pk or self.parent_transaction is None:
            return
        if not self.initial.get('description'):
            self.initial['description'] = self.parent_transaction.journal_line_memo

    def _narrow(self, name, queryset):
        """ Restrict a choice field's queryset if this subclass renders it. """
        field = self.fields.get(name)
        if field is not None:
            field.queryset = queryset

    # -- direction ----------------------------------------------------------
    def _direction(self):
        """ ``'revenue'`` or ``'expense'`` for the row being edited. """
        amount = None
        if self.data:
            raw = self.data.get(self.add_prefix('amount'))
            try:
                amount = Decimal(raw) if raw not in (None, '') else None
            except Exception:
                amount = None
        if amount is None and self.instance.pk:
            amount = self.instance.amount
        if amount is None and self.parent_transaction is not None:
            amount = self.parent_transaction.net_amount
        if amount is None:
            return None

        is_refund = bool(self.data.get(self.add_prefix('refund_of')) or self.instance.refund_of_id)
        if amount > 0 and not is_refund:
            return 'revenue'
        return 'expense'

    def _apply_direction_rules(self):
        """
        Delete whichever half of the routing fields cannot apply.

        This is the structural half of the Poka-Yoke rule described in the
        class docstring: a revenue form does not validate away a fund source,
        it has no fund source field at all. ``linked_event`` survives on both
        sides but is relabelled, because it means two different things.
        """
        direction = self._direction()
        if direction == 'revenue':
            for name in ('fund_source', 'lnl_spend_category', 'fr_line_target'):
                self.fields.pop(name, None)
        elif direction == 'expense':
            self.fields.pop('non_event_revenue_type', None)
            # linked_event stays: a sub-rental hired for one show is that
            # show's cost, passed straight through. It means something
            # different here than on revenue, so it says so.
            event = self.fields.get('linked_event')
            if event is not None:
                event.label = "Incurred for event"
                event.help_text = ("For costs billed straight through to one show -- a "
                                   "sub-rental, a one-off hire. Leave blank for general "
                                   "club spending.")
        # direction is None (a brand-new encumbrance with no amount yet): keep
        # everything and let clean() arbitrate once an amount is typed.

        # The cross-year opt-in is meaningless without the picker it widens.
        if 'fr_line_target' not in self.fields:
            self.fields.pop('allow_cross_year_fr', None)

    def _apply_partition_default(self):
        """
        Start the Projection tick box from the org code the money left, and say
        what changing it means.

        It used to be disabled outright. That made the common case impossible
        to record: a Projection purchase bought out of the main account on an
        SGA funding request is 226-AG money and Projection spending at the same
        time. So the code sets the starting position and the Treasurer has the
        final say -- with a warning, and on the account SGA funds directly for
        Projection, with a written reason.
        """
        parent = self.parent_transaction
        field = self.fields.get('is_projection')
        if parent is None or field is None:
            return

        match = parent.matched_partition_code
        if match is None:
            return
        if not self.instance.pk:
            field.initial = bool(match['is_projection'])
        side = "Projection" if match['is_projection'] else "Event Production"
        other = "Event Production" if match['is_projection'] else "Projection"
        if match.get('crossing_requires_reason'):
            field.help_text = (
                "Paid out of %s, so it starts as %s spending. Filing it as %s is allowed "
                "but has to be explained in the audit note." % (match['code'], side, other))
        else:
            field.help_text = (
                "Paid out of %s, so it starts as %s spending. Change it if the money was "
                "really for %s -- that is normal when SGA reimburses this account."
                % (match['code'], side, other))

    def clean(self):
        """
        Reconcile the trimmed-down form with the full model.

        The model knows about fields this form may have deleted, so they are
        explicitly nulled on the instance first -- otherwise a form that
        dropped ``fund_source`` would leave a stale value on an edited row and
        model validation would see a revenue entry carrying expense routing.
        """
        cleaned = super(BaseAllocationForm, self).clean()
        # Fields stripped above are absent from cleaned_data; re-assert them as
        # None on the instance so model validation sees a consistent picture.
        for name in (ParsedTransaction.REVENUE_FIELDS + ParsedTransaction.EXPENSE_FIELDS
                     + ParsedTransaction.SHARED_FIELDS):
            if name not in self.fields:
                setattr(self.instance, name, None)
        if self.parent_transaction is not None:
            self.instance.parent_transaction = self.parent_transaction
        # Rendering the tick box means a human saw it and the answer stands,
        # including a deliberate "no". A form without it lets the org code
        # decide, which is what the split modal wants.
        if 'is_projection' in self.fields:
            self.instance.state_partition()
        self._check_fund_and_fr_line(cleaned)
        self._default_event_expense_category(cleaned)
        return cleaned

    def _default_event_expense_category(self, cleaned):
        """
        Fill the spend category for a cost billed straight to an event.

        The linked event already says what the money was for, so making the
        Treasurer also pick a category is a question with no useful answer.
        Which category that is comes from the ``is_event_passthrough`` flag on
        the row, so it is renameable and retirable like any other.

        Only ever fills a blank -- an explicit choice is never overwritten.
        """
        if 'lnl_spend_category' not in self.fields or cleaned.get('lnl_spend_category'):
            return
        if not cleaned.get('linked_event'):
            return
        category = event_passthrough_category()
        if category is None:
            return
        cleaned['lnl_spend_category'] = category
        self.instance.lnl_spend_category = category
        # It was required for expenses, and it is now supplied.
        self.errors.pop('lnl_spend_category', None)

    def _check_fund_and_fr_line(self, cleaned):
        """
        Say plainly, field by field, what the model would otherwise reject.

        The same rules live in ``ParsedTransaction.clean()`` so they hold for
        the shell and for bulk actions; here they are attached to the field the
        Treasurer has to change, and the cross-year rule is added on top.
        """
        if 'fr_line_target' not in self.fields:
            return

        fund = cleaned.get('fund_source')
        line = cleaned.get('fr_line_target')

        if line is None:
            if fund is not None and fund.requires_funding_request:
                self.add_error('fr_line_target',
                               "%s money has to name the funding request line it comes out "
                               "of." % fund)
            return

        if fund is None or not fund.requires_funding_request:
            self.add_error(
                'fr_line_target',
                "Only a fund that draws on a funding request may name an FR line — %s does "
                "not. Change the fund, or clear this." % (fund or "no fund"))
            return

        # Crossing fiscal years is legal, but has to be deliberate.
        entry_year = self._entry_fiscal_year()
        request_year = line.funding_request.fiscal_year
        if request_year != entry_year and not cleaned.get('allow_cross_year_fr'):
            self.add_error(
                'fr_line_target',
                "This is FY%s spending but %s is an FY%s request. If that is genuinely "
                "intended, tick “Charge a different fiscal year”."
                % (entry_year, line.funding_request.name, request_year))

    def _update_errors(self, errors):
        """
        Model validation can key an error to a field this subclass doesn't
        render (e.g. ``amount`` on the queue's routing-only form). Django raises
        ValueError in that case, turning a validation problem into a 500, so
        those get rerouted to non-field errors instead.
        """
        if hasattr(errors, 'error_dict'):
            rehomed = {}
            for field, messages in errors.error_dict.items():
                target = field if (field in self.fields or field == NON_FIELD_ERRORS) \
                    else NON_FIELD_ERRORS
                rehomed.setdefault(target, []).extend(messages)
            errors = ValidationError(rehomed)
        return super(BaseAllocationForm, self)._update_errors(errors)


class AllocationForm(BaseAllocationForm):
    """
    Full-page edit of a single slice (the Entry page).

    This is where an expense gets its final shape: where the money came from
    and what it was for. Both are structural -- reports group by them and a
    blank makes a line uncountable -- so both are required.

    The audit explanation and the receipt are not. They used to be, and that
    made this page unusable for its most common job: fixing a spend category
    that was picked wrong three weeks ago meant first producing a receipt for
    somebody else's purchase, or inventing a sentence about it. A line missing
    its paperwork is a line to chase, not a line to lock -- so the page asks
    for both, says which are missing, and saves either way.
    """
    REQUIRED_ON_EXPENSES = ('fund_source', 'lnl_spend_category')

    def __init__(self, *args, **kwargs):
        """
        Say out loud that the paperwork fields are optional.

        Without the help text a blank box reads as an oversight rather than
        as a choice, and the whole point of this form is that fixing a
        mis-filed category should not require somebody else's receipt.
        """
        super(AllocationForm, self).__init__(*args, **kwargs)
        receipt = self.fields.get('receipt_file')
        if receipt is not None and not receipt.required:
            receipt.help_text = ("Attach one if you have it. Entries without a receipt can "
                                 "still be saved, and show as missing on the entry page.")
        explanation = self.fields.get('audit_explanation')
        if explanation is not None and not explanation.required:
            explanation.help_text = "Optional, but the first thing an auditor asks for."
        self.helper = FormHelper()
        self.helper.form_tag = False
        # base_finance.html emits the autocomplete scripts once for the whole
        # app, so crispy must not emit them again: its copy also carries a
        # jQuery UI 1.13 theme, and the widget here runs on jQuery UI 1.10.
        # Two themes over one widget is what made the dropdown flicker.
        self.helper.include_media = False
        self.helper.label_class = 'col-md-4'
        self.helper.field_class = 'col-md-8'
        self.helper.form_class = 'form-horizontal'


class ReconcileForm(BaseAllocationForm):
    """
    The fast single-line form used in the ingestion queue (Page 3).

    Amount and date are inherited from the bank line, so the Treasurer only
    supplies routing.
    """
    # Every expense leaving the queue must at least say where the money came
    # from. Receipt and explanation are deferred to the Entry page.
    REQUIRED_ON_EXPENSES = ('fund_source',)

    class Meta(BaseAllocationForm.Meta):
        fields = ('linked_event', 'non_event_revenue_type', 'fund_source', 'lnl_spend_category',
                  'fr_line_target', 'project_tag', 'is_projection', 'audit_explanation')

    def __init__(self, *args, **kwargs):
        """ Compact styling: this form is rendered many times down one page. """
        super(ReconcileForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        # base_finance.html emits the autocomplete scripts once for the whole
        # app, so crispy must not emit them again: its copy also carries a
        # jQuery UI 1.13 theme, and the widget here runs on jQuery UI 1.10.
        # Two themes over one widget is what made the dropdown flicker.
        self.helper.include_media = False
        if 'audit_explanation' in self.fields:
            self.fields['audit_explanation'].widget.attrs['rows'] = 2

    def _direction(self):
        """
        Take the direction from the bank line, which cannot be argued with.

        The base class infers it from the typed amount; here there is no
        amount box, and the sign Workday recorded is authoritative.
        """
        if self.parent_transaction is not None:
            return 'revenue' if self.parent_transaction.net_amount > 0 else 'expense'
        return super(ReconcileForm, self)._direction()

    def _inherit_from_parent(self):
        """
        Amount and date are never typed here -- they come from the bank line.
        They have to land on the instance *before* model validation runs, or
        Model.clean() sees a null amount.

        The amount taken is what is *left* on the line, not its full value: a
        line already part-allocated from the split page still appears in the
        queue, and allocating the whole amount again would put more against it
        than the bank ever paid.
        """
        parent = self.parent_transaction
        if parent is None:
            return
        self.instance.parent_transaction = parent
        remaining = parent.unallocated_amount
        self.instance.amount = remaining if remaining else parent.net_amount
        self.instance.effective_date = parent.accounting_date
        if not self.instance.description:
            # The CSV's Journal Line Memo is the closest thing to a human
            # description of the line; fall back to the payee if it is blank.
            self.instance.description = parent.journal_line_memo or parent.description

    def clean(self):
        """ Inherit amount and date before the model gets a look at them. """
        cleaned = super(ReconcileForm, self).clean()
        self._inherit_from_parent()
        return cleaned

    def save(self, commit=True):
        """
        Re-inherit from the parent, then full-clean before writing.

        ``_inherit_from_parent`` runs again rather than being trusted from
        ``clean()``: ``save(commit=False)`` rebuilds the instance from
        ``cleaned_data``, which has no amount or date in it.
        """
        instance = super(ReconcileForm, self).save(commit=False)
        self._inherit_from_parent()
        if commit:
            instance.full_clean()
            instance.save()
        return instance


class EncumbranceForm(BaseAllocationForm):
    """
    A crew member logging a pending purchase to reserve funds before the
    Workday feed catches up. Always saved as Pending with no parent.
    """
    # No receipt yet -- the purchase hasn't happened.
    REQUIRED_ON_EXPENSES = ('fund_source', 'lnl_spend_category')

    amount = forms.DecimalField(
        max_digits=12, decimal_places=2, label="Amount to encumber",
        help_text="Enter the expected cost as a positive number; it is recorded as an expense.")

    class Meta(BaseAllocationForm.Meta):
        fields = ('amount', 'effective_date', 'description', 'fund_source', 'lnl_spend_category',
                  'fr_line_target', 'project_tag', 'is_projection', 'audit_explanation',
                  'receipt_file')

    def __init__(self, *args, **kwargs):
        """
        Insist on a description and a reason.

        There is no bank line to fall back on here -- nothing has happened in
        Workday yet -- so if the person entering it does not say what the
        money is for, nothing else ever will.
        """
        super(EncumbranceForm, self).__init__(*args, **kwargs)
        self.fields['description'].required = True
        self.fields['audit_explanation'].required = True
        self.fields['audit_explanation'].label = "What is this for?"
        self.helper = FormHelper()
        self.helper.form_tag = False
        # base_finance.html emits the autocomplete scripts once for the whole
        # app, so crispy must not emit them again: its copy also carries a
        # jQuery UI 1.13 theme, and the widget here runs on jQuery UI 1.10.
        # Two themes over one widget is what made the dropdown flicker.
        self.helper.include_media = False

    def _direction(self):
        """ Always an expense: you cannot encumber money coming in. """
        return 'expense'

    def clean_amount(self):
        """ Reject zero, and normalise whatever sign was typed to negative. """
        amount = self.cleaned_data['amount']
        if amount == 0:
            raise ValidationError("Enter a non-zero amount.")
        # Encumbrances are always outgoing money; accept either sign from the
        # user and normalise, rather than making them remember the convention.
        return -abs(amount)

    def save(self, commit=True):
        """ Save with no parent and Pending status, whatever the form said. """
        instance = super(EncumbranceForm, self).save(commit=False)
        instance.parent_transaction = None
        instance.status = TransactionStatus.PENDING
        if commit:
            instance.full_clean()
            instance.save()
        return instance


# ---------------------------------------------------------------------------
# Split purchases
# ---------------------------------------------------------------------------

class SplitLineForm(BaseAllocationForm):
    """
    One slice inside the split modal.

    The modal has no date column -- a slice happened when the purchase did --
    so, like :class:`ReconcileForm`, the date is inherited from the bank line
    rather than typed.
    """
    REQUIRED_ON_EXPENSES = ('fund_source',)

    class Meta(BaseAllocationForm.Meta):
        fields = ('amount', 'description', 'fund_source', 'lnl_spend_category',
                  'fr_line_target', 'project_tag', 'linked_event', 'non_event_revenue_type',
                  'audit_explanation')

    def _inherit_effective_date(self):
        """
        Take the date from the bank line being split.

        ``effective_date`` carries a ``default=timezone.localdate``, so a slice
        built by this form is never missing one -- it silently has *today's*.
        Both callers guarded against that with ``if not entry.effective_date``,
        which can therefore never fire, and splitting a September purchase the
        following August filed every slice a whole fiscal year late. Nothing on
        screen said so: the ledger showed the date it had been given.

        The date is not a preference here, it is a property of the purchase, so
        it is taken outright rather than filled in only when blank.
        """
        parent = self.parent_transaction or self.instance.parent_transaction
        if parent is not None:
            self.instance.effective_date = parent.accounting_date

    def clean(self):
        """ Inherit the purchase date before the model gets a look at it. """
        cleaned = super(SplitLineForm, self).clean()
        self._inherit_effective_date()
        return cleaned

    def save(self, commit=True):
        """ Re-inherit the date, then full-clean before writing. """
        instance = super(SplitLineForm, self).save(commit=False)
        self._inherit_effective_date()
        if commit:
            instance.full_clean()
            instance.save()
        return instance

    def __init__(self, *args, **kwargs):
        """ Mark the amount box so the modal's running total can find it. """
        super(SplitLineForm, self).__init__(*args, **kwargs)
        # Appended, not assigned: _style_widgets() has already put
        # form-control here and replacing the attribute would strip it.
        amount = self.fields['amount'].widget
        amount.attrs['step'] = '0.01'
        amount.attrs['class'] = (amount.attrs.get('class', '') + ' split-amount').strip()


class BaseSplitFormSet(BaseInlineFormSet):
    """
    Enforces the split-purchase mandate: the slices must add up to the bank
    line to the cent. This is the formset-level guard behind the disabled
    'Save' button in the UI.
    """
    def __init__(self, *args, **kwargs):
        """ Accept the bank line being split, which every slice needs. """
        self.parent_transaction = kwargs.pop('parent_transaction', None)
        super(BaseSplitFormSet, self).__init__(*args, **kwargs)

    def get_form_kwargs(self, index):
        """ Pass the parent line down to each slice form. """
        kwargs = super(BaseSplitFormSet, self).get_form_kwargs(index)
        kwargs['parent_transaction'] = self.parent_transaction or self.instance
        return kwargs

    def clean(self):
        """
        Require the slices to add up to the bank line, to the cent.

        Returns early when individual forms already have errors: a slice that
        failed its own validation has no amount to add up, and complaining
        about the total on top of that only buries the real problem.
        """
        super(BaseSplitFormSet, self).clean()
        if any(self.errors):
            return

        parent = self.parent_transaction or self.instance
        if parent is None or parent.pk is None:
            return

        total = Decimal('0.00')
        live_forms = 0
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get('DELETE'):
                continue
            amount = form.cleaned_data.get('amount')
            if amount is None:
                continue
            total += amount
            live_forms += 1

        if live_forms == 0:
            raise ValidationError("A transaction needs at least one allocation slice.")

        if total != parent.net_amount:
            remainder = parent.net_amount - total
            raise ValidationError(
                "Allocations total $%s but the bank line is $%s — $%s is still unallocated. "
                "The split must balance to exactly $0.00 before it can be saved."
                % (total, parent.net_amount, remainder))

        # Every slice must share the sign of the parent: you cannot turn half of
        # an expense into revenue by splitting it.
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get('DELETE'):
                continue
            amount = form.cleaned_data.get('amount')
            if amount is not None and amount != 0 and (amount > 0) != (parent.net_amount > 0):
                raise ValidationError(
                    "Every slice must run the same direction as the bank line "
                    "($%s). Split slices cannot flip revenue into expense." % parent.net_amount)


SplitFormSet = inlineformset_factory(
    WorkdayTransaction, ParsedTransaction, form=SplitLineForm, formset=BaseSplitFormSet,
    fk_name='parent_transaction', extra=2, can_delete=True,
)


# ---------------------------------------------------------------------------
# Bulk actions
# ---------------------------------------------------------------------------

class BulkActionForm(forms.Form):
    """ Backs the slide-up bulk action bar on the spreadsheet ledger. """
    ACTIONS = (
        ('project_tag', 'Assign project tag'),
        ('lnl_spend_category', 'Assign spend category'),
        ('fund_source', 'Assign fund source'),
        ('status', 'Set status'),
    )

    action = forms.ChoiceField(choices=ACTIONS)
    # Optional so that submitting with nothing selected reaches the view's
    # "Nothing was selected" message. Required, it fails here instead and the
    # Treasurer is told that a hidden field they have never seen is missing --
    # and the view's own branch for it becomes unreachable.
    selected = forms.CharField(widget=forms.HiddenInput, required=False)
    project_tag = ProjectTagChoiceField()
    lnl_spend_category = forms.ModelChoiceField(
        queryset=SpendCategory.objects.active(), required=False, label="Spend category")
    # Funds that need an FR line are left out on purpose: the line cannot be
    # chosen in bulk, so applying one would leave every row it touched invalid.
    fund_source = forms.ModelChoiceField(
        queryset=FundSource.objects.active().filter(requires_funding_request=False),
        required=False, label="Fund source",
        help_text="Funds that draw on a specific funding request are set one entry at a "
                  "time, so the request line can be named.")
    status = forms.ChoiceField(choices=[('', '---')] + list(TransactionStatus.choices),
                               required=False)

    def __init__(self, *args, **kwargs):
        """ Style the widgets by hand -- see the comment below for why. """
        super(BulkActionForm, self).__init__(*args, **kwargs)
        # The bar these render into is dark and sets ``color: #fff``. A bare
        # <select> inherits that colour while keeping the browser's own white
        # background, so the value picker came out white-on-white -- present,
        # focusable, and completely unreadable. ``form-control`` states both.
        #
        # This is a plain Form, so it gets none of BaseAllocationForm's widget
        # styling; the one <select> that looked right was the one the template
        # writes out by hand.
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.HiddenInput):
                continue
            existing = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = (existing + ' form-control input-sm').strip()

    def clean(self):
        """
        Require a value for whichever action was chosen.

        The bar shows one value field per action and hides the rest, so the
        chosen action's own field is the only one that can be required -- and
        which one that is is not known until the form is submitted.
        """
        cleaned = super(BulkActionForm, self).clean()
        action = cleaned.get('action')
        if action and not cleaned.get(action):
            self.add_error(action, "Pick a value to apply.")
        return cleaned

    @property
    def selected_ids(self):
        """
        The ticked row ids, parsed out of the hidden field.

        Non-numeric fragments are dropped rather than raising: the value is
        assembled by JavaScript, and a malformed one should narrow the
        selection, not 500 the page.
        """
        raw = self.cleaned_data.get('selected', '')
        return [int(pk) for pk in raw.split(',') if pk.strip().isdigit()]


class BulkReconcileForm(forms.Form):
    """
    Reconcile a batch of queue rows that all take the same routing.

    A monthly export arrives with a dozen Amazon supply orders on it, and every
    one of them is Consumables out of the standing budget. Answering the same
    two questions twelve times is the work this page exists to remove, not the
    work it exists to make.

    Deliberately expense-only. "The same settings" for money coming in means
    "the same event", which is a different question with a different picker and
    is rarely true of a batch; revenue rows in a selection are reported and left
    alone rather than being quietly given expense routing that the database
    would refuse anyway.
    """
    # Optional so that submitting with nothing selected reaches the view's
    # "Nothing was selected" message. Required, it fails here instead and the
    # Treasurer is told a hidden field they have never seen is missing.
    selected = forms.CharField(widget=forms.HiddenInput, required=False)

    # Required for the same reason ReconcileForm requires it: an expense that
    # does not say where the money came from is not reconciled, it is filed.
    fund_source = forms.ModelChoiceField(
        # Funds needing an FR line are left out for the reason BulkActionForm
        # leaves them out: the line cannot be chosen in bulk, so every row would
        # come out invalid.
        queryset=FundSource.objects.none(), label="Fund",
        help_text="Funds drawing on a specific funding request are reconciled one line at "
                  "a time, so the request line can be named.")
    lnl_spend_category = forms.ModelChoiceField(
        queryset=SpendCategory.objects.none(), required=False, label="Spend category")
    project_tag = ProjectTagChoiceField()

    def __init__(self, *args, **kwargs):
        """ Resolve the querysets and style the widgets at instantiation. """
        super(BulkReconcileForm, self).__init__(*args, **kwargs)
        # Resolved per instance, not at import time, so retiring a category in
        # the admin takes effect without a restart.
        self.fields['fund_source'].queryset = (
            FundSource.objects.active().filter(requires_funding_request=False))
        self.fields['lnl_spend_category'].queryset = SpendCategory.objects.active()

        fund = self.fields['fund_source']
        fund.widget = FundSourceSelect(attrs={'class': 'fin-fund-source'})
        fund.widget.choices = fund.choices

        # Same reasoning as BulkActionForm: this bar is dark and sets a colour,
        # and a control that inherits it keeps its own light background.
        for field in self.fields.values():
            if isinstance(field.widget, forms.HiddenInput):
                continue
            existing = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = (existing + ' form-control input-sm').strip()

    @property
    def selected_ids(self):
        """ The ticked queue rows, parsed as in :class:`BulkActionForm`. """
        raw = self.cleaned_data.get('selected', '')
        return [int(pk) for pk in raw.split(',') if pk.strip().isdigit()]


class OpenEncumbranceChoiceField(forms.ModelChoiceField):
    """ Open reservations, labelled with what is left rather than what was asked for. """

    def label_from_instance(self, obj):
        """ ``Whole gear order — $296.45 still reserved · Aug 20, 2025``. """
        return "%s — $%s still reserved · %s" % (
            obj.description or "(no description)", abs(obj.amount),
            date_format(obj.effective_date, 'M j, Y'))


class BulkEncumbranceForm(forms.Form):
    """
    Draw one reservation down across a whole selection of queue rows.

    The case this exists for: a single encumbrance is written for a job, and
    Workday then delivers it as ten separate invoice lines. Matching them one
    at a time works -- the reservation survives each draw -- but it is the same
    ten-times-over interaction the bulk bar exists to remove, and the balance to
    keep track of between clicks is the thing most likely to be got wrong.

    No routing fields, unlike :class:`BulkReconcileForm`: the answer to "where
    does this money go" is already written on the reservation, and asking it
    again here would let a bulk action contradict the thing it is drawing from.
    """
    selected = forms.CharField(widget=forms.HiddenInput, required=False)
    encumbrance = OpenEncumbranceChoiceField(
        queryset=ParsedTransaction.objects.none(), required=False,
        label="Encumbrance", empty_label="Draw from encumbrance…")

    def __init__(self, *args, **kwargs):
        """ Resolve the open reservations per instance, newest first. """
        super(BulkEncumbranceForm, self).__init__(*args, **kwargs)
        self.fields['encumbrance'].queryset = (
            ParsedTransaction.objects
            .filter(parent_transaction__isnull=True,
                    status=TransactionStatus.PENDING,
                    amount__lt=0)
            .order_by('-effective_date', '-pk'))
        for field in self.fields.values():
            if isinstance(field.widget, forms.HiddenInput):
                continue
            existing = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = (existing + ' form-control input-sm').strip()

    @property
    def selected_ids(self):
        """ The ticked queue rows, parsed as in :class:`BulkReconcileForm`. """
        raw = self.cleaned_data.get('selected', '')
        return [int(pk) for pk in raw.split(',') if pk.strip().isdigit()]


# ---------------------------------------------------------------------------
# Funding requests
# ---------------------------------------------------------------------------

class FundingRequestForm(forms.ModelForm):
    """ The header half of a funding request; the lines are a formset. """

    class Meta:
        model = FundingRequest
        fields = ('name', 'reference', 'fiscal_year', 'date_submitted', 'date_approved',
                  'is_projection', 'closed', 'notes')
        widgets = {
            'date_submitted': forms.DateInput(attrs={'type': 'date'}),
            'date_approved': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        """
        Replace the plain year box with the same list the filter bar uses.

        Rebuilt per instance because the choices depend on the configured
        fiscal year start month, which is editable from the admin.
        """
        super(FundingRequestForm, self).__init__(*args, **kwargs)
        self.fields['fiscal_year'] = forms.ChoiceField(
            choices=fiscal_year_choices(), initial=current_fiscal_year(), label="Fiscal Year")
        self.helper = FormHelper()
        self.helper.form_tag = False
        # base_finance.html emits the autocomplete scripts once for the whole
        # app, so crispy must not emit them again: its copy also carries a
        # jQuery UI 1.13 theme, and the widget here runs on jQuery UI 1.10.
        # Two themes over one widget is what made the dropdown flicker.
        self.helper.include_media = False


class FRLineItemForm(forms.ModelForm):
    """
    One awarded line inside a funding request.

    Rendered as a row in a formset, so both overrides below are about the
    row being *blank*: ``sort_order`` carries a model default, and a default
    is enough to make Django think an untouched row was filled in.
    """
    project_tag = ProjectTagChoiceField()

    class Meta:
        model = FRLineItem
        fields = ('name', 'description', 'amount_awarded', 'lnl_spend_category',
                  'project_tag', 'sort_order')
        widgets = {
            'description': forms.Textarea(attrs={
                'rows': 2, 'placeholder': 'What this line covers'}),
        }

    def __init__(self, *args, **kwargs):
        """ Stop Django demanding a hand-typed sort order on every row. """
        super(FRLineItemForm, self).__init__(*args, **kwargs)
        # sort_order carries a model default, but Django still renders it as
        # mandatory, which meant no line could be saved without hand-typing a
        # number. The formset fills it in from row position instead.
        self.fields['sort_order'].required = False
        self.fields['sort_order'].label = "Order"
        self.fields['sort_order'].help_text = ""

    def has_changed(self):
        """
        Decide "is this row blank?" on what the user actually typed.

        ``sort_order`` carries a model default of 0, so it counts as changed the
        moment a row is rendered or cloned with an empty box — which made an
        untouched row look filled in and demand a name and an amount.
        """
        return bool(set(self.changed_data) - {'sort_order'})

    def clean(self):
        """ Refuse an award cut below what has already been spent against it. """
        cleaned = super(FRLineItemForm, self).clean()
        # Guard the burndown: you cannot cut an award below what is already spent.
        if self.instance.pk and not cleaned.get('DELETE'):
            awarded = cleaned.get('amount_awarded')
            spent = self.instance.spent
            if awarded is not None and awarded < spent:
                self.add_error('amount_awarded',
                               "$%s is already allocated against this line; the award cannot be "
                               "lowered below that." % spent)
        return cleaned


class BaseFRLineItemFormSet(BaseInlineFormSet):
    """ Numbers the lines by where they sit in the table, unless told otherwise. """

    def clean(self):
        """ Number any line that was left without an explicit order. """
        super(BaseFRLineItemFormSet, self).clean()
        if any(self.errors):
            return
        position = 0
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get('DELETE'):
                continue
            if form.cleaned_data.get('sort_order') in (None, ''):
                form.instance.sort_order = position
            position += 1


# `extra` only sets how many blank rows are rendered up front. The form's
# "Add another line" button raises TOTAL_FORMS at runtime, so a request can
# carry as many lines as it needs.
FRLineItemFormSet = inlineformset_factory(
    FundingRequest, FRLineItem, form=FRLineItemForm, formset=BaseFRLineItemFormSet,
    extra=3, can_delete=True)


# ---------------------------------------------------------------------------
# Project tags
# ---------------------------------------------------------------------------

class ProjectTagForm(forms.ModelForm):
    """ Create or rename one node of the project tag forest. """
    parent = ProjectTagChoiceField(
        queryset=ProjectTag.objects.all(), label="Parent project",
        help_text="Leave blank to create a top-level project")

    class Meta:
        model = ProjectTag
        fields = ('name', 'code', 'parent', 'description', 'is_projection', 'archived')
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, **kwargs):
        """ Keep the tag, and everything under it, out of its own parent list. """
        super(ProjectTagForm, self).__init__(*args, **kwargs)
        qs = ProjectTag.objects.all()
        if self.instance.pk:
            # Prevent making a node its own ancestor.
            qs = qs.exclude(pk__in=self.instance.get_descendants(include_self=True))
        self.fields['parent'].queryset = qs
        self.helper = FormHelper()
        self.helper.form_tag = False
        # base_finance.html emits the autocomplete scripts once for the whole
        # app, so crispy must not emit them again: its copy also carries a
        # jQuery UI 1.13 theme, and the widget here runs on jQuery UI 1.10.
        # Two themes over one widget is what made the dropdown flicker.
        self.helper.include_media = False
