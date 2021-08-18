from django.db import models


# Create your models here.
class SlackMessage(models.Model):
    """
    Used for archiving slack messages
    """
    posted_to = models.CharField(max_length=128)
    posted_by = models.CharField(max_length=24)
    content = models.TextField()
    blocks = models.BooleanField(default=False)
    ts = models.CharField(max_length=24, verbose_name="Timestamp")
    public = models.BooleanField(default=True)
    parent = models.ForeignKey("self", on_delete=models.CASCADE, blank=True)
    deleted = models.BooleanField(default=False, verbose_name="Remove from workspace",
                                  help_text="Remove from the Slack workspace? This action cannot be undone.")

    class Meta:
        permissions = (
            ('post_officer', 'Post Slack message as an officer'),
            ('post_official', 'Post Slack message as LNL'),
            ('manage_channel', 'Add or remove users from a Slack channel')
        )
