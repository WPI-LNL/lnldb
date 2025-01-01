import logging
from django.conf import settings
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError


logger = logging.getLogger(__name__)


# API Methods
def delete_file(id):
    client = WebClient(token=settings.SLACK_TOKEN)

    response = client.files_delete(file=id)
    return response['ok']


def load_channels(archived=False):
    """
    Get a list of all the public channels in Slack

    :param archived: Boolean - Include archived channels

    :returns: Response object (Dictionary)
    """
    if not settings.SLACK_TOKEN:
        return {'ok': False, 'error': 'config_error'}

    client = WebClient(token=settings.SLACK_TOKEN)

    try:
        response = client.conversations_list(exclude_archived=not archived)
        assert response['ok'] is True

        channels = []
        for channel in response['channels']:
            channels.append((channel['id'], channel['name']))

        return {'ok': True, 'channels': channels}
    except SlackApiError as e:
        assert e.response['ok'] is False
        return e.response


def channel_info(id, num_members=False):
    """
    Retrieves all the information about a channel

    :param id: The ID of the channel
    :return: Channel details (Dictionary)
    """

    if not settings.SLACK_TOKEN:
        return None

    client = WebClient(token=settings.SLACK_TOKEN)

    try:
        response = client.conversations_info(channel=id, include_num_members=num_members)
        assert response['ok'] is True
        return response['channel']
    except SlackApiError as e:
        assert e.response['ok'] is False
        return None
    
def channel_latest_message(id):
    """
    Retrieves the latest message in a channel

    :param id: The ID of the channel
    :return: The message details
    """

    if not settings.SLACK_TOKEN:
        return None

    client = WebClient(token=settings.SLACK_TOKEN)

    try:
        response = client.conversations_history(channel=id, limit=1)
        assert response['ok'] is True
        return float(response['messages'][0])
    except SlackApiError as e:
        assert e.response['ok'] is False
        return None

def channel_member_ids(id):
    """
    Retrieves list of channel members' IDs

    :param id: The ID of the channel
    :return: list of member Slack IDs
    """

    if not settings.SLACK_TOKEN:
        return None

    client = WebClient(token=settings.SLACK_TOKEN)

    try:
        response = client.conversations_members(channel=id)
        assert response['ok'] is True
        if response['response_metadata']['next_cursor']:
            cursor = response['response_metadata']['next_cursor']
            members = response['members']
            while cursor:
                response = client.conversations_members(channel=id, cursor=cursor)
                assert response['ok'] is True
                members += response['members']
                cursor = response['response_metadata']['next_cursor']
            return members
        return response['members']
    except SlackApiError as e:
        assert e.response['ok'] is False
        return None

def channel_members(id):
    """
    Retrieves list of channel members and matches to users in the database

    :param id: The ID of the channel
    :return: list of members
    """

    member_ids = channel_member_ids(id)
    if not member_ids: return None
    
    members = []
    for member_id in member_ids:
        user = user_profile(member_id)
        if user['ok']:
            members.append(user['user']['profile']['email'])
    return members


def join_channel(channel):
    """
    If the app gets the 'not_in_channel' error when accessing a public channel, call this method

    :param channel: The channel to join
    :returns: Response object (Dictionary)
    """
    if not settings.SLACK_TOKEN:
        return {'ok': False, 'error': 'config_error'}

    client = WebClient(token=settings.SLACK_TOKEN)

    try:
        response = client.conversations_join(channel=channel)
        assert response['ok'] is True
        return {'ok': response['ok']}
    except SlackApiError as e:
        assert e.response['ok'] is False
        return e.response


def upload(attachment, filename, title=None, message=None, channels=None):
    """
    Upload a new file to Slack

    :param attachment: File path to the file
    :param filename: Filename with file extension (i.e. example.pdf)
    :param title: Title of the file to display in Slack
    :param message: The message text introducing the file in the specified ``channels``
    :param channels: Comma-separated list of channel names or ids where the file should be posted (i.e. C1234567890)
    :returns: Response object (Dictionary)
    """

    if not settings.SLACK_TOKEN:
        return {'ok': False, 'error': 'config_error'}

    client = WebClient(token=settings.SLACK_TOKEN)
    client.timeout = 600

    try:
        if channels:
            response = client.files_upload(channels=channels, file=attachment, filename=filename,
                                           initial_comment=message, title=title)
        else:
            response = client.files_upload(file=attachment, filename=filename, title=title)
        assert response['ok'] is True
        return {'ok': True, 'file': response['file']}
    except SlackApiError as e:
        assert e.response['ok'] is False
        return e.response


