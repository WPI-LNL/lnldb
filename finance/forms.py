"""
Every form the finance pages put in front of a Treasurer.

The organising idea is Poka-Yoke: wherever a rule can be enforced by the
form not *having* a field, it is enforced that way rather than by
validating one. :class:`BaseAllocationForm` removes expense routing from a
revenue form outright, so a revenue entry cannot carry a spend category even
if the client-side JS is bypassed -- which matters, because the database
has a constraint saying the same thing and a stray value would surface as
an IntegrityError rather than a field error.

The custom fields at the top exist for a related reason. A dropdown is a
place to make a quiet mistake, so each one is labelled with whatever makes
the wrong option obviously wrong -- the year a funding request belongs to,
how much of a line is left, which purchase a refund is against.
"""
import datetime
from decimal import Decimal, InvalidOperation

from ajax_select.fields import AutoCompleteSelectField
from crispy_forms.helper import FormHelper
from django import forms
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.db.models import F, Q, Value
from django.forms.models import BaseInlineFormSet, ModelChoiceIterator, inlineformset_factory
from django.utils import timezone
from django.utils.formats import date_format
from mptt.forms import TreeNodeChoiceField

from finance.importers import CSV_EXTENSIONS, XLSX_EXTENSIONS
from finance.models import (ZERO, BalanceCheckpoint, BudgetCategory, DrawsOn, Encumbrance,
                            FRLineItem, FundingKind, FundingRequest, FundSource,
                            FundTransfer, MultiBilling, ParsedTransaction, PartitionCode,
                            ProjectTag, RevenueSource, SpendCategory,
                            TransactionStatus,
                            WorkdayTransaction, check_request_ids, current_fiscal_year, dollars,
                            event_passthrough_category, fiscal_year_bounds,
                            fiscal_year_choices, fiscal_year_for, line_charge_problem, money,
                            own_fund_for_account, refund_window, summed_money)
from finance.suggestions import AWARD, lookups_for_form, suggest_all, suggest_description


def finance_form_helper(**attrs):
    """
    The crispy helper every finance form uses, built in one place.

    Two settings are the same on every one of them, and neither is a preference:

    ``form_tag = False``
        The finance templates write their own ``<form>``. A second one nested
        inside it is invalid markup, and the browser closes the outer form at
        the inner one -- so the submit button ends up outside the form it is
        meant to submit.

    ``include_media = False``
        ``base_finance.html`` emits the autocomplete scripts once for the whole
        app -- see
        :func:`finance.templatetags.finance_extras.autocomplete_media` -- so
        crispy must not emit them again: its copy also carries a jQuery UI 1.13
        theme, and the widget here runs on jQuery UI 1.10. Two themes over one
        widget is what made the dropdown flicker.

    Both were previously copied, comment and all, into six ``__init__``
    methods. That is six places to edit the day ajax_select bumps a jQuery
    version, and five chances to miss one -- and a form that misses it renders
    correctly right up until someone opens the event picker on it.

    Anything else is passed as a keyword and set on the helper, which is how
    the Entry page asks for its horizontal layout without a second copy of the
    shared part.
    """
    helper = FormHelper()
    helper.form_tag = False
    helper.include_media = False
    for name, value in attrs.items():
        setattr(helper, name, value)
    return helper


