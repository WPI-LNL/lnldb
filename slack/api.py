import json
import logging
from cryptography.fernet import Fernet
from django.conf import settings
from django.shortcuts import reverse
from django.http import HttpResponse, HttpResponseNotFound, HttpResponseServerError, JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import permission_required
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from accounts.models import UserPreferences
from data.decorators import process_in_thread
from rt import api as rt_api
from . import views


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


# Event Handlers
@csrf_exempt
@require_POST
def handle_event(request):
    """
    Event endpoint for the Slack API. Slack will send POST requests here whenever certain events have been triggered.
    """

    payload = json.loads(request.body)
    if payload['type'] == "url_verification":
        return JsonResponse({"challenge": payload['challenge']})
    elif payload['type'] == "event_callback":
        event = payload['event']
        if event['type'] == "team_join":
            slack_post(event['user']['id'], text="Welcome to LNL!", content=views.welcome_message())
        return HttpResponse()
    elif payload['type'] == "app_home_opened":
        load_app_home(payload['user'])
        return HttpResponse()
    return HttpResponse("Not implemented")


@process_in_thread
def load_app_home(user_id):
    """
    Load the App's Home tab.

    :param user_id: The identifier for the user in Slack
    :return: Response object (Dictionary)
    """

    ticket_ids = []
    tickets = []
    user = user_profile(user_id)
    if user['ok']:
        ticket_ids = rt_api.get_tickets_for_user(user['user']['profile']['email'])
    for ticket_id in ticket_ids:
        ticket = rt_api.fetch_ticket(ticket_id)
        if ticket.get('message'):
            continue
        tickets.append(ticket)
    blocks = views.app_home(tickets)

    if not settings.SLACK_TOKEN:
        return {'ok': False, 'error': 'config_error'}

    client = WebClient(token=settings.SLACK_TOKEN)

    try:
        response = client.views_publish(user_id=user_id, view={"type": "home", "blocks": blocks})
        assert response['ok'] is True
        return response
    except SlackApiError as e:
        assert e.response['ok'] is False
        return e.response


# Interaction handlers
@csrf_exempt
@require_POST
def handle_interaction(request):
    """
    Interaction endpoint for the Slack API. Slack will send POST requests here when users interact with a shortcut or
    interactive component.
    """

    payload = json.loads(request.POST['payload'])
    interaction_type = payload.get('type', None)

    # Handle shortcut
    if interaction_type == "shortcut":
        callback_id = payload.get('callback_id', None)
        if callback_id == "tfed":
            blocks = views.tfed_modal()
            modal_id = open_modal(payload.get('trigger_id', None), blocks)
            if modal_id:
                return HttpResponse()
            return HttpResponseServerError("Failed to open modal")

    # Handle modal view submission
    if interaction_type == "view_submission":
        values = payload['view']['state']['values']
        callback_id = payload['view'].get('callback_id', None)

        # TFed ticket submission
        if callback_id == "tfed-modal":
            subject = values['subject']['subject-action']['value']
            description = values['description']['description-action']['value']
            topic = values['rt_topic']['rt_topic-action']['selected_option']['value']
            user_id = payload['user']['id']
            user = user_profile(user_id)
            if user['ok']:
                __create_ticket(user, subject, description, topic)
                return HttpResponse()
            return HttpResponseServerError("Failed to obtain user information")

        # Update TFed ticket
        elif callback_id == "ticket-update-modal":
            ticket_info = payload['view']['blocks'][1]
            owner_id = None
            if ticket_info['type'] != "divider":
                ticket_info = payload['view']['blocks'][2]
                owner_id = values['ticket_assignee']['ticket_assignee-action']['selected_user']
            ticket_id = ticket_info['block_id'].split("#")[0]
            channel = ticket_info['block_id'].split("#")[1]
            ts = ticket_info['block_id'].split("#")[2]
            status = values['ticket_status']['ticket_status-action']['selected_option']
            if status:
                status = status['value']
            comments = values['ticket_comment']['ticket_comment-action']['value']
            checkboxes = values['email_requestor']['email_requestor-action']['selected_options']
            notify_requestor = False
            if len(checkboxes) > 0:
                notify_requestor = True

            # Obtain user's RT token
            user_id = payload['user']['id']
            token = __retrieve_rt_token(user_id)

            __update_ticket(ticket_id, status, owner_id, comments, notify_requestor, token, user_id, channel, ts)
            return HttpResponse()
        return HttpResponseNotFound()

    # Handle block interaction event
    if interaction_type == "block_actions":
        action = payload['actions'][0]['action_id']
        channel = payload.get('channel', None)
        if channel:
            channel = channel['id']
        message = payload.get('message', None)
        view = payload.get('view', None)

        # TFed message
        if channel in [settings.SLACK_TARGET_TFED, settings.SLACK_TARGET_TFED_DB] and message and not view:
            ticket_id = message['blocks'][0]['block_id'].split('~')[0]
            blocks = views.ticket_update_modal(ticket_id, channel, message['ts'], action)

            # Get current ticket from RT
            resp = refresh_ticket_message(channel, message)
            if not resp['ok']:
                logger.warning("Failed to update ticket in Slack. Please check RT to see if your changes were applied.")

            # Check that user has token, if not display a warning
            user_id = payload['user']['id']
            token = __retrieve_rt_token(user_id)
            if not token:
                error_message = "Hi there! Before you can update tickets, you'll need to set up access to your RT " \
                                "account. Visit https://lnl.wpi.edu" + reverse("support:link-account") +  \
                                " to get started."
                post_ephemeral(channel, error_message, user_id, 'Request Tracker')
                return HttpResponse()

            modal_id = open_modal(payload.get('trigger_id', None), blocks)
            if modal_id:
                return HttpResponse()
            return HttpResponseServerError("Failed to open modal")
        return HttpResponse()
    return HttpResponseNotFound()


