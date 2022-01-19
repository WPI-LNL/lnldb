from django import forms
from multiupload.fields import MultiFileField


class TicketSubmissionForm(forms.Form):
    subject = forms.CharField(max_length=100)
    description = forms.CharField(widget=forms.Textarea, label="Please describe your problem or request in detail.")
    attachments = MultiFileField(max_file_size=1024 * 1024 * 20, required=False)  # 20 MB limit

    class Meta:
        layout = [
            ("Text", "<span style='color: grey'><em>Your name and contact information will automatically be shared "
                     "with our support team when you submit this form.</em></span><br><br>"),
            ("Field", "subject"),
            ("Field", "description"),
            ("Field", "attachments")
        ]


class AuthTokenForm(forms.Form):
    token = forms.CharField()

    class Meta:
        layout = [
            ("Text", "To continue, you'll need to create an Auth Token in RT. For instructions on how to do this, "
                     "<a href='https://lnldb.readthedocs.io/en/latest/help/accounts/linking-rt.html'>click here</a>.<br><br>"),
            ("Field", "token")
        ]
