"""
The forms for creating, editing and emailing bills and multi-bills.

Two styles live here. The bill and email forms moved from the events app with
the bills, unchanged, so they still lay themselves out the way the events
app's forms do: each renders its own ``<form>`` and buttons through crispy,
inside the site's generic form templates. The multi-bill forms were rewritten
in finance and follow :mod:`finance.forms`: their templates write the
``<form>`` and the buttons, and the helper comes from
:func:`finance.forms.finance_form_helper`.
"""
import datetime
import re
from collections import Counter

from ajax_select.fields import AutoCompleteSelectField, AutoCompleteSelectMultipleField
from crispy_forms.bootstrap import FormActions, PrependedText
from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Layout, Reset, Submit
from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.formats import date_format

from events.models import BaseEvent, Event2019, Organization
from finance.forms import finance_form_helper
from finance.models import (ISD_NUMBER_FORMAT, ZERO, Billing, BillingEmail, MultiBilling, MultiBillingCharge,
                            MultiBillingEmail, NoBillNeeded, default_rental_fee_percent, money,
                            normalise_isd_number)


class CustomOrganizationEmailModelMultipleChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, org):
        return '%s (%s)' % (org.name, org.exec_email)


class BillingForm(forms.ModelForm):
    def __init__(self, event, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        self.helper.form_method = "post"
        self.helper.form_action = ""
        self.event = event
        self.helper.layout = Layout(
            PrependedText('date_billed', '<i class="glyphicon glyphicon-calendar"></i>', css_class="datepick"),
            PrependedText('amount', '<strong>$</strong>'),
            FormActions(
                Submit('save-and-return', 'Save and Return'),
                Submit('save-and-make-email', 'Save and Make Email'),
                Reset('reset', 'Reset Form'),
            )
        )
        super(BillingForm, self).__init__(*args, **kwargs)

        self.fields['amount'].initial = "%.2f" % event.cost_total
        self.fields['date_billed'].initial = datetime.date.today()

    def save(self, commit=True):
        obj = super(BillingForm, self).save(commit=False)
        obj.event = self.event
        if commit:
            obj.save()
        return obj

    class Meta:
        model = Billing
        fields = ('date_billed', 'amount')


class BillingUpdateForm(forms.ModelForm):
    """
    The bill's amount. Whether it is paid is not here: marking a bill paid,
    and saying how when no payment from Workday covers it, is the *Mark paid*
    form's (:class:`BillPaidForm`).
    """
    def __init__(self, event, *args, **kwargs):
        self.event = event
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        self.helper.form_method = "post"
        self.helper.form_action = ""

        self.helper.layout = Layout(
            PrependedText('amount', '<strong>$</strong>'),
            FormActions(
                Submit('save', 'Save Changes'),
                Reset('reset', 'Reset Form'),
            )
        )
        super(BillingUpdateForm, self).__init__(*args, **kwargs)

        self.fields['amount'].initial = str(event.cost_total)

    def save(self, commit=True):
        obj = super(BillingUpdateForm, self).save(commit=False)
        obj.event = self.event
        if commit:
            obj.save()
        return obj

    class Meta:
        model = Billing
        fields = ('amount',)


def billable_events(bill=None, include_unmarked=False):
    """
    The events a multi-bill may cover, earliest first.

    Reviewed, still open, with no bill of their own, on no other multi-bill
    (an event on two bills would be billed twice), and not marked *No bill
    needed*. Only events marked to be billed in bulk unless
    ``include_unmarked``. The events already on ``bill`` are always offered,
    so editing it can keep them.
    """
    others = MultiBilling.objects.all()
    if bill is not None and bill.pk:
        others = others.exclude(pk=bill.pk)
    events = (BaseEvent.objects.filter(closed=False, reviewed=True, billings__isnull=True,
                                       no_bill_needed__isnull=True)
              .exclude(multibillings__in=others))
    if not include_unmarked:
        events = events.filter(billed_in_bulk=True)
    if bill is not None and bill.pk:
        events = events | BaseEvent.objects.filter(multibillings=bill)
    return (events.distinct().select_related('billing_org').prefetch_related('org')
            .order_by('datetime_start', 'pk'))


def client_tally(events):
    """
    The clients a set of events would be billed to, most events first, as
    ``[(org, count)]``. Events with no client on file are left out. A tie goes
    to the client of the earlier event.
    """
    clients = [event.org_to_be_billed for event in sorted(events, key=lambda e: (e.datetime_start, e.pk))]
    return Counter(org for org in clients if org is not None).most_common()


class BillableEventField(forms.ModelMultipleChoiceField):
    """ Each event labelled with who it would be billed to and when it ran. """

    def label_from_instance(self, event):
        client = event.org_to_be_billed
        when = date_format(timezone.localtime(event.datetime_start), 'M j, Y')
        return '%s — %s (%s)' % (event.event_name, client.retname if client else 'no client on file', when)


class MultiBillForm(forms.ModelForm):
    """
    Creating a multi-bill, or changing one that is not paid yet: the events it
    covers, who it is billed to, what it is called, and whether its invoice
    carries each event's own.

    There is no total to type. The bill comes to its events' prices plus its
    own charges, worked out by :meth:`MultiBilling.breakdown` and saved when
    the form is.

    Events with different clients may share a bill -- a run of films booked
    partly under "LNL" and partly under "LNL + SocComm Films" is one bill --
    but only once the Treasurer has seen the clients listed and ticked the
    box. The box appears only when the chosen events disagree.
    """
    events = BillableEventField(queryset=BaseEvent.objects.none(), widget=forms.CheckboxSelectMultiple)
    org = AutoCompleteSelectField('Orgs', required=False, label="Bill to",
                                  help_text="Leave blank to bill the client most of these events are for.")
    confirm_mixed_clients = forms.BooleanField(required=False)

    class Meta:
        model = MultiBilling
        fields = ('events', 'org', 'name', 'description', 'date_billed', 'attach_event_invoices')
        widgets = {'date_billed': forms.DateInput(attrs={'type': 'date'}),
                   'description': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, include_unmarked=False, **kwargs):
        super(MultiBillForm, self).__init__(*args, **kwargs)
        self.fields['events'].queryset = billable_events(self.instance, include_unmarked)
        self.fields['events'].help_text = (
            "Reviewed events with no bill yet. Events already on another multi-bill are not listed."
            if include_unmarked else
            "Reviewed events marked to be billed in bulk, with no bill yet. Events already on another "
            "multi-bill are not listed.")
        if not self.instance.pk:
            self.fields['date_billed'].initial = datetime.date.today()

        # The box is offered only when the events disagree about their client:
        # the ones submitted, or, before anything is, the ones already on the
        # bill -- which were confirmed when it was made, so the box starts
        # ticked -- or the ones ticked on the Billing page, which were not.
        self.clients = self._submitted_clients()
        fields = ['events', 'org']
        if len(self.clients) > 1:
            self.fields['confirm_mixed_clients'].label = "Bill these together: they are for %s" % ', '.join(
                '%s (%s event%s)' % (org.retname, count, '' if count == 1 else 's') for org, count in self.clients)
            self.fields['confirm_mixed_clients'].initial = not self.is_bound and bool(self.instance.pk)
            fields.append('confirm_mixed_clients')
        self.helper = finance_form_helper()
        self.helper.layout = Layout(*(fields + ['name', 'description', 'date_billed', 'attach_event_invoices']))

    def _submitted_clients(self):
        """
        The client tally of the events in the submitted data, before it is
        validated -- or, on a form not yet submitted, of the bill's own events,
        or of the events it starts with ticked.
        """
        if not self.is_bound:
            if self.instance.pk:
                return client_tally(self.instance.events.all())
            chosen = self.initial.get('events') or []
            return client_tally(self.fields['events'].queryset.filter(pk__in=chosen)) if chosen else []
        submitted = self.fields['events'].widget.value_from_datadict(self.data, self.files, self.add_prefix('events'))
        pks = [pk for pk in (submitted or []) if str(pk).isdigit()]
        return client_tally(self.fields['events'].queryset.filter(pk__in=pks)) if pks else []

    def clean(self):
        cleaned = super(MultiBillForm, self).clean()
        events = cleaned.get('events')
        if not events:
            return cleaned
        tally = client_tally(events)
        if cleaned.get('org') is None:
            if not tally:
                self.add_error('org', "None of these events has a client on file, so choose who to bill.")
            else:
                cleaned['org'] = tally[0][0]
        if len(tally) > 1 and not cleaned.get('confirm_mixed_clients'):
            self.add_error('confirm_mixed_clients',
                           "These events are for different clients. Tick the box to bill them together.")
        return cleaned

    def save(self, commit=True):
        bill = super(MultiBillForm, self).save(commit=False)
        if bill.amount is None:
            bill.amount = ZERO
        if commit:
            bill.save()
            self.save_m2m()
            bill.recalculate()
        return bill


class MultiBillChargeForm(forms.ModelForm):
    """
    One of a multi-bill's own charges. Which boxes matter depends on the kind:
    quantity and price for a one-off or a rental, a percentage for a fee or
    discount. The ones that do not apply are cleared rather than kept, because
    the database refuses a charge priced both ways.
    """
    add_rental_fee = forms.BooleanField(required=False, initial=True)

    class Meta:
        model = MultiBillingCharge
        fields = ('kind', 'description', 'quantity', 'unit_price', 'percent')
        labels = {'unit_price': "Price each", 'percent': "Percent"}

    def __init__(self, *args, **kwargs):
        super(MultiBillChargeForm, self).__init__(*args, **kwargs)
        rate = self.instance.rental_fee_percent
        if rate is None:
            rate = default_rental_fee_percent()
        self.fields['add_rental_fee'].label = "Add the %s%% rental fee" % rate.normalize()
        self.fields['add_rental_fee'].help_text = "Rentals only, as on an event."
        if self.instance.pk:
            self.fields['add_rental_fee'].initial = self.instance.rental_fee_percent is not None
        self.fields['quantity'].min_value = 1
        self.helper = finance_form_helper()
        self.helper.layout = Layout('kind', 'description', 'quantity', 'unit_price', 'add_rental_fee', 'percent')

    def clean(self):
        cleaned = super(MultiBillChargeForm, self).clean()
        kind = cleaned.get('kind')
        if kind == MultiBillingCharge.PERCENT:
            percent = cleaned.get('percent')
            if percent is None:
                self.add_error('percent', "Enter the percentage: 10 for a fee, -10 for a discount.")
            elif percent == 0 or not -100 <= percent <= 100:
                self.add_error('percent', "Enter a percentage between -100 and 100, other than 0.")
            cleaned['unit_price'] = None
            cleaned['quantity'] = 1
            cleaned['add_rental_fee'] = False
        elif kind:
            if cleaned.get('unit_price') is None:
                if 'unit_price' not in self.errors:
                    self.add_error('unit_price', "Enter the price of one.")
            elif kind == MultiBillingCharge.RENTAL and cleaned['unit_price'] < 0:
                self.add_error('unit_price', "A rental cannot be a credit. Add a credit as a one-off charge.")
            if not cleaned.get('quantity') and 'quantity' not in self.errors:
                self.add_error('quantity', "Enter how many.")
            cleaned['percent'] = None
            if kind != MultiBillingCharge.RENTAL:
                cleaned['add_rental_fee'] = False
        return cleaned

    def save(self, commit=True):
        charge = super(MultiBillChargeForm, self).save(commit=False)
        if not self.cleaned_data.get('add_rental_fee'):
            charge.rental_fee_percent = None
        elif charge.rental_fee_percent is None:
            # Fixed when the fee is first added, so a later change to the
            # default pricelist does not reprice a bill already sent.
            charge.rental_fee_percent = default_rental_fee_percent()
        if commit:
            charge.save()
        return charge


class BillSentForm(forms.Form):
    """
    When a bill (or a multi-bill) reached its client some other way than its
    email from lnldb, and how: handed over at a meeting, or sent from the
    Treasurer's own inbox. It moves the bill on to *Waiting on client*, as the
    email would.
    """
    sent_on = forms.DateField(label="Sent on", widget=forms.DateInput(attrs={'type': 'date'}))
    sent_note = forms.CharField(required=False, max_length=200, label="How it was sent",
                                help_text="Such as handed over at a meeting, or emailed from your own inbox.")

    def __init__(self, *args, **kwargs):
        self.bill = kwargs.pop('bill')
        super(BillSentForm, self).__init__(*args, **kwargs)
        self.helper = finance_form_helper()

    def clean_sent_on(self):
        day = self.cleaned_data['sent_on']
        if day > timezone.localdate():
            raise ValidationError("A bill cannot have been sent after today.")
        if day < self.bill.date_billed:
            raise ValidationError("The bill was made on %s, so it cannot have been sent before then."
                                  % date_format(self.bill.date_billed, 'M j, Y'))
        return day


class BillPaidForm(forms.Form):
    """
    When a bill (or a multi-bill) was paid, and how, when it was not through
    Workday.

    ``covered`` says whether the payments filed against the bill add up to
    it. When they do, how it was paid may be left blank. When they do not --
    cash, a check, a bill from before the books start -- it must be said, so
    that a bill marked paid with no payment behind it always says why.
    """
    date_paid = forms.DateField(label="Paid on", widget=forms.DateInput(attrs={'type': 'date'}))
    paid_note = forms.CharField(required=False, max_length=200, label="How it was paid")

    def __init__(self, *args, **kwargs):
        covered = kwargs.pop('covered', False)
        super(BillPaidForm, self).__init__(*args, **kwargs)
        self.helper = finance_form_helper()
        note = self.fields['paid_note']
        if covered:
            note.help_text = "Only if it was not paid through Workday."
        else:
            note.required = True
            note.help_text = ("No payment received in Workday covers this bill, so say how it was paid: cash, a "
                              "check, or a bill from before the books start.")
            note.error_messages['required'] = "Say how it was paid. No payment received in Workday covers it."

    def clean_date_paid(self):
        day = self.cleaned_data['date_paid']
        if day > timezone.localdate():
            raise ValidationError("A bill cannot have been paid after today.")
        return day


# ---------------------------------------------------------------------------
# What a bill is charged to in Workday
#
# The worktag usually comes back through the bill's own form, on the event. A
# client who replies by email instead -- and every multi-bill's client, since
# a multi-bill has no form -- has it recorded by the Treasurer. Recording the
# ISD then takes the worktag, the fund and the amount it charged, and the
# number Workday gave it.
# ---------------------------------------------------------------------------

#: A worktag as the client's own form accepts it: "1234-CC", "123-AG".
WORKTAG_FORMAT = re.compile(r'[0-9]+-[A-Z][A-Z]')


def bill_events(bill):
    """ The events a bill is for, as their own kind (an ``Event2019`` reads its worktag). """
    if isinstance(bill, MultiBilling):
        pks = list(bill.events.values_list('pk', flat=True))
    else:
        pks = [bill.event_id]
    return sorted(BaseEvent.objects.filter(pk__in=pks), key=lambda e: (e.datetime_start, e.pk))


def worktag_prefill(bill, events):
    """
    The worktag and fund to start a bill's form with, and where they came
    from, as ``(worktag, fund, source)``. What the bill already records comes
    first; then what the client sent through the bill's form; then what is on
    file for the client from their last bill, which still has to be confirmed
    with them.
    """
    if bill.worktag_charged:
        return bill.worktag_charged, bill.fund_charged, "recorded on this bill."
    if not isinstance(bill, MultiBilling) and events:
        event = events[0]
        if getattr(event, 'worktag', None):
            return event.worktag, getattr(event, 'workday_fund', None), \
                "sent by the client through the bill's form."
    client = bill.org if isinstance(bill, MultiBilling) else (events[0].org_to_be_billed if events else None)
    if client is not None and client.worktag:
        return client.worktag, client.workday_fund, \
            "on file for %s from their last bill. Confirm it with them." % client.retname
    return '', None, ''


def _fund_choices():
    return [('', '---------')] + list(Event2019._meta.get_field('workday_fund').choices)


class BillWorktagForm(forms.Form):
    """
    The worktag and fund to charge, for a client who replied to the bill by
    email. Saving it moves the bill to *Create ISD*.
    """
    worktag = forms.CharField(max_length=20, help_text="Such as 1234-CC.")
    fund = forms.TypedChoiceField(coerce=int, choices=(), label="Funding source")

    def __init__(self, *args, bill=None, events=(), **kwargs):
        super(BillWorktagForm, self).__init__(*args, **kwargs)
        self.bill = bill
        self.events = list(events)
        self.fields['fund'].choices = _fund_choices()
        worktag, fund, source = worktag_prefill(bill, self.events)
        if not self.is_bound:
            self.initial.setdefault('worktag', worktag)
            self.initial.setdefault('fund', fund)
        if source:
            self.fields['worktag'].help_text = "Filled in: %s" % source
        self.helper = finance_form_helper()
        self.helper.layout = Layout(*self.layout_fields())

    def layout_fields(self):
        return ['worktag', 'fund']

    def clean_worktag(self):
        worktag = re.sub(r'\s+', '', self.cleaned_data['worktag']).upper()
        if not WORKTAG_FORMAT.match(worktag):
            raise ValidationError("That is not a worktag. Worktags look like 1234-CC or 123-AG.")
        return worktag

    def save(self, user=None):
        bill = self.bill
        worktag, fund = self.cleaned_data['worktag'], self.cleaned_data['fund']
        if (bill.worktag_charged, bill.fund_charged) != (worktag, fund) or not bill.worktag_entered_on:
            bill.worktag_entered_on = datetime.date.today()
        bill.worktag_charged, bill.fund_charged = worktag, fund
        bill.save(update_fields=['worktag_charged', 'fund_charged', 'worktag_entered_on'])
        return bill


class BillISDForm(BillWorktagForm):
    """
    The Internal Service Delivery created in Workday for a bill: the number
    Workday gave it, the worktag, fund and amount it charges, and the day.

    Saving it moves the bill to *Waiting on approval*, and marks each of its
    events entered into Workday, which locks the client's worktag form as it
    always has once the ISD exists.
    """
    amount = forms.DecimalField(max_digits=8, decimal_places=2, label="Amount charged")
    isd_number = forms.CharField(max_length=20, label="ISD number", help_text="Such as 25090179-ISD.")
    entered_on = forms.DateField(label="Created in Workday on", widget=forms.DateInput(attrs={'type': 'date'}))

    def __init__(self, *args, **kwargs):
        super(BillISDForm, self).__init__(*args, **kwargs)
        bill = self.bill
        if not self.is_bound:
            self.initial.setdefault('amount', money(bill.isd_amount if bill.isd_amount is not None else bill.amount))
            self.initial.setdefault('isd_number', bill.isd_number or '')
            self.initial.setdefault('entered_on', bill.isd_entered_on or datetime.date.today())
        if bill.isd_amount is None:
            self.fields['amount'].help_text = "Filled in: what the client was billed."

    def layout_fields(self):
        return ['isd_number', 'worktag', 'fund', 'amount', 'entered_on']

    def clean_entered_on(self):
        entered_on = self.cleaned_data['entered_on']
        if entered_on > datetime.date.today():
            raise ValidationError("The ISD cannot have been created after today.")
        return entered_on

    def clean_isd_number(self):
        number = normalise_isd_number(self.cleaned_data['isd_number'])
        if not ISD_NUMBER_FORMAT.match(number):
            raise ValidationError("Workday's ISD numbers are digits, then -ISD, such as 25090179-ISD.")
        for model in (Billing, MultiBilling):
            clash = model.objects.filter(isd_number=number)
            if isinstance(self.bill, model):
                clash = clash.exclude(pk=self.bill.pk)
            clash = clash.first()
            if clash is not None:
                raise ValidationError("%s is already recorded on %s." % (
                    number, clash.display_name if isinstance(clash, MultiBilling)
                    else 'the bill for %s' % clash.event.event_name))
        return number

    def save(self, user=None):
        bill = self.bill
        bill.worktag_charged, bill.fund_charged = self.cleaned_data['worktag'], self.cleaned_data['fund']
        bill.isd_number = self.cleaned_data['isd_number']
        bill.isd_amount = self.cleaned_data['amount']
        bill.isd_entered_on = self.cleaned_data['entered_on']
        bill.isd_entered_by = user
        bill.save(update_fields=['worktag_charged', 'fund_charged', 'isd_number', 'isd_amount', 'isd_entered_on',
                                 'isd_entered_by'])
        set_entered_into_workday(self.events, True)
        return bill


def set_entered_into_workday(events, entered):
    """
    Tick, or untick, the events app's "entered into Workday" box on each of
    these events that has one. The client's worktag form stays locked while it
    is ticked.
    """
    for event in events:
        if hasattr(event, 'entered_into_workday') and event.entered_into_workday != entered:
            event.entered_into_workday = entered
            event.save(update_fields=['entered_into_workday'])


def clear_isd(bill, events):
    """
    Take a recorded ISD off a bill -- one entered by mistake, or cancelled in
    Workday -- so it is back at *Create ISD*, and unlock its events' worktag
    form. The worktag stays.
    """
    bill.isd_number = None
    bill.isd_amount = None
    bill.isd_entered_on = None
    bill.isd_entered_by = None
    bill.save(update_fields=['isd_number', 'isd_amount', 'isd_entered_on', 'isd_entered_by'])
    set_entered_into_workday(events, False)


class NoBillNeededForm(forms.ModelForm):
    """
    Why an event reviewed for billing is not being billed. Offered with
    SGA-funded already chosen when the event is marked SGA-funded and comes to
    $0, and saying so; never saved without the Treasurer.
    """

    class Meta:
        model = NoBillNeeded
        fields = ('reason', 'note')
        widgets = {'note': forms.Textarea(attrs={'rows': 3}), 'reason': forms.RadioSelect}

    def __init__(self, *args, suggested=False, **kwargs):
        super(NoBillNeededForm, self).__init__(*args, **kwargs)
        if suggested and not self.is_bound and not self.instance.pk:
            self.initial['reason'] = NoBillNeeded.SGA_FUNDED
            self.fields['reason'].help_text = ("Filled in: the event is marked SGA-funded and has no rentals or "
                                               "one-off charges, so it comes to $0.")
        self.helper = finance_form_helper()
        self.helper.layout = Layout('reason', 'note')

    def clean(self):
        cleaned = super(NoBillNeededForm, self).clean()
        if cleaned.get('reason') == NoBillNeeded.OTHER and not (cleaned.get('note') or '').strip():
            self.add_error('note', "Say why, when the reason is Other.")
        return cleaned


class BillingEmailForm(forms.ModelForm):
    def __init__(self, billing, *args, **kwargs):
        super(BillingEmailForm, self).__init__(*args, **kwargs)
        self.billing = billing
        orgs = billing.event.org.all()
        self.fields["email_to_orgs"].queryset = orgs
        self.fields["email_to_orgs"].initial = orgs
        if billing.event.contact:
            self.fields["email_to_users"].initial = [billing.event.contact.pk]
        self.helper = FormHelper()
        self.helper.form_class = 'form-horizontal'
        self.helper.label_class = 'col-lg-2'
        self.helper.field_class = 'col-lg-10'
        self.helper.layout = Layout(
            HTML('<p class="text-muted">The bill PDF for this event will be attached to the email. The message you '
                 'type below is not the entire contents of the email; a large "PAY NOW" button and identifying '
                 'information about the event being billed will be added to the email below your message.</p>'),
            'subject',
            'message',
            'email_to_users',
            'email_to_orgs',
            FormActions(
                Submit('save', 'Send Email'),
            )
        )

    def clean(self):
        cleaned_data = super(BillingEmailForm, self).clean()
        if not cleaned_data.get('email_to_users', None) and not cleaned_data.get('email_to_orgs', None):
            raise ValidationError('No recipients')
        for user in map(lambda id: get_user_model().objects.get(id=id), cleaned_data.get('email_to_users', [])):
            if not user.email:
                raise ValidationError('User %s has no email address on file' % user.get_full_name())
        for org in cleaned_data.get('email_to_orgs', []):
            if not org.exec_email:
                raise ValidationError('Organization %s has no email address on file' % org.name)
        return cleaned_data

    def save(self, commit=True):
        instance = super(BillingEmailForm, self).save(commit=False)
        instance.billing = self.billing
        if commit:
            instance.save()
            self.save_m2m()
        return instance

    class Meta:
        model = BillingEmail
        fields = ('subject', 'message', 'email_to_users', 'email_to_orgs')

    email_to_users = AutoCompleteSelectMultipleField('Users', required=False, label="User Recipients")
    email_to_orgs = CustomOrganizationEmailModelMultipleChoiceField(
        queryset=Organization.objects.all(),
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'checkbox'}),
        required=False, label="Client Recipients",
        help_text="The email address listed is the client's exec email alias on file."
    )