class ProjectTagChoiceField(TreeNodeChoiceField):
    """
    A project picker whose options are nested by depth, so a sub-project is
    never mistaken for a top-level one::

        New Equipment List 2026
            └ D60 Lustr Fixtures

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
        """
        Attach the line's request and spend category as data attributes.

        The request is how the queue's "Funding request" box narrows this
        picker to one request's lines (routing.js, rule 6), and the kind is
        how the fund narrows it to a budget's lines or a request's (rule 1).
        """
        option = super(FRLineSelect, self).create_option(name, value, *args, **kwargs)
        line = getattr(value, 'instance', None)
        if line is not None:
            option['attrs']['data-request'] = str(line.funding_request_id)
            option['attrs']['data-kind'] = line.funding_request.kind
            if line.lnl_spend_category_id:
                option['attrs']['data-spend-category'] = str(line.lnl_spend_category_id)
        return option


class FRLineChoiceIterator(ModelChoiceIterator):
    """
    Groups the lines under the request each belongs to, one ``<optgroup>`` a
    request, the way the project pickers nest a sub-project under its parent::

        FY26 · F.26.6 A Term Films
            └ Film Rights — $5000.00 left
            └ Concessions — $120.00 left

    Requests come in the order their lines first appear, which
    :func:`open_fr_lines` makes the order the request box beside the picker
    lists them in.

    A budget can have a hundred lines, so its lines are grouped one heading
    a category instead, the way the budget's own page nests them::

        FY27 · Budget · Consumables
            └ 4521 Gaff tape — $120.00 left
    """

    def __iter__(self):
        if self.field.empty_label is not None:
            yield ("", self.field.empty_label)
        groups = {}
        for line in self.queryset:
            request = line.funding_request
            if request.is_budget:
                key = (request.pk, line.category_id)
                heading = "%s · %s" % (request.short_label,
                                       line.category.name if line.category_id else "No category")
            else:
                key, heading = (request.pk, None), request.short_label
            choices = groups.setdefault(key, (heading, []))[1]
            choices.append(self.choice(line))
        for heading, choices in groups.values():
            yield (heading, choices)


class FRLineChoiceField(forms.ModelChoiceField):
    """
    Funding request lines, each indented under its request.

    Labelled with the two things you can silently get wrong: the fiscal year
    the request belongs to, which is on the request's heading, and how much of
    the line is left, which is on the line. See
    :attr:`finance.models.FRLineItem.nested_label`.

    Every form that picks a line pairs this with a :class:`LineRequestChoiceField`
    and fills both in with :func:`offer_fr_lines`.
    """
    widget = FRLineSelect
    iterator = FRLineChoiceIterator

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
        # What routing.js calls the box when the fund draws on budgets.
        self.widget.attrs['data-budget-label'] = "Budget line"

    def label_from_instance(self, obj):
        """ Label the line with what it is for and its remaining balance. """
        return obj.nested_label


class FundingKindSelect(forms.Select):
    """
    Tags each request's ``<option>`` with its kind, so routing.js can offer
    only budgets when the fund draws on budgets, and only funding requests
    when it draws on those.
    """

    def create_option(self, name, value, *args, **kwargs):
        """ Attach ``data-kind``: request or budget. """
        option = super(FundingKindSelect, self).create_option(name, value, *args, **kwargs)
        request = getattr(value, 'instance', None)
        if request is not None:
            option['attrs']['data-kind'] = request.kind
        return option


class LineRequestChoiceField(forms.ModelChoiceField):
    """
    The request a spending line's FR line is picked from.

    Not a column of its own: the line is what is saved, and it already says
    which request it belongs to. This box exists so the request the memo quotes
    is filled in even when the line it names cannot be worked out -- and so the
    line picker beside it can be narrowed to that request's lines. It sits
    beside the line picker on every form that has one, so a line is picked the
    same way everywhere; :func:`offer_fr_lines` keeps its options in step with
    the picker's.
    """

    widget = FundingKindSelect

    def __init__(self, *args, **kwargs):
        """ Start empty; the form narrows this alongside the line picker. """
        kwargs.setdefault('queryset', FundingRequest.objects.none())
        kwargs.setdefault('required', False)
        kwargs.setdefault('label', "Funding request")
        kwargs.setdefault('empty_label', "Any")
        kwargs.setdefault('help_text', "Lists only its lines in the line picker.")
        super(LineRequestChoiceField, self).__init__(*args, **kwargs)
        self.widget.attrs['data-budget-label'] = "Budget"

    def label_from_instance(self, obj):
        """ The year and the number, which are what the memo quotes. """
        return obj.short_label


#: How every funding request picker orders requests. The line pickers order
#: their lines request by request in the same order, so the headings there
#: and the options in the request box come in step.
REQUEST_ORDER = ('fiscal_year', 'reference', 'name', 'pk')


def open_fr_lines(keep=None):
    """
    The lines of every open funding request and budget, request by request.

    Only lines SGA approved money for: one pending SGA approval, or denied
    at $0, has nothing to charge to. A budget's lines come category by
    category, in the budget's own order, with the lines in no category last.
    Which kind the picker shows is the fund's to say (routing.js, rule 1).

    ``keep`` is the key of a line to list whatever has become of it: the one an
    entry is already charged to. A request is closed once SGA pays it, and the
    entries charged to it still have to open and save.

    Spend is annotated because every option says what is left on its line,
    which would otherwise be a query per line per form.
    """
    lines = FRLineItem.objects.filter(funding_request__closed=False).chargeable()
    if keep:
        lines = FRLineItem.objects.filter(Q(pk=keep) | Q(pk__in=lines.values('pk')))
    return (lines
            .select_related('funding_request', 'category')
            .with_spend()
            .order_by(*['funding_request__%s' % key for key in REQUEST_ORDER]
                      + [F('category__sort_order').asc(nulls_last=True), 'category__name',
                         'category__pk', 'sort_order', 'pk']))


def offer_fr_lines(form, lines):
    """
    Offer ``lines`` in a form's line picker, and their requests in the box beside it.

    The request box offers exactly the requests the line picker has lines
    from, so the two can never disagree about what is on offer.
    """
    form.fields['fr_line_target'].queryset = lines
    request = form.fields.get('fr_request')
    if request is not None:
        request.queryset = (FundingRequest.objects
                            .filter(pk__in=lines.values('funding_request'))
                            .order_by(*REQUEST_ORDER))


def fr_request_mismatch(line, chosen):
    """
    Why ``line`` cannot be filed with ``chosen`` in the request box, or ``None``.

    The request box only narrows the line picker, and routing.js keeps the two
    in step; a line from another request means one of them was changed without
    the other, and only the Treasurer knows which.
    """
    if chosen is None or line.funding_request_id == chosen.pk:
        return None
    request = line.funding_request.reference or line.funding_request.name
    named = chosen.reference or chosen.name
    return ("The %s line belongs to %s, not to %s chosen beside it. Pick a line of %s, "
            "or change the %s." % (line.label, request, named, named,
                                   "budget" if chosen.is_budget else "request"))


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


class FundingRequestChoiceField(forms.ModelChoiceField):
    """
    The request an SGA payment is for, labelled with what SGA still owes on it.

    Every request is offered, open or closed, because a reimbursement routinely
    arrives after a request is closed for spending. See
    :attr:`finance.models.FundingRequest.picker_label`. Budgets are offered
    too, for SGA's deposit and money returned to SGA; routing.js shows
    whichever kind the fund draws on.
    """
    widget = FundingKindSelect

    def __init__(self, *args, **kwargs):
        """ Start empty; the form fills the queryset in. """
        kwargs.setdefault('queryset', FundingRequest.objects.none())
        kwargs.setdefault('required', False)
        kwargs.setdefault('label', "SGA funding request")
        super(FundingRequestChoiceField, self).__init__(*args, **kwargs)
        self.widget.attrs.setdefault('data-budget-label', "SGA budget")

    def label_from_instance(self, obj):
        """ Label the request with its year and what SGA owes on it. """
        return obj.picker_label


class MultiBillChoiceField(forms.ModelChoiceField):
    """
    The multi-bill a payment is for, labelled with its name, when it was sent
    and what it came to: the three things a Treasurer matches a payment by.
    """

    def __init__(self, *args, **kwargs):
        """ Start empty; the form fills the queryset in. """
        kwargs.setdefault('queryset', MultiBilling.objects.none())
        kwargs.setdefault('required', False)
        kwargs.setdefault('label', "Linked multi-bill")
        super(MultiBillChoiceField, self).__init__(*args, **kwargs)

    def label_from_instance(self, obj):
        """ "Fall films · Oct 3, 2026 · $1,200.00", and "paid" once it is. """
        label = "%s · %s · %s" % (obj.display_name, date_format(obj.date_billed, 'M j, Y'),
                                  dollars(obj.amount))
        return label + " · paid" if obj.date_paid else label


class RevenueSourceSelect(forms.Select):
    """
    Carries the fund each kind of income goes into onto its ``<option>``.

    Picking "SGA Budget" has exactly one right answer for the fund, and
    routing.js fills it in from here -- the same way an FR line fills in its
    spend category.
    """

    def create_option(self, name, value, *args, **kwargs):
        """ Attach the fund this source pays into. """
        option = super(RevenueSourceSelect, self).create_option(name, value, *args, **kwargs)
        source = getattr(value, 'instance', None)
        if source is not None and source.credits_fund_id:
            option['attrs']['data-credits-fund'] = str(source.credits_fund_id)
        return option


class FundSourceSelect(forms.Select):
    """
    Tags each option with whether that fund needs a funding request line, so
    the browser can show or hide the FR picker without a round trip. The
    server re-checks regardless; this only saves the Treasurer from being
    offered a field that cannot legally be filled in.
    """

    def create_option(self, name, value, *args, **kwargs):
        """
        Flag the funds that need a line, and say whose: ``data-draws-on`` is
        ``request`` or ``budget``, which routing.js matches against each line's
        ``data-kind``.
        """
        option = super(FundSourceSelect, self).create_option(name, value, *args, **kwargs)
        fund = getattr(value, 'instance', None)
        if fund is not None and getattr(fund, 'draws_on', ''):
            option['attrs']['data-requires-fr'] = '1'
            option['attrs']['data-draws-on'] = fund.draws_on
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
# Uploading a Workday export (CSV or .xlsx)
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
        self.helper = finance_form_helper()

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
    entirely, so a revenue form is structurally incapable of submitting a spend
    category even if the client-side JS is bypassed.

    The fields in ``ParsedTransaction.SHARED_FIELDS`` are the exceptions, and
    appear on both: ``linked_event`` (revenue earned by an event, costs
    incurred for one), ``fund_source`` (money leaving a fund, money arriving in
    one) and ``funding_request`` (SGA's reimbursement in, money SGA takes back
    out).
    """
    linked_event = AutoCompleteSelectField('Events', required=False, label="Linked event",
                                           help_text="Search by event name or client")
    project_tag = ProjectTagChoiceField()
    # Not saved -- the line says which request it is on. It narrows the line
    # picker to that request's lines, and in the queue it is filled in from the
    # memo's request number even when the line cannot be. See
    # LineRequestChoiceField.
    fr_request = LineRequestChoiceField()
    fr_line_target = FRLineChoiceField()

    # Ticking this widens the FR picker to other years. It is not a model
    # field: charging across fiscal years is legal, it just has to be meant.
    allow_cross_year_fr = forms.BooleanField(
        required=False, label="Charge a different fiscal year",
        help_text="Only tick this if the spending really belongs to another year's request.")

    # Required on every expense-side form. Left off revenue forms entirely,
    # because a DB constraint forbids revenue from carrying expense routing.
    REQUIRED_ON_EXPENSES = ()
    # Required when the row is money coming in. Only the fund can be: it is
    # the one routing field both directions share that every line must name.
    REQUIRED_ON_REVENUE = ()

    class Meta:
        model = ParsedTransaction
        fields = ('amount', 'effective_date', 'description', 'linked_event', 'linked_multibill',
                  'non_event_revenue_type', 'fund_source', 'lnl_spend_category',
                  'fr_line_target', 'funding_request', 'project_tag', 'is_projection',
                  'refund_of', 'audit_explanation', 'receipt_file')
        widgets = {
            'effective_date': forms.DateInput(attrs={'type': 'date'}),
            'audit_explanation': forms.Textarea(attrs={'rows': 3}),
            'description': forms.TextInput(attrs={'placeholder': 'Short label for the ledger'}),
        }
        # Through ``field_classes`` rather than declared on the class, because a
        # declared field is added to every subclass whatever its ``Meta.fields``
        # says -- and two of the subclasses here leave these out on purpose.
        # An encumbrance has no money to give back and cannot be SGA's payment,
        # so EncumbranceForm has neither; the split modal has no refund column,
        # so SplitLineForm has no ``refund_of``.
        field_classes = {'refund_of': RefundTargetChoiceField,
                         'funding_request': FundingRequestChoiceField,
                         'linked_multibill': MultiBillChoiceField}

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
        # So does an archived project.
        self._narrow('lnl_spend_category',
                     self._live_or_saved('lnl_spend_category', SpendCategory.objects.active()))
        self._narrow('fund_source', self._live_or_saved('fund_source', FundSource.objects.active()))
        self._narrow('non_event_revenue_type',
                     self._live_or_saved('non_event_revenue_type', RevenueSource.objects.active())
                     .select_related('credits_fund'))
        self._narrow('project_tag',
                     self._live_or_saved('project_tag', ProjectTag.objects.filter(archived=False)))
        # Every request, closed ones included, newest first: SGA pays for a
        # request after the spending, often once it is closed. Budgets too,
        # for SGA's deposit and money returned to SGA.
        self._narrow('funding_request', FundingRequest.objects.with_totals()
                     .order_by('-fiscal_year', 'kind', 'reference', 'name'))
        # Paid ones too: the payment that pays a bill is often settled after
        # the bill was marked paid by hand.
        self._narrow('linked_multibill', MultiBilling.objects.select_related('org')
                     .prefetch_related('events').order_by('-date_billed', '-pk'))

        fund = self.fields.get('fund_source')
        if fund is not None:
            fund.widget = FundSourceSelect(attrs={'class': 'fin-fund-source'})
            fund.widget.choices = fund.choices
        source = self.fields.get('non_event_revenue_type')
        if source is not None:
            source.widget = RevenueSourceSelect()
            source.widget.choices = source.choices

        self._style_widgets()
        self._narrow_fr_lines()
        self._apply_direction_rules()
        self._seat_fr_pickers()
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
        Offer the lines of this year's open funding requests.

        Charging an FY25 transaction to an FY26 request is legitimate now and
        then -- an invoice lands late, an award is carried over -- but it is far
        more often a mistake, and one that quietly corrupts two years' burndown
        at once. So the other years are behind a tick box rather than sitting in
        the same dropdown one scroll away.
        """
        field = self.fields.get('fr_line_target')
        if field is None:
            return
        offer_fr_lines(self, self._offer_lines(field))

        # A saved line names its request, so the request box starts on it and
        # the line picker opens on that request's lines -- the way a queue row
        # opens on the request its memo quotes.
        current = self.instance.fr_line_target if self.instance.pk else None
        if current is not None and 'fr_request' in self.fields:
            self.initial.setdefault('fr_request', current.funding_request_id)

    def _offer_lines(self, field):
        """ The lines the FR line picker offers; see :meth:`_narrow_fr_lines`. """
        lines = open_fr_lines(keep=self.instance.fr_line_target_id if self.instance.pk else None)
        fiscal_year = self._entry_fiscal_year()

        # A submitted form keeps the full list so that picking another year
        # fails in clean() with an explanation, rather than as a bare "select a
        # valid choice". The narrowing below is about what gets *offered*.
        if self.is_bound or self._cross_year_requested():
            field.help_text = ("Every open funding request is listed — check the year on the "
                               "request you pick from.")
            return lines

        same_year = lines.filter(funding_request__fiscal_year=fiscal_year)
        # Whatever is already saved stays selectable, or editing an entry that
        # was deliberately charged across years would silently drop its line.
        current = self.instance.fr_line_target_id if self.instance.pk else None
        if current and not same_year.filter(pk=current).exists():
            self.initial.setdefault('allow_cross_year_fr', True)
            field.help_text = "This entry is deliberately charged to another fiscal year."
            return lines.filter(Q(funding_request__fiscal_year=fiscal_year) | Q(pk=current))
        field.help_text = ("FY%s requests. Tick the box below to use another year."
                           % str(fiscal_year)[-2:])
        return same_year

    def _seat_fr_pickers(self):
        """
        Put the request box, the line picker and the cross-year tick box together.

        Two of the three are not model fields, and a ModelForm puts declared
        extras after every model field -- so on a page crispy renders whole,
        the box that narrows the line picker and the one that widens it came
        out at the bottom of the form, under the receipt. The queue and the
        split modal place each field by hand, and are unaffected.
        """
        if 'fr_line_target' not in self.fields:
            return
        group = [name for name in ('fr_request', 'fr_line_target', 'allow_cross_year_fr')
                 if name in self.fields]
        order = []
        for name in self.fields:
            if name == 'fr_line_target':
                order.extend(group)
            elif name not in group:
                order.append(name)
        self.order_fields(order)

    def _refundable_queryset(self):
        """
        Expenses this could be a refund of.

        Restricted to this fiscal year and the one before (:func:`refund_window`):
        a credit note lands within weeks of the purchase, so an older match is
        nearly always the wrong row picked out of a long list, but a few weeks
        can cross June 30.

        Three kinds of row are left out because choosing them could only ever
        fail validation, and an option that cannot be picked is worse than no
        option -- it reads as a bug in the ledger rather than a rule:

        * encumbrances, where no money has left the account to come back;
        * this entry itself, which cannot be its own refund;
        * anything already credited back in full, by refunds other than this
          one. The purchase this entry already refunds is always offered, even
          when this refund is what credited it in full, or saving the entry
          again would lose it.

        ``parent_transaction`` is selected because every label reads the
        payee off it, and a dropdown of forty purchases is otherwise forty
        queries.
        """
        start, end = refund_window(self._entry_fiscal_year())
        qs = (ParsedTransaction.objects
              .filter(amount__lt=0, parent_transaction__isnull=False)
              .annotate(_credited=summed_money('refunds__amount'))
              .filter(Q(effective_date__range=(start, end), _credited__lt=F('amount') * Value(-1))
                      | Q(pk=self.instance.refund_of_id))
              .select_related('parent_transaction')
              .order_by('-effective_date', '-pk'))
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        return qs

    def _apply_required_fields(self):
        """
        Mark this direction's mandatory fields, if this form renders them.

        Money SGA takes back is the one expense that needs no spend category:
        nothing was bought, and filing it under one would put SGA's correction
        on the spending chart.
        """
        direction = self._direction()
        if direction is None:
            return
        names = self.REQUIRED_ON_REVENUE if direction == 'revenue' else self.REQUIRED_ON_EXPENSES
        if direction == 'expense' and self._sga_return_selected():
            names = tuple(name for name in names if name != 'lnl_spend_category')
        for name in names:
            field = self.fields.get(name)
            if field is not None:
                field.required = True

    def _sga_return_selected(self):
        """
        Whether this expense names the request SGA took money back for.

        Read from the raw data, like :meth:`_refund_selected`, because it
        decides which fields are required before validation runs.
        """
        if 'funding_request' not in self.fields:
            return False
        if self.data:
            return bool(self.data.get(self.add_prefix('funding_request')))
        return bool(self.instance.funding_request_id or self.initial.get('funding_request'))

    # -- filling in from the export -----------------------------------------
    def suggestions(self):
        """ The routing this bank line implies, worked out once per form. """
        if self._suggestions is None and self.parent_transaction is not None:
            self._suggestions = suggest_all(self.parent_transaction)
        return self._suggestions or {}

    def _prefill_from_workday(self):
        """
        Select every answer the line already carries, so reconciling is reading.

        What lands here is whatever :mod:`finance.suggestions` did not have to
        guess at: the spend category a funding request line was awarded for,
        the routing LNL wrote into the Workday memo, an LNL category mapped to
        a Workday account, and the fund a Treasurer nominated as the fallback. Each arrives with a note saying
        which of those it was, which the queue prints under the box -- a filled
        box is allowed, a filled box that overstates where it came from is not.

        A guess -- a word noticed in some prose, a resemblance between two
        purchases -- stays a chip to click and fills in nothing, because a
        pre-selected dropdown gets accepted without being read.

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
            self._mark_inherited(field, suggestion, name)

    @staticmethod
    def _mark_inherited(field, suggestion, name=None):
        """
        Tell routing.js which pre-filled boxes may give way to a chosen line.

        Rule 2 in ``static/js/routing.js`` fills the spend category and project
        in from whichever FR line is chosen, and it will only ever overwrite a
        box it filled in itself -- a value the Treasurer picked by hand survives
        switching lines. A box *this* method filled in belongs in the first
        group, not the second: nobody chose it by hand. Saying so is one data
        attribute, which is what jQuery's ``.data('fin-inherited')`` reads.

        The spend category is marked whatever answered it. One that came off
        the award is the same answer from the same place and has to follow the
        line; one read off Workday's category is weaker than the award of the
        line the Treasurer then picks, and must give way to it -- otherwise a
        wrong guess from the export outlives the line that corrects it. The
        project is never filled in here, so a line's project always lands.

        A filled-in fund is marked whatever answered it, for rule 5: choosing
        the kind of income decides the fund, and a fund nobody chose by hand
        must give way to that rather than be refused on save.
        """
        if (suggestion.source != AWARD
                and name not in ('fund_source', 'lnl_spend_category')):
            return
        widget = getattr(field, 'widget', None)
        if widget is not None:
            widget.attrs['data-fin-inherited'] = str(suggestion.value)

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
        Pre-fill Description from the memo, minus the routing written into it.

        LNL writes its memos as ``{description}, {FR line}, {FR code}``, so the
        whole memo is the wrong thing to copy here: the two fields after the
        comma are about to be recorded in columns of their own, and repeating
        them in prose is how a description column stops being read. See
        :func:`finance.suggestions.parse_memo`.

        Only for a brand-new slice, so it never overwrites what the Treasurer
        already typed.
        """
        field = self.fields.get('description')
        if field is None or self.instance.pk or self.parent_transaction is None:
            return
        if not self.initial.get('description'):
            self.initial['description'] = suggest_description(self.parent_transaction)

    def _live_or_saved(self, name, live):
        """
        ``live``, plus whatever this entry already holds in ``name``.

        A choice that isn't on offer posts back blank, or is refused. So
        without this, fixing a typo on an entry whose project was since
        archived would quietly clear the project.
        """
        saved = getattr(self.instance, '%s_id' % name, None) if self.instance.pk else None
        if saved is None:
            return live
        return live.model.objects.filter(Q(pk=saved) | Q(pk__in=live.values('pk')))

    def _narrow(self, name, queryset):
        """ Restrict a choice field's queryset if this subclass renders it. """
        field = self.fields.get(name)
        if field is not None:
            field.queryset = queryset

    # -- direction ----------------------------------------------------------
    def _refund_selected(self):
        """
        Whether this row is being filed as a credit against an earlier purchase.

        Read from the raw data rather than ``cleaned_data`` because the answer
        is needed in ``__init__``, long before validation: it decides which
        fields the form even has. Subclasses that fix the direction from the
        bank line still have to consult it, so it lives here rather than inline
        in :meth:`_direction`.
        """
        return bool(self.data.get(self.add_prefix('refund_of'))
                    or self.instance.refund_of_id)

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

        if amount > 0 and not self._refund_selected():
            return 'revenue'
        return 'expense'

    def _apply_direction_rules(self):
        """
        Delete whichever half of the routing fields cannot apply.

        This is the structural half of the Poka-Yoke rule described in the
        class docstring: a revenue form does not validate away a spend
        category, it has no spend category field at all. The shared fields --
        ``linked_event``, ``fund_source`` and ``funding_request`` -- survive on
        both sides, and each is relabelled on the side where it means something
        different.
        """
        direction = self._direction()
        request = self.fields.get('funding_request')
        if direction == 'revenue':
            for name in ParsedTransaction.EXPENSE_FIELDS:
                self.fields.pop(name, None)
            fund = self.fields.get('fund_source')
            if fund is not None:
                fund.label = "Into fund"
                fund.help_text = self._revenue_fund_help()
            multibill = self.fields.get('linked_multibill')
            if multibill is not None:
                multibill.help_text = ("For one payment covering a multi-bill, in place of an event. "
                                       "Each event on the bill is credited with its share, by price.")
            if request is not None:
                request.label = "Reimburses request"
                request.help_text = ("The funding request SGA is paying back, or the budget SGA "
                                     "is depositing. Needed whenever the money goes into a fund "
                                     "that draws on requests or budgets.")
                request.widget.attrs['data-budget-label'] = "Deposit for budget"
        elif direction == 'expense':
            for name in ParsedTransaction.REVENUE_FIELDS:
                self.fields.pop(name, None)
            if request is not None:
                request.label = "SGA took back money for"
                request.help_text = ("Only when SGA is reclaiming money it paid -- a "
                                     "reimbursement made twice, or a budget's unspent money "
                                     "at year end. Ordinary spending names a line instead.")
                request.widget.attrs['data-budget-label'] = "Returned to SGA from budget"
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

        # The cross-year opt-in and the request box are meaningless without the
        # picker they widen and narrow.
        if 'fr_line_target' not in self.fields:
            self.fields.pop('allow_cross_year_fr', None)
            self.fields.pop('fr_request', None)

    def _revenue_fund_help(self):
        """
        What choosing a fund for money coming in means, for this line's account.

        Two answers cover nearly every line, and the help says which is which:
        an SGA reimbursement repays a funding request, and everything else --
        event billing above all -- is the account's own money.
        """
        own = own_fund_for_account(getattr(self.parent_transaction, 'partition_code_label', ''))
        tail = (" Everything else on %s is %s." % (self.parent_transaction.partition_code_label, own)
                if own is not None else "")
        return ("The pot this money adds to. An SGA reimbursement goes to the fund that "
                "spent it, which brings that fund back towards zero." + tail)

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
                "Paid out of %s, so it starts as %s spending. Counting it as %s is allowed "
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
        dropped ``lnl_spend_category`` would leave a stale value on an edited
        row and model validation would see a revenue entry carrying expense
        routing. The flip side: a subclass that leaves a routing field out of
        ``Meta.fields`` clears it on every save, so a field an entry must keep
        has to be rendered.
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
        self._default_fund_from_source(cleaned)
        self._check_fund_and_fr_line(cleaned)
        self._default_event_expense_category(cleaned)
        return cleaned

    def _default_fund_from_source(self, cleaned):
        """
        Fill the fund in from the kind of income, when that decides it.

        SGA pays each of its three kinds of money into its own fund, so the
        source and the fund are one answer given twice. routing.js fills the
        box in the browser; this covers a form posted without it. Only a blank
        is filled -- a fund that disagrees is the model's to refuse, by name.
        """
        if 'fund_source' not in self.fields or cleaned.get('fund_source'):
            return
        source = cleaned.get('non_event_revenue_type')
        if source is None or source.credits_fund_id is None:
            return
        cleaned['fund_source'] = source.credits_fund
        self.instance.fund_source = source.credits_fund
        self.errors.pop('fund_source', None)

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

        # Money SGA took back names the request or budget instead of a line.
        problem = line_charge_problem(fund, line,
                                      paying_back=bool(cleaned.get('funding_request')))
        if problem:
            self.add_error('fr_line_target', problem)
            return
        if line is None:
            return

        mismatch = fr_request_mismatch(line, cleaned.get('fr_request'))
        if mismatch:
            self.add_error('fr_line_target', mismatch)
            return

        # Crossing fiscal years is legal, but has to be deliberate.
        entry_year = self._entry_fiscal_year()
        request_year = line.funding_request.fiscal_year
        if request_year != entry_year and not cleaned.get('allow_cross_year_fr'):
            self.add_error(
                'fr_line_target',
                "This is FY%s spending but %s is an FY%s %s. If that is genuinely "
                "intended, tick “Charge a different fiscal year”."
                % (str(entry_year)[-2:], line.funding_request.name, str(request_year)[-2:],
                   "budget" if line.funding_request.is_budget else "request"))

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
    REQUIRED_ON_REVENUE = ('fund_source',)

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
        self.helper = finance_form_helper(
            label_class='col-md-4', field_class='col-md-8', form_class='form-horizontal')

    def _apply_direction_rules(self):
        """
        Take the routing boxes off a refund, as the queue does.

        A refund is charged wherever its purchase is, and the model copies that
        on every save, so a box here could only be changed and then put back.
        The page shows the purchase's routing instead. Read from what was
        submitted, so clearing the purchase brings the boxes back to file the
        money as something else.
        """
        super(AllocationForm, self)._apply_direction_rules()
        if self.is_bound:
            refund = self.data.get(self.add_prefix('refund_of'))
        else:
            refund = self.instance.refund_of_id or self.initial.get('refund_of')
        if refund:
            for name in ParsedTransaction.REFUND_INHERITED + ('allow_cross_year_fr', 'fr_request'):
                self.fields.pop(name, None)


