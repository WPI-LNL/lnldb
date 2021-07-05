from django import forms
from multiupload.fields import MultiFileField


class TicketSubmissionForm(forms.Form):
    subject = forms.CharField(max_length=100)
    description = forms.CharField(widget=forms.Textarea, label="Please describe your problem or request in detail.")
    attachments = MultiFileField(max_file_size=1024 * 1024 * 20, required=False)  # 20 MB limit

    class Meta:
        layout = [
            ("Field", "subject"),
            ("Field", "description"),
            ("Field", "attachments")
        ]