def slack_post(channel, thread=None, text=None, content=None, username=None, icon_url=None, attachment=None):
    """
    Post a message on Slack

    The `text` parameter is not required when the `content` parameter is provided, however including it is still
    highly recommended.

    :param channel: The identifier of the Slack conversation to post to
    :param thread: The timestamp of another message to post this message as a reply to
    :param text: Message text (Formatting: https://api.slack.com/reference/surfaces/formatting)
    :param content: List of valid blocks data (https://api.slack.com/block-kit)
    :param username: Name displayed by the bot
    :param icon_url: The URL to an image / icon to display next to the message (profile picture)
    :param attachment: Dictionary with file details - {'name': 'Example File', 'filepath': '/media/slack/example.pdf'}
    :returns: Response object (Dictionary)
    """

    if not settings.SLACK_TOKEN:
        return {'ok': False, 'error': 'config_error'}

    client = WebClient(token=settings.SLACK_TOKEN)

    if attachment:
        filename = attachment['filepath'].split('/')[-1]
        return upload(attachment['filepath'], filename, attachment['name'], text, channel)

    if content:
        try:
            if username:
                response = client.chat_postMessage(channel=channel, thread_ts=thread, blocks=content, text=text,
                                                   username=username, icon_url=icon_url)
            else:
                response = client.chat_postMessage(channel=channel, thread_ts=thread, blocks=content, text=text)
            assert response['ok'] is True
            return {'ok': True, 'message': response['message']}
        except SlackApiError as e:
            assert e.response['ok'] is False
            return e.response
    elif text:
        try:
            if username:
                response = client.chat_postMessage(channel=channel, thread_ts=thread, text=text, username=username,
                                                   icon_url=icon_url)
            else:
                response = client.chat_postMessage(channel=channel, thread_ts=thread, text=text)
            assert response['ok'] is True
            return {'ok': True, 'message': response['message']}
        except SlackApiError as e:
            assert e.response['ok'] is False
            return e.response
    elif not content and not text:
        return {'ok': False, 'error': 'no_text'}


def post_ephemeral(channel, text, user, username=None):
    """
    Send an ephemeral message to a user in a channel. This message will only be visible to the target user.

    :param channel: The identifier of the Slack conversation to post to
    :param text: Message text (Formatting: https://api.slack.com/reference/surfaces/formatting)
    :param user: The identifier of the specified user
    :param username: Name displayed by the bot
    :return: Response object (Dictionary)
    """

    if not settings.SLACK_TOKEN:
        return {'ok': False, 'error': 'config_error'}

    client = WebClient(token=settings.SLACK_TOKEN)

    try:
        response = client.chat_postEphemeral(channel=channel, text=text, user=user, username=username)
        assert response['ok'] is True
        return response
    except SlackApiError as e:
        assert e.response['ok'] is False
        return e.response


def message_react(channel, message, reaction):
    """
    React to a Slack message

    :param channel: The channel the message was posted to
    :param message: The timestamp of the message
    :param reaction: The name of the emoji to react to the message with
    :return: Response object (Dictionary)
    """

    if not settings.SLACK_TOKEN:
        return {'ok': False, 'error': 'config_error'}

    client = WebClient(token=settings.SLACK_TOKEN)

    try:
        response = client.reactions_add(channel=channel, timestamp=message, name=reaction)
        assert response['ok'] is True
        return response
    except SlackApiError as e:
        assert e.response['ok'] is False
        return e.response


def message_unreact(channel, message, reaction):
    """
    Remove a reaction from a Slack message

    :param channel: The channel the message was posted to
    :param message: The timestamp of the message
    :param reaction: The name of the emoji to remove from the message
    :return: Response object (Dictionary)
    """

    if not settings.SLACK_TOKEN:
        return {'ok': False, 'error': 'config_error'}

    client = WebClient(token=settings.SLACK_TOKEN)

    try:
        response = client.reactions_remove(channel=channel, timestamp=message, name=reaction)
        assert response['ok'] is True
        return response
    except SlackApiError as e:
        assert e.response['ok'] is False
        return e.response


def retrieve_message(channel, message_id):
    """
    Retrieve a single message from Slack

    :param channel: The channel the message was posted to
    :param message_id: The timestamp of the message
    :return: The message details
    """

    if not settings.SLACK_TOKEN:
        return {'ok': False, 'error': 'config_error'}

    client = WebClient(token=settings.SLACK_TOKEN)

    try:
        response = client.conversations_history(channel=channel, latest=message_id, inclusive=True, limit=1)
        assert response['ok'] is True
        return response
    except SlackApiError as e:
        assert e.response['ok'] is False
        return e.response


