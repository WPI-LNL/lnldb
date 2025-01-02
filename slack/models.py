import datetime
from django.db import models
from django.contrib.auth import get_user_model
from .api import channel_info, channel_members, channel_latest_message, user_profile


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
    parent = models.ForeignKey("self", on_delete=models.CASCADE, blank=True, null=True)
    deleted = models.BooleanField(default=False, verbose_name="Remove from workspace",
                                  help_text="Remove from the Slack workspace? This action cannot be undone.")

    class Meta:
        permissions = (
            ('post_officer', 'Post Slack message as an officer'),
            ('post_official', 'Post Slack message as LNL'),
            ('manage_channel', 'Add or remove users from a Slack channel')
        )


class ReportedMessage(models.Model):
    """
    Used when users report problematic Slack messages
    """
    message = models.ForeignKey(SlackMessage, on_delete=models.CASCADE, related_name="reports")
    comments = models.TextField(blank=True, null=True)
    reported_by = models.CharField(max_length=12)
    reported_on = models.DateTimeField(auto_now_add=True)
    resolved = models.BooleanField(default=False)

class Channel(models.Model):
    """
    Used to store Slack channel ID and retrieve common information about Slack channels
    """
    id = models.CharField(max_length=256, unique=True, primary_key=True)

    def __str__(self):
        return self.name
    
    @property
    def name(self) -> str:
        try:
            info = channel_info(self.id)
            if 'name' in info:
                return channel_info(self.id)['name']
        except:
            pass
        return "Unknown ("+str(self.id)+")"
    
    @property
    def private(self) -> bool:
        try:
            info = channel_info(self.id)
            return 'is_private' in info and channel_info(self.id)['is_private']
        except:
            return None
    
    @property
    def archived(self) -> bool:
        try:
            info = channel_info(self.id)
            return 'is_archived' in info and channel_info(self.id)['is_archived']
        except:
            return None
    
    @property
    def num_members(self) -> int:
        try:
            info = channel_info(self.id, num_members=True)
            return info['num_members']
        except:
            return None

    @property
    def members(self) -> list:
        try:
            return channel_members(self.id)
        except:
            return []
    
    @property
    def last_updated(self) -> datetime.datetime:
        try:
            msg = channel_latest_message(self.id)
            return datetime.datetime.fromtimestamp(msg['ts'])
        except:
            return None
    
    @property
    def created_on(self) -> datetime.datetime:
        try:
            info = channel_info(self.id)
            return datetime.datetime.fromtimestamp(info['created'])
        except:
            return None
    
    @property
    def creator(self) -> str:
        try:
            slack_user_id = channel_info(self.id)['creator']
            slack_user = user_profile(slack_user_id)
            if slack_user['ok']:
                username = slack_user['user']['profile'].get('email', '').split('@')[0]
                return get_user_model().objects.filter(username=username).first()
        except:
            return None
    
    @property
    def info(self) -> dict:
        try:
            return channel_info(self.id)
        except:
            return None

    class Meta:
        permissions = ()