class ReconcileForm(BaseAllocationForm):
    """
    The fast single-line form used in the ingestion queue (Page 3).

    Amount and date are inherited from the bank line, so the Treasurer only
    supplies routing.
    """
    # Every line leaving the queue must at least say which fund the money came
    # out of or went into. Receipt and explanation are deferred to the Entry
    # page. A refund names none of its own: it inherits the purchase's.
    REQUIRED_ON_EXPENSES = ('fund_source',)
    REQUIRED_ON_REVENUE = ('fund_source',)

    #: Routing a credit takes from the purchase it reverses, rather than asking
    #: for it again. There is exactly one right answer for every one of these
    #: and the original entry already holds it, so the queue fills them in and
    #: shows no boxes at all. See ``ParsedTransaction.REFUND_INHERITED``.
    REFUND_INHERITED = ParsedTransaction.REFUND_INHERITED

    class Meta(BaseAllocationForm.Meta):
        fields = ('refund_of', 'linked_event', 'linked_multibill', 'non_event_revenue_type',
                  'fund_source', 'funding_request', 'lnl_spend_category', 'fr_line_target', 'project_tag',
                  'is_projection', 'audit_explanation')

    def __init__(self, *args, **kwargs):
        """ Compact styling: this form is rendered many times down one page. """
        super(ReconcileForm, self).__init__(*args, **kwargs)
        self.helper = finance_form_helper()
        if 'audit_explanation' in self.fields:
            self.fields['audit_explanation'].widget.attrs['rows'] = 2

    def _refundable_queryset(self):
        """
        Nothing to offer against a debit line.

        A refund is money coming back, so the picker means something only on a
        positive line. :meth:`_apply_direction_rules` drops the field from a
        debit row outright, which is what actually keeps the query from ever
        running -- a queryset is lazy, and an unrendered field never evaluates
        one. This is a second guard behind that one: should the field ever
        survive onto a debit row, it offers nothing rather than offering
        purchases that could only fail validation on the way back.
        """
        if self.parent_transaction is not None and self.parent_transaction.net_amount <= 0:
            return ParsedTransaction.objects.none()
        return super(ReconcileForm, self)._refundable_queryset()

    def _direction(self):
        """
        Take the direction from the bank line, which cannot be argued with.

        The base class infers it from the typed amount; here there is no
        amount box, and the sign Workday recorded is authoritative.

        The one thing that *can* argue with it is the Treasurer naming the
        purchase this credit reverses. A refund is money arriving that belongs
        on the expense side -- it has to land on the fund and the funding
        request line it is giving back to -- so a positive line with a refund
        target is an expense, exactly as the base class has it.
        """
        if self.parent_transaction is not None:
            positive = self.parent_transaction.net_amount > 0
            return 'revenue' if positive and not self._refund_selected() else 'expense'
        return super(ReconcileForm, self)._direction()

    def _apply_direction_rules(self):
        """
        Strip the queue row down to the one question each kind of line asks.

        Two subtractions on top of the base rules, both of which exist so that
        no row ever renders a box it cannot honour:

        * A **debit** line loses the refund picker. Money going out is not a
          credit against anything, and the database says so -- a refund must be
          positive -- so offering the field could only ever produce an error.

        * A **refund** loses the expense routing. Those fields are not blank
          for it to fill; they are already answered by the purchase being
          reversed, and :meth:`_inherit_refund_routing` copies them across.
          Leaving them on screen would ask the Treasurer to retype an answer
          the ledger holds, and let them get it wrong -- and because
          ``fund_source`` is required on the expense side, a refund chosen from
          a row that renders as revenue would otherwise bounce with an error
          against a box that was never on screen to fill in.
        """
        super(ReconcileForm, self)._apply_direction_rules()

        if self.parent_transaction is not None and self.parent_transaction.net_amount <= 0:
            self.fields.pop('refund_of', None)
        elif self._refund_selected():
            for name in self.REFUND_INHERITED + ('allow_cross_year_fr', 'fr_request'):
                self.fields.pop(name, None)

    def _inherit_refund_routing(self, original):
        """
        Point the credit at everything the original purchase was charged to.

        Runs after :meth:`BaseAllocationForm.clean`, which nulls every routing
        field the form does not render -- which, on a refund, is all of them.
        Filling them in first would be undone.
        """
        if original is None:
            return
        for name in self.REFUND_INHERITED:
            setattr(self.instance, name, getattr(original, name))

    def _inherit_from_parent(self):
        """
        Amount and date are never typed here -- they come from the bank line.
        They have to land on the instance *before* model validation runs, or
        Model.clean() sees a null amount.

        The amount taken is what is *left* on the line, not its full value: a
        line already part-allocated from the split page still appears in the
        queue, and allocating the whole amount again would put more against it
        than the bank ever paid. A line with nothing left is refused rather
        than filed again: it used to fall back to the whole amount, so a line
        already split to the cent took a second copy of itself.
        """
        parent = self.parent_transaction
        if parent is None:
            return
        self.instance.parent_transaction = parent
        remaining = parent.unallocated_amount
        if not remaining:
            raise ValidationError(
                "%s already has entries for its whole amount, so there is nothing left to settle. "
                "Open the line to change how it is split." % parent.reference)
        self.instance.amount = remaining
        self.instance.effective_date = parent.accounting_date
        if not self.instance.description:
            # The memo's first field: what the line was for, without the FR
            # line and request number that follow it in LNL's house format and
            # are about to be recorded as routing. Falls back to the payee.
            self.instance.description = suggest_description(parent) or parent.description

    def clean(self):
        """
        Inherit amount, date and refund routing before the model looks.

        The refund target is read out of ``cleaned_data`` rather than off the
        instance: ``ModelForm`` only writes the form's values onto the instance
        in ``_post_clean``, which has not run yet.
        """
        cleaned = super(ReconcileForm, self).clean()
        self._inherit_from_parent()
        self._inherit_refund_routing((cleaned or {}).get('refund_of'))
        return cleaned

    def save(self, commit=True):
        """
        Re-inherit from the parent, then full-clean before writing.

        ``_inherit_from_parent`` runs again rather than being trusted from
        ``clean()``: ``save(commit=False)`` rebuilds the instance from
        ``cleaned_data``, which has no amount or date in it -- and rebuilding
        it drops the routing copied off the refund target too, so that is
        redone here for the same reason.
        """
        instance = super(ReconcileForm, self).save(commit=False)
        self._inherit_from_parent()
        self._inherit_refund_routing(instance.refund_of if instance.refund_of_id else None)
        if commit:
            instance.full_clean()
            instance.save()
        return instance