class MultiBillingEmailForm(forms.ModelForm):
    def __init__(self, multibilling, *args, **kwargs):
        super(MultiBillingEmailForm, self).__init__(*args, **kwargs)
        self.multibilling = multibilling
        orgsets = map(lambda event: event.org.all(), multibilling.events.all())
        orgs = next(iter(orgsets))
        for orgset in orgsets:
            orgs |= orgset
        orgs = orgs.distinct()
        contacts = map(lambda event: event.contact.pk, multibilling.events.filter(contact__isnull=False))
        self.fields["email_to_orgs"].queryset = orgs
        self.fields["email_to_orgs"].initial = multibilling.org
        self.fields["email_to_users"].initial = contacts
        self.helper = FormHelper()
        self.helper.form_class = 'form-horizontal'
        self.helper.label_class = 'col-lg-2'
        self.helper.field_class = 'col-lg-10'
        self.helper.layout = Layout(
            HTML('<p class="text-muted">The bill PDF will be attached to the email.</p>'),
            'subject',
            'message',
            'email_to_users',
            'email_to_orgs',
            FormActions(
                Submit('save', 'Send Email'),
            )
        )

    def clean(self):
        cleaned_data = super(MultiBillingEmailForm, self).clean()
        if not cleaned_data.get('email_to_users', None) and not cleaned_data.get('email_to_orgs', None):
            raise ValidationError('No recipients')
        for user in map(lambda id: get_user_model().objects.get(id=id), cleaned_data.get('email_to_users', [])):
            if not user.email:
                raise ValidationError('User %s has no email address on file' % user.get_full_name())
        for org in cleaned_data.get('email_to_orgs', []):
            if not org.exec_email:
                raise ValidationError('Organization %s has no email address on file' % org.name)
        return cleaned_data

    def save(self, commit=True):
        instance = super(MultiBillingEmailForm, self).save(commit=False)
        instance.multibilling = self.multibilling
        if commit:
            instance.save()
            self.save_m2m()
        return instance

    class Meta:
        model = MultiBillingEmail
        fields = ('subject', 'message', 'email_to_users', 'email_to_orgs')

    email_to_users = AutoCompleteSelectMultipleField('Users', required=False, label="User Recipients")
    email_to_orgs = CustomOrganizationEmailModelMultipleChoiceField(
        queryset=Organization.objects.all(),
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'checkbox'}),
        required=False, label="Client Recipients",
        help_text="The email address listed is the client's exec email alias on file."
    )
