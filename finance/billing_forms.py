"""
The forms for creating, editing and emailing bills and multi-bills.

They moved here from the events app with the bills themselves, unchanged, so
they still lay themselves out the way the events app's forms do: each renders
its own ``<form>`` and buttons through crispy, inside the site's generic form
templates. That is the opposite of :mod:`finance.forms`, whose templates write
the ``<form>`` themselves, which is why they live in a module of their own.
"""
import datetime

from ajax_select.fields import AutoCompleteSelectMultipleField
from crispy_forms.bootstrap import FormActions, PrependedText
from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Layout, Reset, Submit
from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from events.models import BaseEvent, Organization
from finance.models import Billing, BillingEmail, MultiBilling, MultiBillingEmail


class CustomEventModelMultipleChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, event):
        return '%s—%s' % (event.event_name, ', '.join(map(lambda org: org.name, event.org.all())))


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


class MultiBillingForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        show_nonbulk_events = kwargs.pop('show_nonbulk_events')
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        self.helper.form_method = "post"
        self.helper.form_action = ""
        layout = []
        if show_nonbulk_events:
            layout += [
                HTML(
                    '<a href="?show_nonbulk_events=false">Switch back to showing only events marked for '
                    'semester billing</a>')
            ]
        else:
            layout += [
                HTML('<a href="?show_nonbulk_events=true">Show events not marked for semester billing</a>')
            ]
        layout += [
            'events',
            PrependedText('date_billed', '<i class="glyphicon glyphicon-calendar"></i>', css_class="datepick"),
            PrependedText('amount', '<strong>$</strong>'),
            FormActions(
                Submit('save-and-return', 'Save and Return'),
                Submit('save-and-make-email', 'Save and Make Email'),
                Reset('reset', 'Reset Form'),
            )
        ]
        self.helper.layout = Layout(*layout)
        super(MultiBillingForm, self).__init__(*args, **kwargs)
        if show_nonbulk_events is True:
            self.fields['events'].queryset = BaseEvent.objects.filter(closed=False, reviewed=True,
                                                                      billings__isnull=True) \
                .exclude(multibillings__isnull=False, multibillings__date_paid__isnull=False)
            self.fields['events'].help_text = 'Only unbilled, reviewed events are listed above.'
        self.fields['date_billed'].initial = datetime.date.today()

    def clean(self):
        cleaned_data = super(MultiBillingForm, self).clean()
        events = cleaned_data.get('events', [])
        if events:
            org = events[0].org_to_be_billed
            for event in events[1:]:
                if event.org_to_be_billed != org:
                    raise ValidationError('All events you select must have the same \'Client to bill\'.')
        return cleaned_data

    def save(self, commit=True):
        instance = super(MultiBillingForm, self).save(commit=False)
        instance.org = self.cleaned_data['events'].first().org_to_be_billed
        if commit:
            instance.save()
            self.save_m2m()
        return instance

    class Meta:
        model = MultiBilling
        fields = ('events', 'date_billed', 'amount')

    events = CustomEventModelMultipleChoiceField(
        queryset=BaseEvent.objects.filter(closed=False, reviewed=True, billings__isnull=True, billed_in_bulk=True) \
            .exclude(multibillings__isnull=False, multibillings__date_paid__isnull=False),
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'checkbox'}),
        help_text="Only unbilled, reviewed events that are marked for semester billing are listed above."
    )


class MultiBillingUpdateForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super(MultiBillingUpdateForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        self.helper.form_method = "post"
        self.helper.form_action = ""
        events_str = ', '.join(map(lambda event: event.event_name, self.instance.events.all()))
        self.helper.layout = Layout(
            HTML('<p>Events: ' + events_str + '</p>'),
            PrependedText('date_paid', '<i class="glyphicon glyphicon-calendar"></i>', css_class="datepick"),
            PrependedText('amount', '<strong>$</strong>'),
            FormActions(
                Submit('save', 'Save Changes'),
                Reset('reset', 'Reset Form'),
            )
        )
        self.fields['date_paid'].initial = datetime.date.today()

    class Meta:
        model = MultiBilling
        fields = ('date_paid', 'amount')


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