class EncumbranceForm(forms.ModelForm):
    """
    What an encumbrance's lines share: what the purchase is and the quote. The
    money itself is on the lines -- see :class:`EncumbranceLineFormSet`.

    One description is all it asks for. There used to be a second required
    box, "What is this for?", which on nearly every encumbrance was the
    description typed again.
    """

    class Meta:
        model = Encumbrance
        fields = ('description', 'receipt_file')
        widgets = {
            'description': forms.TextInput(attrs={'placeholder': 'e.g. Spring gear order'}),
        }

    def __init__(self, *args, **kwargs):
        super(EncumbranceForm, self).__init__(*args, **kwargs)
        self.helper = finance_form_helper()


class EncumbranceLineForm(BaseAllocationForm):
    """
    One line of an encumbrance: an amount, and where it is charged.

    Always an expense, always Pending, and never on a bank line. The date is the
    day the encumbrance was logged, as a split's entries take the bank line's. A
    line left without a description of its own takes the encumbrance's, so the ledger
    never shows a blank; and the box starts empty again on the edit page when
    the line only ever had that, so renaming the encumbrance renames it too.
    """
    # The receipt is not asked for: the purchase has not happened yet, and the
    # quote, if there is one, is the encumbrance's.
    REQUIRED_ON_EXPENSES = ('fund_source', 'lnl_spend_category')

    amount = forms.DecimalField(max_digits=12, decimal_places=2, label="Amount")

    class Meta(BaseAllocationForm.Meta):
        # linked_event has to be listed here, not merely declared on the base
        # class: a ModelForm only saves the fields in Meta.fields. A sub-rental
        # is usually booked before its invoice exists, so encumbering it is
        # exactly when somebody knows which show it is for.
        fields = ('amount', 'description', 'fund_source', 'lnl_spend_category',
                  'fr_line_target', 'project_tag', 'linked_event', 'is_projection')
        widgets = dict(BaseAllocationForm.Meta.widgets, description=forms.TextInput(
            attrs={'placeholder': 'Same as the encumbrance'}))

    def __init__(self, *args, **kwargs):
        self.encumbrance_date = kwargs.pop('encumbrance_date', None)
        self.encumbrance_description = kwargs.pop('encumbrance_description', '')
        super(EncumbranceLineForm, self).__init__(*args, **kwargs)
        # Shown unsigned, as it is typed: see clean_amount().
        if self.instance.pk and not self.is_bound:
            self.initial['amount'] = abs(self.instance.amount)
            if self.instance.description == self.encumbrance_description:
                self.initial['description'] = ''
        amount = self.fields['amount'].widget
        amount.attrs['step'] = '0.01'
        amount.attrs['class'] = (amount.attrs.get('class', '') + ' fin-line-amount').strip()

    def _entry_fiscal_year(self):
        """ The encumbrance's year: a new line has no date of its own yet. """
        if self.encumbrance_date:
            return fiscal_year_for(self.encumbrance_date)
        return super(EncumbranceLineForm, self)._entry_fiscal_year()

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

    def clean(self):
        """ Take the day the encumbrance was logged, and its description when the line has none. """
        cleaned = super(EncumbranceLineForm, self).clean()
        if self.encumbrance_date:
            self.instance.effective_date = self.encumbrance_date
        if not (cleaned.get('description') or '').strip():
            cleaned['description'] = self.encumbrance_description
            self.instance.description = self.encumbrance_description
        self.instance.parent_transaction = None
        self.instance.status = TransactionStatus.PENDING
        return cleaned


