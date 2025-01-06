import datetime
import re
from django.db import models
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.forms import ValidationError
from django.dispatch import receiver
from django.db.models.signals import pre_save

from lnldb import settings
from django.forms import ValidationError
from .api import channel_info, channel_members, channel_latest_message, get_id_from_name, lookup_user, user_add, user_profile

SLACK_CHANNEL_ID_REGEX = r'/(C0\w+)'


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
    allowed_groups = models.ManyToManyField(
        Group,
        verbose_name="Allowed Groups",
        related_name="allowed_channels",
        blank=True,
    )
    required_groups = models.ManyToManyField(
        Group,
        verbose_name="Required Groups",
        related_name="required_channels",
        blank=True,
    )

    def __str__(self):
        return self.name
    
    @staticmethod
    def get_or_create(channel_id):
        if type(channel_id) == Channel:
            return channel_id
        if (match := re.search(SLACK_CHANNEL_ID_REGEX, channel_id)):
            channel_id = match.group(1)
        try:
            return Channel.objects.get(id=channel_id)
        except Channel.DoesNotExist:
            if True: #validate_channel(channel_id): #TODO: Test validation logic
                return Channel.objects.create(id=channel_id)
            elif (channel_id := get_id_from_name(channel_id.removeprefix("#"))):
                return Channel.get_or_create(channel_id)
            else:
                return None
    
    @staticmethod
    def validate_field(value):
        pass
        # if not Channel.get_or_create(value): # TODO: Test channel validation
        #     raise ValidationError("Invalid channel ID")
    
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
            return ""
    
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
            return ""
    
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
    
    @property
    def link(self) -> str:
        return settings.SLACK_BASE_URL+"/archives/"+self.id+"/"
    
    def add_ccs_to_channel(self) -> bool:
        '''
        Adds all crew chiefs for events in this channel to the channel
        
        :return: True if successful, False if not
        '''
        for event in self.event.all():
            slack_ids = [lookup_user(cci.crew_chief) for cci in event.ccinstances.all()]
            response = user_add(self.id, slack_ids)
            if not response['ok']:
                # raise Exception(response) # TODO: Add exception catching for Slack channel member updates
                pass
        return True

    class Meta:
        permissions = ()

@receiver(pre_save, sender=Channel)
def update_channel_members_on_save(sender, instance:Channel, *args, **kwargs):
    try:
        channel = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        pass # Object is new
    else:
        if not channel.required_groups == instance.required_groups:
            for group in instance.required_groups.all().exclude(pk__in=channel.required_groups.all()):
                usernames = group.user_set.all().values_list('username', flat=True)
                response = user_add(channel.id, usernames)
                if not response['ok']:
                    # raise Exception(response) # TODO: Add exception catching for Slack channel member updates
                    pass
        super().save(*args, **kwargs)