def replace_message(channel, message_id, text=None, content=None):
    """
    Replace an existing message in Slack. The message will need to have been published by the bot.

    The `text` parameter is not required when the `content` parameter is provided, however including it is still
    highly recommended.

    :param channel: The identifier of the Slack conversation the message was posted to
    :param message_id: The timestamp of the message to be updated
    :param text: Message text (Formatting: https://api.slack.com/reference/surfaces/formatting)
    :param content: List of valid blocks data (https://api.slack.com/block-kit)
    :return: Response object (Dictionary)
    """

    if not settings.SLACK_TOKEN:
        return {'ok': False, 'error': 'config_error'}

    client = WebClient(token=settings.SLACK_TOKEN)

    if content or text:
        try:
            response = client.chat_update(channel=channel, ts=message_id, as_user=True, text=text, blocks=content,
                                          link_names=True)
            assert response['ok'] is True
            return {'ok': True, 'message': response['message']}
        except SlackApiError as e:
            assert e.response['ok'] is False
            return e.response
    else:
        return {'ok': False, 'error': 'no_text'}


def message_link(channel, message_id):
    """
    Get a permalink for a specific message in Slack.

    :param channel: The channel the message was posted in
    :param message_id: The timestamp of the message
    :return: Permalink URL
    """

    if not settings.SLACK_TOKEN:
        return None

    client = WebClient(token=settings.SLACK_TOKEN)

    try:
        response = client.chat_getPermalink(channel=channel, message_ts=message_id)
        assert response['ok'] is True
        return response['permalink']
    except SlackApiError as e:
        assert e.response['ok'] is False
        return None


def user_add(channel, users):
    """
    Invite users to join a slack channel. The bot must be a member of the channel.

    :param channel: The identifier of the Slack channel to invite the users to
    :param users: The identifiers of the specified users (List of up to 1000)
    :return: Response object (Dictionary)
    """

    if not settings.SLACK_TOKEN:
        return {'ok': False, 'error': 'config_error'}

    client = WebClient(token=settings.SLACK_TOKEN)

    try:
        response = client.conversations_invite(channel=channel, users=users)
        assert response['ok'] is True
        return {'ok': response['ok']}
    except SlackApiError as e:
        assert e.response['ok'] is False
        return e.response


def user_kick(channel, user):
    """
    Remove a user from a slack channel. The bot must be a member of the channel.

    :param channel: The identifier of the Slack channel to remove users from
    :param user: The identifier of the specified user
    :return: Response object (Dictionary)
    """

    if not settings.SLACK_TOKEN:
        return {'ok': False, 'error': 'config_error'}

    client = WebClient(token=settings.SLACK_TOKEN)

    try:
        response = client.conversations_kick(channel=channel, user=user)
        assert response['ok'] is True
        return {'ok': response['ok']}
    except SlackApiError as e:
        assert e.response['ok'] is False
        return e.response


def user_profile(user_id):
    """
    Get basic user profile information

    :param user_id: The identifier for the user in Slack (i.e. U123456789)
    :return: Slack user info (Dictionary)
    """

    if not settings.SLACK_TOKEN:
        return {'ok': False, 'error': 'config_error'}

    client = WebClient(token=settings.SLACK_TOKEN)

    try:
        response = client.users_info(user=user_id)
        assert response['ok'] is True
        return response
    except SlackApiError as e:
        assert e.response['ok'] is False
        return e.response


def lookup_user(email):
    """
    Will search for a user in the Slack workspace using their email address

    :param email: The email address for the user
    :return: The identifier for the user in Slack (`None` if the search returns nothing)
    """

    if not settings.SLACK_TOKEN:
        return None

    client = WebClient(token=settings.SLACK_TOKEN)

    try:
        response = client.users_lookupByEmail(email=email)
        assert response['ok'] is True
        return response['user']['id']
    except SlackApiError as e:
        assert e.response['ok'] is False
        return None


def check_presence(user):
    """
    Gets user presence information from Slack ("active" or "away")

    :param user: The identifier of the specified user
    :return: True if user is currently active, False if user is away
    """

    if not settings.SLACK_TOKEN:
        return None

    client = WebClient(token=settings.SLACK_TOKEN)

    try:
        response = client.users_getPresence(user=user)
        assert response['ok'] is True
        if response['presence'] == 'active':
            return True
        else:
            return False
    except SlackApiError as e:
        assert e.response['ok'] is False
        return None


def open_modal(trigger_id, blocks):
    """
    Opens a modal view (in Slack) in response to user action

    :param trigger_id: The trigger id provided by the API during the user's last interaction
    :param blocks: Block configuration (https://api.slack.com/block-kit)
    :return: View ID if successful; None otherwise
    """

    if not settings.SLACK_TOKEN:
        return None

    client = WebClient(token=settings.SLACK_TOKEN)

    try:
        response = client.views_open(trigger_id=trigger_id, view=blocks)
        assert response['ok'] is True
        return response['view']['id']
    except SlackApiError as e:
        assert e.response['ok'] is False
        return None