class BaseEncumbranceLineFormSet(BaseInlineFormSet):
    """
    The lines of one encumbrance that are still open.

    A line already matched to its Workday charge is an ordinary entry now, and
    is changed from its own page; offering it here would let one form undo a
    match by editing the amount.
    """

    def __init__(self, *args, **kwargs):
        self.encumbrance_date = kwargs.pop('encumbrance_date', None)
        self.encumbrance_description = kwargs.pop('encumbrance_description', '')
        super(BaseEncumbranceLineFormSet, self).__init__(*args, **kwargs)
        # One empty line to fill in on a new encumbrance; none under the lines
        # an existing one already has. "Add a line" adds more.
        self.extra = 0 if self.instance.pk else 1

    def get_queryset(self):
        return (super(BaseEncumbranceLineFormSet, self).get_queryset()
                .filter(parent_transaction__isnull=True).order_by('pk'))

    def get_form_kwargs(self, index):
        kwargs = super(BaseEncumbranceLineFormSet, self).get_form_kwargs(index)
        kwargs['encumbrance_date'] = self.encumbrance_date
        kwargs['encumbrance_description'] = self.encumbrance_description
        return kwargs

    def clean(self):
        """ An encumbrance with no money on it sets nothing aside. """
        super(BaseEncumbranceLineFormSet, self).clean()
        if any(self.errors):
            return
        live = [form for form in self.forms
                if form.cleaned_data and not form.cleaned_data.get('DELETE')]
        if live:
            return
        if self.instance.pk and self.instance.lines.filter(parent_transaction__isnull=False).exists():
            # Every open line was taken off, but some were matched already:
            # what is left is simply done.
            return
        raise ValidationError("An encumbrance needs at least one line with an amount. To "
                              "cancel it altogether, delete it instead.")


EncumbranceLineFormSet = inlineformset_factory(
    Encumbrance, ParsedTransaction, form=EncumbranceLineForm,
    formset=BaseEncumbranceLineFormSet, fk_name='encumbrance', extra=1, can_delete=True,
)


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
    REQUIRED_ON_REVENUE = ('fund_source',)

    class Meta(BaseAllocationForm.Meta):
        fields = ('amount', 'description', 'fund_source', 'lnl_spend_category',
                  'fr_line_target', 'funding_request', 'project_tag', 'linked_event',
                  'linked_multibill', 'non_event_revenue_type', 'audit_explanation')

    def has_changed(self):
        """
        Treat a new row with no amount as the blank row it is.

        Blank rows are drawn with the fund and category filled in from the bank
        line, and a posted form isn't filled in again. So without this every
        row left unused looks half-finished, and refuses the save for its
        missing amount. A row with no amount puts nothing on the line.
        """
        if not self.instance.pk and not (self.data.get(self.add_prefix('amount')) or '').strip():
            return False
        return super(SplitLineForm, self).has_changed()

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

    def _parent(self):
        return self.parent_transaction or self.instance.parent_transaction

    def _direction(self):
        """
        Take the direction from the bank line, not from the typed amount.

        Every slice has to run the same way as the line it splits, so the sign
        tells the form nothing it does not already know -- and read from what
        was typed, a cost entered as ``4342.40`` became a revenue row and lost
        its spend category. A refund is the exception, as on a queue row: money
        coming in that belongs on the expense side.
        """
        parent = self._parent()
        if parent is not None:
            positive = parent.net_amount > 0
            return 'revenue' if positive and not self._refund_selected() else 'expense'
        return super(SplitLineForm, self)._direction()

    def _keep_refund_routing(self):
        """
        Keep the routing a refund took from its purchase.

        The table shows the columns of the line's own direction, and a refund
        on money coming in is an expense: its spend category and FR line aren't
        on the row, so they come back blank. Put into ``cleaned_data`` before
        the checks run, so a refund on a funding request still names its line.
        """
        if not self.instance.refund_of_id:
            return
        original = self.instance.refund_of
        for name in ReconcileForm.REFUND_INHERITED:
            if name in self.fields:
                self.cleaned_data[name] = getattr(original, name)
            setattr(self.instance, name, getattr(original, name))

    def clean_amount(self):
        """
        Give the amount the bank line's sign, whichever sign was typed.

        Amounts are typed as they read on the receipt, as the encumbrance form
        takes them; ``-4342.40`` out of habit is the same answer.
        """
        amount = self.cleaned_data.get('amount')
        parent = self._parent()
        if amount is None or parent is None:
            return amount
        return -abs(amount) if parent.net_amount < 0 else abs(amount)

    def clean(self):
        """
        Inherit the purchase date before the model gets a look at it, and
        reopen the slice.

        Re-saving a split reopens it, and the page settles it again once every
        slice is saved. Checked while still Settled, each slice is weighed
        against its siblings' *old* amounts, so moving money from one settled
        slice to another could never balance one slice at a time.
        """
        self._keep_refund_routing()
        cleaned = super(SplitLineForm, self).clean()
        self._inherit_effective_date()
        self.instance.status = TransactionStatus.PENDING
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
        # Shown unsigned, as it is typed: see clean_amount().
        if self.initial.get('amount') is not None:
            self.initial['amount'] = abs(Decimal(str(self.initial['amount'])))
        # Appended, not assigned: _style_widgets() has already put
        # form-control here and replacing the attribute would strip it.
        amount = self.fields['amount'].widget
        amount.attrs['step'] = '0.01'
        amount.attrs['class'] = (amount.attrs.get('class', '') + ' split-amount').strip()
        # A table cell, not a paragraph. Every field in Meta.fields has to be
        # on screen: one the table leaves out is posted blank, and the formset
        # saves that blank over whatever the slice already held.
        note = self.fields.get('audit_explanation')
        if note is not None:
            note.widget.attrs['rows'] = 1
            note.widget.attrs.setdefault('placeholder', 'Why, if it needs saying')


class BaseSplitFormSet(BaseInlineFormSet):
    """
    Enforces the split-purchase mandate: the slices must add up to the bank
    line to the cent. This is the formset-level guard behind the disabled
    'Save' button in the UI.
    """
    def __init__(self, *args, **kwargs):
        """
        Accept the bank line being split, which every slice needs, and whether
        the person saving may settle, without which a settled entry can't be
        removed.
        """
        self.parent_transaction = kwargs.pop('parent_transaction', None)
        self.can_settle = kwargs.pop('can_settle', True)
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

        for form in self.forms:
            if not form.cleaned_data or not form.cleaned_data.get('DELETE') or form.instance.pk is None:
                continue
            # The database won't orphan a refund, so its purchase stays until
            # the refund goes.
            if form.instance.refunds.exists():
                raise ValidationError(
                    "%s has a refund recorded against it. Remove the refund first."
                    % (form.instance.description or "An entry you deleted"))
            # Read from the database: SplitLineForm.clean() has already set
            # every row to Pending, to be settled again once saved.
            if not self.can_settle and ParsedTransaction.objects.filter(
                    pk=form.instance.pk, status=TransactionStatus.SETTLED).exists():
                raise ValidationError(
                    "%s is settled, and you don't have permission to unsettle it."
                    % (form.instance.description or "An entry you deleted"))

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
            raise ValidationError("A line needs at least one entry.")

        if total != parent.net_amount:
            # Unsigned, as the amounts are typed.
            remainder = abs(parent.net_amount) - abs(total)
            raise ValidationError(
                "The entries add up to %s but the line is %s — %s. "
                "They must add up to the line exactly before it can be saved."
                % (dollars(abs(total)), dollars(abs(parent.net_amount)),
                   "%s is left to settle" % dollars(remainder) if remainder > 0
                   else "%s too much is entered" % dollars(-remainder)))
        # No check that every slice runs the line's way: SplitLineForm gives
        # each one the line's sign and direction, so half an expense cannot be
        # turned into revenue by splitting it.


SplitFormSet = inlineformset_factory(
    WorkdayTransaction, ParsedTransaction, form=SplitLineForm, formset=BaseSplitFormSet,
    fk_name='parent_transaction', extra=2, can_delete=True,
)


# ---------------------------------------------------------------------------
# Bulk actions
# ---------------------------------------------------------------------------

