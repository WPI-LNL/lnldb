import json
import logging
from cryptography.fernet import Fernet
from django.conf import settings
from django.shortcuts import reverse
from django.db import connection
from django.http import HttpResponse, HttpResponseNotFound, HttpResponseServerError, JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from accounts.models import UserPreferences
from data.decorators import process_in_thread
from rt import api as rt_api
from slack.api import slack_post, user_profile, open_modal, post_ephemeral, retrieve_message, replace_message, \
    channel_info, join_channel, message_react

from .models import Channel, SlackMessage, ReportedMessage
from . import views

logger = logging.getLogger(__name__)


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
        elif event['type'] == "app_home_opened":
            load_app_home(event['user'])
        elif event['type'] == "channel_created":
            if settings.SLACK_AUTO_JOIN:
                join_channel(event['channel']['id'])
            channel = Channel.objects.create(id=event['channel']['id'])
            if event['channel']['name'].startswith("active"):
                channel.required_groups.add(*Group.objects.filter(name__in=["Active", "Officer"]))
            # if event['channel']['name'].startswith("exec"): # Need to remove advisor from "Officers" before enabling
            #     channel.required_groups.add(*Group.objects.filter(name="Officer"))
            if event['channel']['name'].startswith("ext"):
                channel.allowed_groups.add(*Group.objects.filter(name__in=["Officer"]))
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
        email = user['user']['profile']['email']
        ticket_ids = sorted(rt_api.simple_ticket_search(requestor=email, status="__Active__"), reverse=True)
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
    if interaction_type == "message_action":
        callback_id = payload.get('callback_id', None)
        if callback_id == "report":
            channel = payload.get('channel', {'id': None})['id']
            sender = payload['message'].get('user', None)
            if not sender:
                sender = payload['message']['username']
            ts = payload['message']['ts']
            text = payload['message']['text']
            message, created = SlackMessage.objects.get_or_create(posted_to=channel, posted_by=sender, ts=ts,
                                                                         content=text)
            blocks = views.report_message_modal(message)
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
        elif callback_id == "ticket-comment-modal":
            ticket_id = payload['view']['blocks'][0]['block_id']
            comments = values[ticket_id]['comment-action']['value']
            user_id = payload['user']['id']
            token = __retrieve_rt_token(user_id)
            __post_ticket_comment(ticket_id, user_id, comments, token)
            return HttpResponse()
        elif callback_id == "report-modal":
            message_id = payload['view']['blocks'][0]['block_id']
            comments = values['report-comment']['comment-action']['value']
            reporter = payload['user']['id']
            __save_report(message_id, reporter, comments)
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
            __refresh_ticket_async(channel, message)

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

        # Home tab menu options
        if action == "home-ticket-update":
            ticket_id = payload['actions'][0]['block_id']
            option = payload['actions'][0]['selected_option']['value']
            if option == 'Comment':
                blocks = views.ticket_comment_modal(ticket_id)
                modal_id = open_modal(payload.get('trigger_id', None), blocks)
                if not modal_id:
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
    display_name = user['user']['profile']['real_name']
    resp = rt_api.create_ticket(topic, user_email, subject, description + "\n\n- " + display_name)
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


@process_in_thread
def __post_ticket_comment(ticket_id, user_id, comments, token):
    """
    Comment on a TFed ticket (background process).

    :param ticket_id: The ticket number
    :param user_id: The Slack user ID for the user that triggered the action
    :param comments: The comments to be added to the ticket
    :param token: The RT auth token for the user that triggered the action (if applicable)
    """

    user = user_profile(user_id)
    display_name = user['user']['profile']['real_name']
    rt_api.ticket_comment(ticket_id, comments + "\n\n- " + display_name, True, token=token)


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


@process_in_thread
def __refresh_ticket_async(channel, message):
    """
    Update a TFed ticket message with the latest information in the background

    :param channel: The channel the ticket was posted to
    :param message: The original message object
    :return: Response from Slack API after attempting to update the message
    """

    resp = refresh_ticket_message(channel, message)
    if not resp['ok']:
        logger.warning("Failed to update ticket in Slack. Please check RT to see if your changes were applied.")


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
                    cipher_suite = Fernet(settings.CRYPTO_KEY)
                    return cipher_suite.decrypt(prefs.rt_token.encode('utf-8')).decode('utf-8')
    return None


@process_in_thread
def __save_report(message_id, reporter, comments):
    """
    Create a report when a user reports a problematic Slack message

    :param message_id: The primary key value of the corresponding SlackMessage object
    :param reporter: Slack user ID for the user that reported the message
    :param comments: Optional comments for the report
    """

    message = SlackMessage.objects.get(pk=message_id)

    # Ensure message was posted to public channel. For privacy reasons, we currently do not report private messages.
    channel_details = channel_info(message.posted_to)
    if channel_details['is_channel'] and not channel_details['is_private']:
        report = ReportedMessage.objects.create(message=message, comments=comments, reported_by=reporter)

        # Send Exec a notification
        blocks = views.reported_message_notification(reporter, report)
        slack_post(settings.SLACK_TARGET_EXEC, text="You have a new flagged message to review", content=blocks,
                   username="Admin Console")

        # Add red flag to message (to inform sender their message has been reported)
        # message_react(message.posted_to, message.ts, 'triangular_flag_on_post')
    else:
        message.public = False
        message.save()

        post_ephemeral(message.posted_to, "This feature currently does not support reporting private messages. Please "
                                          "contact a member of the executive board directly.", reporter)
    connection.close()
