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

from events.models import BaseEvent, Organization
from finance.forms import finance_form_helper
from finance.models import (ZERO, Billing, BillingEmail, MultiBilling, MultiBillingCharge, MultiBillingEmail,
                            default_rental_fee_percent)


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
    def __init__(self, event, *args, **kwargs):
        self.event = event
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        self.helper.form_method = "post"
        self.helper.form_action = ""

        self.helper.layout = Layout(
            PrependedText('date_paid', '<i class="glyphicon glyphicon-calendar"></i>', css_class="datepick"),
            PrependedText('amount', '<strong>$</strong>'),
            FormActions(
                Submit('save', 'Save Changes'),
                Reset('reset', 'Reset Form'),
            )
        )
        super(BillingUpdateForm, self).__init__(*args, **kwargs)

        self.fields['amount'].initial = str(event.cost_total)
        self.fields['date_paid'].initial = datetime.date.today()

    def save(self, commit=True):
        obj = super(BillingUpdateForm, self).save(commit=False)
        obj.event = self.event
        if commit:
            obj.save()
        return obj

    class Meta:
        model = Billing
        fields = ('date_paid', 'amount')


def billable_events(bill=None, include_unmarked=False):
    """
    The events a multi-bill may cover, earliest first.

    Reviewed, still open, with no bill of their own, and on no other
    multi-bill: an event on two bills would be billed twice. Only events
    marked to be billed in bulk unless ``include_unmarked``. The events
    already on ``bill`` are always offered, so editing it can keep them.
    """
    others = MultiBilling.objects.all()
    if bill is not None and bill.pk:
        others = others.exclude(pk=bill.pk)
    events = (BaseEvent.objects.filter(closed=False, reviewed=True, billings__isnull=True)
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
        # bill -- which were confirmed when it was made, so the box starts ticked.
        self.clients = self._submitted_clients()
        fields = ['events', 'org']
        if len(self.clients) > 1:
            self.fields['confirm_mixed_clients'].label = "Bill these together: they are for %s" % ', '.join(
                '%s (%s event%s)' % (org.retname, count, '' if count == 1 else 's') for org, count in self.clients)
            self.fields['confirm_mixed_clients'].initial = not self.is_bound
            fields.append('confirm_mixed_clients')
        self.helper = finance_form_helper()
        self.helper.layout = Layout(*(fields + ['name', 'description', 'date_billed', 'attach_event_invoices']))

    def _submitted_clients(self):
        """
        The client tally of the events in the submitted data, before it is
        validated -- or, on a form not yet submitted, of the bill's own events.
        """
        if not self.is_bound:
            return client_tally(self.instance.events.all()) if self.instance.pk else []
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


class MultiBillPaidForm(forms.Form):
    """ When a multi-bill was paid, and how, if it was not through Workday. """
    date_paid = forms.DateField(label="Paid on", widget=forms.DateInput(attrs={'type': 'date'}))
    paid_note = forms.CharField(required=False, max_length=200, label="Note",
                                help_text="How it was paid, if not through Workday: cash, a check.")

    def __init__(self, *args, **kwargs):
        super(MultiBillPaidForm, self).__init__(*args, **kwargs)
        self.helper = finance_form_helper()


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