class BulkSelectionForm(forms.Form):
    """
    Shared behaviour for the three forms that act on a ticked set of rows.

    All three -- the ledger's bulk bar, the queue's bulk reconcile and its
    bulk encumbrance draw -- are the same shape: a hidden field that
    JavaScript fills with row ids, and a bar of controls rendered over a dark
    background. They had three verbatim copies of both, which is three places
    to fix a parsing bug in and three chances for the bars to drift apart
    visually.
    """

    # Optional so that submitting with nothing ticked reaches the view's
    # "Nothing was selected" message. Required, it fails here instead and the
    # Treasurer is told that a hidden field they have never seen is missing --
    # and the view's own branch for it becomes unreachable.
    selected = forms.CharField(widget=forms.HiddenInput, required=False)

    def __init__(self, *args, **kwargs):
        """
        Build the form, let the subclass finish it, then style what resulted.

        The order is the point. :meth:`BulkReconcileForm.build_fields` swaps
        the fund widget for a :class:`FundSourceSelect`, and a freshly
        constructed widget carries none of the attributes set on the one it
        replaced -- so styling before that runs silently loses the class on the
        one control that most needs it. Making it a hook means a subclass
        cannot get that order wrong by forgetting to re-style.
        """
        super(BulkSelectionForm, self).__init__(*args, **kwargs)
        self.build_fields()
        self._style_for_dark_bar()

    def build_fields(self):
        """
        Hook for resolving querysets and swapping widgets. No-op by default.

        Subclasses resolve their querysets here rather than at class-definition
        time so that retiring a category in the admin takes effect without a
        restart.
        """

    def _style_for_dark_bar(self):
        """
        Put ``form-control input-sm`` on every visible widget but a tick box.

        The bar these render into is dark and sets ``color: #fff``. A bare
        ``<select>`` inherits that colour while keeping the browser's own white
        background, so the value picker came out white-on-white -- present,
        focusable, and completely unreadable. ``form-control`` states both.

        These are plain ``Form``\\ s, so they get none of
        :meth:`BaseAllocationForm._style_widgets`; the one ``<select>`` that
        ever looked right was the one a template wrote out by hand.
        """
        for field in self.fields.values():
            # A tick box is skipped for the reason BaseAllocationForm._style_widgets
            # skips one: ``form-control`` is a full-width block, which turns a
            # checkbox into a stretched grey slab with its label adrift.
            if isinstance(field.widget, (forms.HiddenInput, forms.CheckboxInput)):
                continue
            existing = field.widget.attrs.get('class', '')
            # Guarded so calling this twice cannot stack duplicate classes,
            # the same way BaseAllocationForm._style_widgets guards.
            missing = [cls for cls in ('form-control', 'input-sm')
                       if cls not in existing.split()]
            if missing:
                field.widget.attrs['class'] = ' '.join([existing] + missing).strip()

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


class BulkActionForm(BulkSelectionForm):
    """ Backs the slide-up bulk action bar on the spreadsheet ledger. """
    ACTIONS = (
        ('project_tag', 'Assign project tag'),
        ('lnl_spend_category', 'Assign spend category'),
        ('fund_source', 'Assign fund source'),
        ('status', 'Set status'),
    )

    action = forms.ChoiceField(choices=ACTIONS)
    project_tag = ProjectTagChoiceField()
    lnl_spend_category = forms.ModelChoiceField(
        queryset=SpendCategory.objects.active(), required=False, label="Spend category")
    # Funds that need a line are left out on purpose: the line cannot be
    # chosen in bulk, so applying one would leave every row it touched invalid.
    fund_source = forms.ModelChoiceField(
        queryset=FundSource.objects.active().filter(draws_on=DrawsOn.NOTHING),
        required=False, label="Fund source",
        help_text="Funds that draw on a funding request or a budget are set one entry at a "
                  "time, so the line can be named.")
    status = forms.ChoiceField(choices=[('', '---')] + list(TransactionStatus.choices),
                               required=False)

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


class BulkReconcileForm(BulkSelectionForm):
    """
    Reconcile a batch of queue rows that all take the same routing.

    A monthly export arrives with a dozen Amazon supply orders on it, and every
    one of them is Consumables out of Legacy. Answering the same
    two questions twelve times is the work this page exists to remove, not the
    work it exists to make.

    Deliberately expense-only. "The same settings" for money coming in means
    "the same event", which is a different question with a different picker and
    is rarely true of a batch; revenue rows in a selection are reported and left
    alone rather than being quietly given expense routing that the database
    would refuse anyway.
    """
    # Required for the same reason ReconcileForm requires it: an expense that
    # does not say where the money came from is not reconciled, it is filed.
    #
    # Every active fund is offered, funding-request money included. It used to
    # be left out, on the same grounds as BulkActionForm: a fund that draws on
    # a request needs an FR line named beside it, so offering the fund without
    # a way to name the line would have produced a bar whose every row came
    # back invalid. The answer to that is the line picker below rather than a
    # missing fund -- a batch charged to one award is the ordinary shape of a
    # funding request being spent, and it was the one batch this bar could not
    # do.
    fund_source = forms.ModelChoiceField(
        queryset=FundSource.objects.none(), label="Fund")
    # Blank unless the chosen fund needs them, which is also when routing.js
    # unhides them -- exactly as on a queue row, request box included, so a
    # line is picked here the way it is picked everywhere else. clean() below
    # pairs the line with the fund and with the request.
    fr_request = LineRequestChoiceField()
    fr_line_target = FRLineChoiceField()
    # The same tick box the per-row form carries, for the same reason: charging
    # spending to another year's request is legitimate -- a late invoice, a
    # carried-over award -- but it has to be meant rather than mis-picked.
    allow_cross_year_fr = forms.BooleanField(
        required=False, label="Other year",
        help_text="Only tick this if the spending really belongs to another year's request.")
    lnl_spend_category = forms.ModelChoiceField(
        queryset=SpendCategory.objects.none(), required=False, label="Spend category")
    project_tag = ProjectTagChoiceField()

    def build_fields(self):
        """ Resolve the querysets per instance and fit the two routing pickers. """
        # Resolved per instance, not at import time, so retiring a category in
        # the admin takes effect without a restart.
        self.fields['fund_source'].queryset = FundSource.objects.active()
        self.fields['lnl_spend_category'].queryset = SpendCategory.objects.active()

        # Every open request, not one fiscal year's, because a selection has no
        # one year to narrow to -- the rows in it can be from either side of a
        # July. Each request leads with its year (FundingRequest.short_label)
        # and the view checks the year row by row, so nothing crosses unnoticed.
        offer_fr_lines(self, open_fr_lines())
        self.fields['fr_line_target'].help_text = (
            "Every open funding request is listed — check the year on the request you "
            "pick from.")

        fund = self.fields['fund_source']
        fund.widget = FundSourceSelect(attrs={'class': 'fin-fund-source'})
        fund.widget.choices = fund.choices

    def clean(self):
        """
        Fund and FR line are a pair, and the bar has to say so itself.

        The view validates every row it writes, so a mismatched pair would be
        caught -- but as the same refusal repeated once per selected line, with
        the fix being a field on a bar that has already been dismissed. Said
        here it is one error against the box to change, before anything is
        written. The rules are ParsedTransaction.clean()'s, worded as
        BaseAllocationForm._check_fund_and_fr_line words them, and the line has
        to be on the request chosen beside it, as on a queue row.
        """
        cleaned = super(BulkReconcileForm, self).clean()
        fund = cleaned.get('fund_source')
        line = cleaned.get('fr_line_target')

        problem = line_charge_problem(fund, line)
        if problem:
            self.add_error('fr_line_target', problem)
        elif line is not None:
            mismatch = fr_request_mismatch(line, cleaned.get('fr_request'))
            if mismatch:
                self.add_error('fr_line_target', mismatch)
        return cleaned


class OpenEncumbranceChoiceField(forms.ModelChoiceField):
    """ Open reservations, labelled with what is left rather than what was asked for. """

    def label_from_instance(self, obj):
        """ ``Spring gear order · Lights — $296.45 still encumbered · Aug 20, 2025``. """
        return "%s — %s still encumbered · %s" % (
            obj.encumbrance_label, dollars(abs(obj.amount)),
            date_format(obj.effective_date, 'M j, Y'))


class BulkEncumbranceForm(BulkSelectionForm):
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
    encumbrance = OpenEncumbranceChoiceField(
        queryset=ParsedTransaction.objects.none(), required=False,
        label="Encumbrance", empty_label="Draw from encumbrance…")

    def build_fields(self):
        """ Resolve the open reservations per instance, newest first. """
        self.fields['encumbrance'].queryset = (
            ParsedTransaction.objects
            .filter(parent_transaction__isnull=True,
                    status=TransactionStatus.PENDING,
                    amount__lt=0)
            .select_related('encumbrance')
            .order_by('-effective_date', 'encumbrance', 'pk'))


# ---------------------------------------------------------------------------
# Funding requests
# ---------------------------------------------------------------------------

def kind_for(data, instance):
    """
    The type a funding request form is for, before the form is validated.

    The line formset has to know it to be built at all -- a budget's lines
    have a number, a side and a category, a request's do not -- so it is read
    off the submitted data, falling back to what the request already is, and
    for a new one to a funding request. A request with money charged to it
    keeps its type whatever was posted: :class:`FundingRequestForm` locks it.
    """
    saved = instance is not None and instance.pk is not None
    if saved and instance.has_money:
        return instance.kind
    posted = (data.get('kind') or '') if data else ''
    if posted in FundingKind.values:
        return posted
    return instance.kind if saved else FundingKind.REQUEST


