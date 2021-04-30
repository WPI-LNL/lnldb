from django.conf import settings
from django.contrib.auth.decorators import permission_required
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError


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


def slack_post(channel, text=None, content=None, username=None, attachment=None):
    """
    Post a message on Slack

    The `text` parameter is not required when the `content` parameter is provided, however including it is still
    highly recommended.

    :param channel: The identifier of the Slack conversation to post to
    :param text: Message text (Formatting: https://api.slack.com/reference/surfaces/formatting)
    :param content: List of valid blocks data (https://api.slack.com/block-kit)
    :param username: Name displayed by the bot
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
                response = client.chat_postMessage(channel=channel, blocks=content, text=text, username=username)
            else:
                response = client.chat_postMessage(channel=channel, blocks=content, text=text)
            assert response['ok'] is True
            return {'ok': True, 'message': response['message']}
        except SlackApiError as e:
            assert e.response['ok'] is False
            return e.response
    elif text:
        try:
            if username:
                response = client.chat_postMessage(channel=channel, text=text, username=username)
            else:
                response = client.chat_postMessage(channel=channel, text=text)
            assert response['ok'] is True
            return {'ok': True, 'message': response['message']}
        except SlackApiError as e:
            assert e.response['ok'] is False
            return e.response
    elif not content and not text:
        return {'ok': False, 'error': 'no_text'}


@permission_required('slack.manage_channel', raise_exception=True)
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


@permission_required('slack.manage_channel', raise_exception=True)
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