@process_in_thread
def __create_ticket(user, subject, description, topic):
    """
    Handler for creating a new TFed ticket

    :param user: The user that submitted the ticket
    :param subject: The ticket's subject line
    :param description: The contents of the ticket
    :param topic: The Queue in RT to post the ticket to
    """

    target = settings.SLACK_TARGET_TFED
    if topic == 'Database':
        target = settings.SLACK_TARGET_TFED_DB
    user_email = user['user']['profile'].get('email', 'lnl-no-reply@wpi.edu')
    resp = rt_api.create_ticket(topic, user_email, subject, description)
    ticket_id = resp.get('id', None)
    if ticket_id:
        ticket_info = {
            "url": 'https://lnl-rt.wpi.edu/rt/Ticket/Display.html?id=' + ticket_id,
            "id": ticket_id,
            "subject": subject,
            "description": description,
            "status": "New",
            "assignee": None,
            "reporter": user['user']['name']
        }
        ticket = views.tfed_ticket(ticket_info)
        slack_post(target, text=description, content=ticket, username='Request Tracker')
        return
    error_message = "Whoops! It appears something went wrong while attempting to submit your request. " \
                    "Please wait a few minutes then try again. If the problem persists, please email " \
                    "us directly at tfed@wpi.edu."
    post_ephemeral(target, error_message, user['user']['id'], username="Request Tracker")


@process_in_thread
def __update_ticket(ticket_id, status, owner_id, comments, notify_requestor, token, user_id, channel, ts):
    """
    Handler for updating an existing TFed ticket

    :param ticket_id: The ticket number
    :param status: The new status to assign to the ticket in RT
    :param owner_id: The Slack user ID for the ticket owner (who the ticket will be assigned to)
    :param comments: Comments to add to the ticket history
    :param notify_requestor: If True, the ticket creator will receive an email with the comments
    :param token: The RT auth token for the user that triggered this action
    :param user_id: The Slack user ID for the user that triggered this action
    :param channel: The identifier of the Slack channel this ticket was posted to
    :param ts: The timestamp of the original ticket message in Slack
    """

    # Update ticket metadata
    owner = user_profile(owner_id)
    username = ''
    if owner['ok']:
        username = owner['user']['profile'].get('email', '').split('@')[0]
    resp = rt_api.update_ticket(ticket_id, token, status, username)
    if rt_api.permission_error(resp):
        error_message = "Sorry, it appears you do not have permission to perform this action."
        post_ephemeral(channel, error_message, user_id, 'Request Tracker')
        return

    # Update ticket in Slack
    current_message = retrieve_message(channel, ts)
    if current_message.get('error', '') == 'not_in_channel':
        join_channel(channel)
        current_message = retrieve_message(channel, ts)
    resp = refresh_ticket_message(channel, current_message['messages'][0])
    if not resp['ok']:
        logger.warning("Failed to update ticket in Slack. Please check RT to see if your changes were applied.")

    # Post comments / replies, if applicable
    if comments:
        slack_user = user_profile(user_id)
        display_name = slack_user['user']['profile']['real_name']
        resp = rt_api.ticket_comment(ticket_id, comments + "\n\n- " + display_name, notify_requestor,
                                     token=token)
        if rt_api.permission_error(resp):
            error_message = "Sorry, it appears you do not have permission to perform this action."
            post_ephemeral(channel, error_message, user_id, 'Request Tracker')
            return

        profile_photo = slack_user['user']['profile']['image_original']
        slack_post(channel, ts, comments, username=display_name, icon_url=profile_photo)


def refresh_ticket_message(channel, message):
    """
    Update a TFed ticket message with the latest information

    :param channel: The channel the ticket was posted to
    :param message: The original message object
    :return: Response from Slack API after attempting to update the message
    """

    ticket_id = message['blocks'][0]['block_id'].split('~')[0]
    ticket_reporter = message['blocks'][0]['block_id'].split('~')[1]
    ticket_description = message['blocks'][1]['text']['text']
    ticket = rt_api.fetch_ticket(ticket_id)
    if ticket.get('message'):
        return {"ok": False}
    ticket_owner = ticket['Owner']['id']
    if ticket_owner == "Nobody":
        ticket_owner = None
    ticket_info = {
        "url": 'https://lnl-rt.wpi.edu/rt/Ticket/Display.html?id=' + ticket_id,
        "id": ticket_id,
        "subject": ticket.get('Subject'),
        "description": ticket_description,
        "status": ticket.get('Status').capitalize(),
        "assignee": ticket_owner,
        "reporter": ticket_reporter
    }
    new_message = views.tfed_ticket(ticket_info)
    return replace_message(channel, message['ts'], ticket_description, new_message)


def __retrieve_rt_token(user_id):
    """
    Retrieve a user's RT auth token (if it exists)

    :param user_id: The Slack user's identifier
    :return: Auth token; `None` if it doesn't exist
    """

    slack_user = user_profile(user_id)
    if slack_user['ok']:
        username = slack_user['user']['profile'].get('email', '').split('@')[0]
        user = get_user_model().objects.filter(username=username).first()
        if user:
            prefs = UserPreferences.objects.filter(user=user).first()
            if prefs:
                if prefs.rt_token:
                    cipher_suite = Fernet(settings.RT_CRYPTO_KEY)
                    return cipher_suite.decrypt(prefs.rt_token.encode('utf-8')).decode('utf-8')
    return None