class FundingRequestForm(forms.ModelForm):
    """
    The header half of a funding request or a budget; the lines are a formset.

    One form for both, with the type at the top. A budget has no request
    number, side or opening figure of its own -- its lines carry the number
    and the side -- so those boxes are hidden for it (the template marks them
    ``fin-request-only``) and cleared on save by
    :meth:`finance.models.FundingRequest._clean_budget`.
    """
    REQUEST_ONLY = ('reference', 'is_projection', 'owed_at_books_start')

    class Meta:
        model = FundingRequest
        fields = ('kind', 'name', 'reference', 'fiscal_year', 'date_submitted', 'date_approved',
                  'is_projection', 'closed', 'owed_at_books_start', 'notes')
        widgets = {
            'kind': forms.RadioSelect,
            'date_submitted': forms.DateInput(attrs={'type': 'date'}),
            'date_approved': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        """
        Replace the plain year box with the same list the filter bar uses,
        and lock the type once money depends on it.

        Rebuilt per instance because the choices depend on the configured
        fiscal year start month, which is editable from the admin.
        """
        super(FundingRequestForm, self).__init__(*args, **kwargs)
        self.fields['fiscal_year'] = forms.ChoiceField(
            choices=fiscal_year_choices(), initial=current_fiscal_year(), label="Fiscal Year")
        # Almost always zero, so a blank box means zero rather than an error.
        self.fields['owed_at_books_start'].required = False
        kind = self.fields['kind']
        kind.required = False
        if self.instance.pk is not None and self.instance.has_money:
            # The money was charged to the fund that draws on this type, so
            # changing it would leave every entry on the wrong side of a rule.
            kind.disabled = True
            kind.help_text = ("Money is charged to it or SGA has paid for it, so its type can't "
                              "change.")
            # Each entry took its side from the request when it was saved.
            side = self.fields['is_projection']
            side.disabled = True
            side.help_text = ("Money is charged to it or SGA has paid for it, so its side can't "
                              "change.")
        self.helper = finance_form_helper()

    def clean_kind(self):
        """ Nothing posted keeps the type it had, or makes a funding request. """
        return self.cleaned_data.get('kind') or self.instance.kind or FundingKind.REQUEST

    def clean_owed_at_books_start(self):
        """ A blank is zero: nothing was owed before the books started. """
        return self.cleaned_data.get('owed_at_books_start') or Decimal('0.00')


class FRLineItemForm(forms.ModelForm):
    """
    One line inside a funding request or a budget.

    Rendered as a row in a formset, so the overrides below are about the row
    being *blank*: ``sort_order`` carries a model default, and a default is
    enough to make Django think an untouched row was filled in.

    A budget line has two more things: a four-digit Request ID and a side.
    It is nested under one of the budget's categories, which the form takes
    as ``category_key`` -- a saved category's pk, or the key the page gave a
    category added on it and not saved yet -- because the category may not
    exist until the form is saved (see :meth:`BaseFRLineItemFormSet.assign_categories`).
    The page fills it in from the category the row sits under. A request's
    lines have none of the three, so they are cleared for one.
    """
    BUDGET_ONLY = ('category_key', 'number', 'is_projection')

    category_key = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = FRLineItem
        fields = ('number', 'name', 'description', 'amount_requested', 'amount_awarded',
                  'is_projection', 'lnl_spend_category', 'sort_order')
        widgets = {
            'description': forms.Textarea(attrs={
                'rows': 2, 'placeholder': 'What this line covers'}),
            # No placeholder: a grey 4521 in an empty box reads as the line's own.
            'number': forms.TextInput(attrs={'inputmode': 'numeric', 'maxlength': '4',
                                             'size': '5'}),
            # No placeholder either: grey words in an empty box read as a
            # dropdown's prompt. Blank is pending SGA approval, which the tag
            # under the box says (approval_state), so it is never read as $0.
            'amount_requested': forms.NumberInput(attrs={'title': 'Amount asked of SGA, in dollars'}),
            'amount_awarded': forms.NumberInput(attrs={
                'title': 'Amount SGA approved, in dollars. Leave blank while pending SGA approval; '
                         'enter 0 if SGA denied it.'}),
        }

    def __init__(self, *args, **kwargs):
        """ Stop Django demanding a hand-typed sort order on every row. """
        self.kind = kwargs.pop('kind', None) or FundingKind.REQUEST
        super(FRLineItemForm, self).__init__(*args, **kwargs)
        # sort_order carries a model default, but Django still renders it as
        # mandatory, which meant no line could be saved without hand-typing a
        # number. The formset fills it in from row position instead.
        self.fields['sort_order'].required = False
        self.fields['sort_order'].label = "Order"
        self.fields['sort_order'].help_text = ""
        self.fields['lnl_spend_category'].label = "Spend category"
        if self.instance.pk is not None:
            self.initial.setdefault('category_key', str(self.instance.category_id or ''))

    @property
    def approval_state(self):
        """
        What the Approved box says as it stands: 'pending' when blank, 'denied'
        at 0, '' for an amount (or anything not a number, which clean() will
        reject). Read by the row's tag; js/fr_lines.js keeps it current.
        """
        value = self['amount_awarded'].value()
        if value is None or str(value).strip() == '':
            return 'pending'
        try:
            return 'denied' if Decimal(str(value).strip()) == 0 else ''
        except (InvalidOperation, ValueError):
            return ''

    def has_changed(self):
        """
        Decide "is this row blank?" on what the user actually typed.

        ``sort_order`` carries a model default of 0, and the page writes the
        order and the category into every row it sends, so on a new row they
        count as changed the moment it is rendered -- which made an untouched
        row look filled in and demand a name. On a saved line they are real
        changes: the line was moved.
        """
        if self.instance.pk is not None:
            return super(FRLineItemForm, self).has_changed()
        return bool(set(self.changed_data) - {'sort_order', 'category_key'})

    def clean(self):
        """
        Refuse an approved amount cut below what has already been spent
        against it, or taken back to pending once anything is charged.
        """
        cleaned = super(FRLineItemForm, self).clean()
        if self.kind != FundingKind.BUDGET:
            cleaned['category_key'] = ''
            cleaned['number'] = ''
            cleaned['is_projection'] = False
        # Guard the burndown: what is approved cannot be cut below what is spent.
        if self.instance.pk and not cleaned.get('DELETE') and 'amount_awarded' not in self.errors:
            awarded = cleaned.get('amount_awarded')
            if awarded is None:
                if self.instance.allocations.exists():
                    self.add_error('amount_awarded',
                                   "Money is charged to this line, so it can't go back to pending "
                                   "SGA approval. Enter what SGA approved.")
            else:
                spent = self.instance.spent
                if awarded < spent:
                    self.add_error('amount_awarded',
                                   "%s is already spent against this line; the approved amount "
                                   "cannot be lowered below that." % dollars(spent))
        return cleaned


class BaseFRLineItemFormSet(BaseInlineFormSet):
    """
    A request's or a budget's lines. Numbers them by where they sit in the
    table, unless told otherwise, and nests a budget's lines under their
    categories.

    ``kind`` is the type the lines are for; see :func:`kind_for`. Left out, it
    is the saved request's own.
    """

    def __init__(self, *args, **kwargs):
        self.kind = kwargs.pop('kind', None)
        super(BaseFRLineItemFormSet, self).__init__(*args, **kwargs)
        saved = self.instance is not None and self.instance.pk is not None
        if self.kind is None:
            self.kind = self.instance.kind if saved else FundingKind.REQUEST
        # Asked once here rather than by each of a hundred rows.
        self.charged = set()
        if saved:
            self.charged = set(ParsedTransaction.objects
                               .filter(fr_line_target__funding_request=self.instance)
                               .values_list('fr_line_target_id', flat=True))

    def get_form_kwargs(self, index):
        kwargs = super(BaseFRLineItemFormSet, self).get_form_kwargs(index)
        kwargs['kind'] = self.kind
        return kwargs

    def add_fields(self, form, index):
        """ Lock the side of a line with money on it (see :class:`FRLineItem`). """
        super(BaseFRLineItemFormSet, self).add_fields(form, index)
        if form.instance.pk in self.charged:
            side = form.fields['is_projection']
            side.disabled = True
            side.widget.attrs['title'] = ("Money is charged to this line, so its side can't "
                                          "change.")

    @property
    def is_budget(self):
        return self.kind == FundingKind.BUDGET

    def _live_forms(self):
        """ The rows that will be saved: filled in and not being removed. """
        return [form for form in self.forms
                if form.cleaned_data and not form.cleaned_data.get('DELETE')]

    def clean(self):
        """
        Refuse to delete a line anything is charged to, refuse two budget
        lines with one Request ID, and number any line that was left without
        an explicit order.
        """
        super(BaseFRLineItemFormSet, self).clean()
        if any(self.errors):
            return
        for form in self.forms:
            if (form.cleaned_data and form.cleaned_data.get('DELETE') and form.instance.pk
                    and form.instance.allocations.exists()):
                raise ValidationError(
                    "“%s” can't be deleted: entries or encumbrances are charged to it. Move them "
                    "to another line first." % form.instance.name)
        if self.is_budget:
            check_request_ids((form.cleaned_data.get('number'), form.cleaned_data.get('name'))
                              for form in self._live_forms())
        position = 0
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get('DELETE'):
                continue
            if form.cleaned_data.get('sort_order') in (None, ''):
                form.instance.sort_order = position
            position += 1

    def assign_categories(self, categories):
        """
        Nest each line under the category its row sat under, before the lines
        are saved. ``categories`` is ``{key: BudgetCategory or None}`` from
        :meth:`BaseBudgetCategoryFormSet.by_key`; a key it does not know -- a
        category removed on the page -- leaves the line with no category. A
        request's lines have none.
        """
        for form in self._live_forms():
            key = form.cleaned_data.get('category_key') or ''
            form.instance.category = categories.get(key) if self.is_budget else None


# `extra` only sets how many blank rows are rendered up front. The form's
# "Add" buttons raise TOTAL_FORMS at runtime, so a request can carry as many
# lines as it needs.
FRLineItemFormSet = inlineformset_factory(
    FundingRequest, FRLineItem, form=FRLineItemForm, formset=BaseFRLineItemFormSet,
    extra=3, can_delete=True)


class BudgetCategoryForm(forms.ModelForm):
    """
    One of a budget's categories: its name, and where it sits among the rest.

    ``key`` is how the lines nested under it name it before it is saved: a
    saved category's pk, or ``new-3`` for one added on the page. The page
    keeps it and ``sort_order`` up to date, so neither is typed.
    """
    key = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = BudgetCategory
        fields = ('name', 'sort_order')
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Category name',
                                           'class': 'fin-category-name'}),
            'sort_order': forms.HiddenInput,
        }

    def __init__(self, *args, **kwargs):
        super(BudgetCategoryForm, self).__init__(*args, **kwargs)
        self.fields['sort_order'].required = False
        # Checked in clean_name, to say what to do about it.
        self.fields['name'].required = False
        if self.instance.pk is not None:
            self.initial.setdefault('key', str(self.instance.pk))

    def has_changed(self):
        """
        A category the page added has a key, and is there to be saved; the
        empty one the page clones new categories from has none.
        """
        if self.instance.pk is not None:
            return super(BudgetCategoryForm, self).has_changed()
        return bool(set(self.changed_data) - {'sort_order'})

    def clean_name(self):
        name = ' '.join((self.cleaned_data.get('name') or '').split())
        if not name:
            raise ValidationError("Every category needs a name. Name it, or remove it.")
        return name

    def clean_sort_order(self):
        value = self.cleaned_data.get('sort_order')
        return self.instance.sort_order if value is None else value


class BaseBudgetCategoryFormSet(BaseInlineFormSet):
    """
    A budget's categories, one level deep: each holds lines, never another
    category. Added, renamed, reordered and removed on the budget's form;
    removing one leaves its lines with no category.
    """

    def clean(self):
        """ Refuse two categories with one name, whatever the case. """
        super(BaseBudgetCategoryFormSet, self).clean()
        if any(self.errors):
            return
        seen = set()
        for form in self.forms:
            data = form.cleaned_data or {}
            if data.get('DELETE') or not data.get('name'):
                continue
            name = data['name']
            if name.lower() in seen:
                raise ValidationError(
                    "Two categories are both called “%s”. Rename one, or move the lines of one "
                    "into the other and remove it." % name)
            seen.add(name.lower())

    def by_key(self):
        """
        ``{key: BudgetCategory or None}`` once the formset is saved: what each
        key the lines may carry now means. A removed category means ``None``,
        so its lines are left with no category.
        """
        found = {'': None}
        for form in self.forms:
            data = form.cleaned_data or {}
            kept = form.instance.pk is not None and not data.get('DELETE')
            category = form.instance if kept else None
            if data.get('key'):
                found[data['key']] = category
            if category is not None:
                found[str(category.pk)] = category
        return found


BudgetCategoryFormSet = inlineformset_factory(
    FundingRequest, BudgetCategory, form=BudgetCategoryForm, formset=BaseBudgetCategoryFormSet,
    extra=0, can_delete=True)


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
        fields = ('name', 'parent', 'description', 'is_projection', 'archived')
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, **kwargs):
        """ Keep the tag, and everything under it, out of its own parent list. """
        super(ProjectTagForm, self).__init__(*args, **kwargs)
        qs = ProjectTag.objects.all()
        if self.instance.pk:
            # Prevent making a node its own ancestor.
            qs = qs.exclude(pk__in=self.instance.get_descendants(include_self=True))
        self.fields['parent'].queryset = qs
        self.helper = finance_form_helper()


# ---------------------------------------------------------------------------
# Fund balances
# ---------------------------------------------------------------------------

def _money_field(label, help_text='', required=False, **kwargs):
    """ A two-decimal amount box, styled like the rest of the finance forms. """
    return forms.DecimalField(
        label=label, help_text=help_text, required=required, max_digits=12,
        decimal_places=2, widget=forms.NumberInput(attrs={'step': '0.01',
                                                          'class': 'form-control'}),
        **kwargs)


class BalanceCheckpointForm(forms.ModelForm):
    """ Write down what Workday says one account holds on one day. """

    class Meta:
        model = BalanceCheckpoint
        fields = ('account', 'as_of', 'balance', 'note')
        widgets = {'as_of': forms.DateInput(attrs={'type': 'date'})}

    def __init__(self, *args, **kwargs):
        """ Default to today: the figure a Treasurer usually has open is today's. """
        super(BalanceCheckpointForm, self).__init__(*args, **kwargs)
        if not self.instance.pk:
            self.fields['as_of'].initial = timezone.localdate()
        self.fields['account'].queryset = PartitionCode.objects.order_by('code')
        self.helper = finance_form_helper()


class FundTransferForm(forms.ModelForm):
    """
    Move money between two funds inside one account.

    Only the ordinary kind is made here. Opening splits and year-end transfers
    are written by their own pages, which know what they are replacing.
    """

    class Meta:
        model = FundTransfer
        fields = ('account', 'date', 'from_fund', 'to_fund', 'amount', 'description')
        widgets = {'date': forms.DateInput(attrs={'type': 'date'})}

    def __init__(self, *args, **kwargs):
        """ Offer only funds still in use. """
        self.books_start = kwargs.pop('books_start', None)
        super(FundTransferForm, self).__init__(*args, **kwargs)
        funds = FundSource.objects.active()
        self.fields['from_fund'].queryset = funds
        self.fields['to_fund'].queryset = funds
        self.fields['account'].queryset = PartitionCode.objects.order_by('code')
        self.helper = finance_form_helper()

    def clean_date(self):
        """
        Refuse a date before the books start.

        Nothing before that day is counted, so a transfer dated earlier would
        silently do nothing. What each fund held on the first day is the
        opening split, which has a page of its own.
        """
        date = self.cleaned_data['date']
        if self.books_start and date < self.books_start:
            raise ValidationError(
                "The books start on %s, and nothing before that counts. To say what each "
                "fund held on that day, use Opening balances instead."
                % date_format(self.books_start, 'M j, Y'))
        return date

    def clean(self):
        """
        Refuse a fund held in another account, unless it has money in this one.

        The transfer moves money inside the account it names. A fund held in
        another account has nothing here to move: the transfer would give the
        other fund a row on this account and leave its real balance untouched,
        and the money would appear out of nowhere. The exception is a fund this
        account's own lines were charged to -- a funding request paid out of
        315-AG, say -- whose row here the year-end close squares the same way.
        """
        cleaned = super(FundTransferForm, self).clean()
        account = cleaned.get('account')
        if account is None:
            return cleaned
        elsewhere = [(name, cleaned[name]) for name in ('from_fund', 'to_fund')
                     if cleaned.get(name) is not None
                     and cleaned[name].account_id not in (None, account.pk)]
        if not elsewhere:
            return cleaned
        from finance.balances import Books

        here, _, _ = Books().positions(account.code, cleaned.get('date') or timezone.localdate())
        for name, fund in elsewhere:
            if fund.pk not in here:
                self.add_error(name, "%s is held in %s, and nothing in %s is charged to it, so it has "
                                     "nothing here to move. Pick a fund held in %s, or record this on %s."
                               % (fund, fund.account.code, account.code, account.code, fund.account.code))
        return cleaned


class OpeningBalancesForm(forms.Form):
    """
    What each account held the night before the books started, and how it split.

    One amount per account, which is a Workday balance, and one per fund held
    in that account other than its own money. The own fund is never asked for:
    it is whatever the others leave, which is what makes the split add up to
    Workday's figure whatever is typed.
    """

    def __init__(self, *args, **kwargs):
        """ One section per account that has money of its own to split. """
        self.books_start = kwargs.pop('books_start')
        accounts = kwargs.pop('accounts')
        super(OpeningBalancesForm, self).__init__(*args, **kwargs)
        night_before = self.books_start - datetime.timedelta(days=1)
        self.sections = []
        for account, own, funds, cash, existing in accounts:
            cash_name = 'cash_%s' % account.pk
            self.fields[cash_name] = _money_field(
                "Workday balance at the end of %s" % date_format(night_before, 'M j, Y'),
                help_text="Leave blank if you only have a later balance. Enter that one as "
                          "a Workday balance instead, and this is worked out from it.",
                initial=cash)
            names = []
            for fund in funds:
                name = 'fund_%s_%s' % (account.pk, fund.pk)
                self.fields[name] = _money_field(
                    fund.name, initial=existing.get(fund.pk) or None,
                    help_text=("Negative for spending SGA had not reimbursed yet."
                               if fund.is_reimbursed else ''))
                names.append((fund, name))
            # Bound fields for the template, names for section_values().
            self.sections.append({'account': account, 'own': own, 'cash_name': cash_name,
                                  'cash': self[cash_name], 'fund_names': names,
                                  'funds': [(fund, self[name]) for fund, name in names]})

    def section_values(self):
        """ ``[(account, own fund, cash or None, {fund: amount})]`` once valid. """
        out = []
        for section in self.sections:
            amounts = {fund: money(self.cleaned_data.get(name))
                       for fund, name in section['fund_names']}
            out.append((section['account'], section['own'],
                        self.cleaned_data.get(section['cash_name']), amounts))
        return out


class YearCloseForm(forms.Form):
    """
    The few answers closing a year needs from a person.

    Each account's Workday balance on June 30, so the close can say whether the
    ledger agrees with the bank; whether to cover each budget overspend from
    the account's own money; and how much of each unpaid reimbursement, if any,
    to give up on.
    """
    notes = forms.CharField(
        required=False, label="Notes",
        widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        help_text="Anything the next Treasurer should know about this year.")

    def __init__(self, *args, **kwargs):
        """ Build one question per account, and one per balance that needs an answer. """
        self.year = kwargs.pop('year')
        self.proposals = kwargs.pop('proposals')
        super(YearCloseForm, self).__init__(*args, **kwargs)
        year_end = fiscal_year_bounds(self.year.fiscal_year)[1]
        self.workday_fields = []
        for account in self.year.accounts:
            name = 'workday_%s' % account.account.pk
            existing = next((row.checkpoint.balance for row in account.checkpoints
                             if row.checkpoint.as_of == year_end), None)
            self.fields[name] = _money_field(
                "%s on %s" % (account.code, date_format(year_end, 'M j, Y')), initial=existing,
                help_text="The balance Workday shows. Optional, but it is the only check "
                          "that no line is missing.")
            self.workday_fields.append((account, name))

        for proposal in self.proposals:
            key = '%s_%s' % (proposal['account'].account.pk, proposal['row'].fund.pk)
            if proposal['kind'] == 'cover':
                proposal['field'] = 'cover_%s' % key
                self.fields[proposal['field']] = forms.BooleanField(
                    required=False, initial=True,
                    label="Cover the %s overspend from %s" % (
                        dollars(proposal['amount']), proposal['account'].own_fund))
            else:
                proposal['field'] = 'write_off_%s' % key
                self.fields[proposal['field']] = _money_field(
                    "Write off", min_value=ZERO, max_value=money(proposal['amount']),
                    help_text="Only what SGA will not pay. The rest carries forward, still "
                              "owed to LNL.")
            proposal['bound_field'] = self[proposal['field']]

    @property
    def workday_rows(self):
        """ ``[(account statement, bound field)]`` for the template. """
        return [(account, self[name]) for account, name in self.workday_fields]

    def workday_balances(self):
        """ ``[(account statement, balance)]`` for each balance typed in. """
        return [(account, self.cleaned_data.get(name)) for account, name in self.workday_fields
                if self.cleaned_data.get(name) is not None]

    def transfers(self):
        """ ``[(account statement, fund, amount, description)]`` the close should make. """
        short_year = str(self.year.fiscal_year)[-2:]
        out = []
        for proposal in self.proposals:
            account, row = proposal['account'], proposal['row']
            if proposal['kind'] == 'cover':
                if self.cleaned_data.get(proposal['field']):
                    out.append((account, row.fund, money(proposal['amount']),
                                "FY%s %s overspend covered from %s"
                                % (short_year, row.fund, account.own_fund)))
            else:
                amount = money(self.cleaned_data.get(proposal['field']))
                if amount > 0:
                    out.append((account, row.fund, amount,
                                "FY%s %s that SGA will not reimburse, written off to %s"
                                % (short_year, row.fund, account.own_fund)))
        return out
