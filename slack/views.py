from ajax_select.fields import AutoCompleteSelectMultipleField
from django import forms
from django.db.models import Value
from django.contrib.auth.decorators import permission_required, login_required
from django.shortcuts import reverse, render, get_object_or_404
from django.http import HttpResponseRedirect

from events.models import BaseEvent, Organization
from lnldb import settings

from .models import Channel, ReportedMessage
from .api import lookup_user, user_add, user_profile, message_link, channel_info


# Slack Management Views

@login_required
@permission_required('slack.view_channel', raise_exception=True)
def channel_list(request):
    """
    View a list of all Slack channels
    """
    return render(request, 'slack/slack_channel_list.html', 
                  {'h2': 'Slack Channels', 
                   'channels': Channel.objects.all()})

class ChannelAssignGroupForm(forms.ModelForm):
    allowed_groups = AutoCompleteSelectMultipleField('Groups', required=False)
    required_groups = AutoCompleteSelectMultipleField('Groups', required=False)
    event = AutoCompleteSelectMultipleField('Events', required=False)
    organization = AutoCompleteSelectMultipleField('Orgs', required=False)

    def __init__(self, *args, **kwargs):
        super(ChannelAssignGroupForm, self).__init__(*args, **kwargs)
        self.fields['allowed_groups'].initial = kwargs['instance'].allowed_groups.all()
        self.fields['required_groups'].initial = kwargs['instance'].required_groups.all()
        self.fields['event'].initial = kwargs['instance'].event.all()
        self.fields['organization'].initial = kwargs['instance'].organization.all()

    class Meta:
        model = Channel
        fields = ('allowed_groups', 'required_groups', 'event', 'organization')

@login_required
@permission_required('slack.change_channel', raise_exception=True)
def channel_detail_edit(request, id):
    return channel_detail(request, id, edit=True)

@login_required
@permission_required('slack.view_channel', raise_exception=True)
def channel_detail(request, id, edit=False):
    """
    View details for a specific Slack channel
    """
    channel = get_object_or_404(Channel, id=id)
    if request.method == 'POST':
        form = ChannelAssignGroupForm(data=request.POST, instance=channel)
        if form.is_valid():
            form.save(commit=True)
            for event in ( (event_set := BaseEvent.objects.filter(pk__in=form.cleaned_data['event'])) | channel.event.all() ).distinct():
                event.slack_channel = channel if event in event_set else None
                event.save()
            for org in ( (org_set := Organization.objects.filter(pk__in=form.cleaned_data['organization'])) | channel.organization.all() ).distinct():
                org.slack_channel = channel if org in org_set else None
                org.save()
            return HttpResponseRedirect(reverse('slack:channel', args=[id]))
    return render(request, 'slack/slack_channel_detail.html', 
                  {'h2': "#"+channel.name+' Details', 
                   'channel': channel,
                   #'creator_name': channel.creator.get_full_name() if channel.creator else None,
                   'form': ChannelAssignGroupForm(instance=channel) if edit else None})

@login_required
@permission_required('slack.view_channel', raise_exception=True)
def channel_directory(request, error=None):
    """
    View a directory of all Slack channels
    """
    channels = ( Channel.objects.filter(allowed_groups__in=request.user.groups.all()).annotate(order=Value(1)) | 
                 Channel.objects.filter(required_groups__in=request.user.groups.all()).annotate(order=Value(2)) ).distinct().order_by('order')
    return render(request, 'slack/slack_channel_directory.html', {'h2': 'Slack Channel Directory', 'channels': channels, 'error': error})

@login_required
@permission_required('slack.view_channel', raise_exception=True)
def channel_join_and_redirect(request, id):
    """
    Join a Slack channel and redirect to the Slack workspace
    """
    channel = get_object_or_404(Channel, id=id)
    if channel not in (channels := ( Channel.objects.filter(allowed_groups__in=request.user.groups.all()) | 
                                     Channel.objects.filter(required_groups__in=request.user.groups.all()) ).distinct()):
        return channel_directory(request, error='You do not have permission to join %s' % channel.name)
    else:
        response = user_add(channel.id, request.user.username)
        if response['ok']:
            return HttpResponseRedirect(channel.link)
        else:
            return channel_directory(request, error="Error joining #%s: %s" % (channel.name, response['error']))

@login_required
@permission_required('slack.view_reportedmessage', raise_exception=True)
def report_list(request):
    """
    View Slack messages reported for moderation
    """

    reports = ReportedMessage.objects.filter(resolved=False)
    if request.method == 'POST':
        report_id = request.POST['report_id']
        report = ReportedMessage.objects.get(pk=report_id)
        report.resolved = True
        report.save()
        # message_unreact(report.message.posted_to, report.message.ts, 'triangular_flag_on_post')
        return HttpResponseRedirect(reverse('slack:moderate'))

    return render(request, 'slack/slack_message_list.html', {'title': 'Reported Messages', 'reports': reports})


@login_required
@permission_required('slack.view_reportedmessage', raise_exception=True)
def view_report(request, pk):
    """
    View full report for a Slack message that has been flagged for moderation
    """

    report = get_object_or_404(ReportedMessage, pk=pk)

    if request.method == 'POST':
        report.resolved = True
        report.save()
        # message_unreact(report.message.posted_to, report.message.ts, 'triangular_flag_on_post')
        return HttpResponseRedirect(reverse('slack:moderate'))

    posted_to = report.message.posted_to
    info = channel_info(posted_to)
    if info:
        posted_to = '#' + info['name']

    slack_message = report.message.content
    if report.message.blocks:
        slack_message = "<a href='https://wpilnl.slack.com/app_redirect?channel=" + \
                        report.message.posted_to + "'>Click here to view message</a>"

    context = {
        'posted_by': report.message.posted_by,
        'posted_to': posted_to,
        'report': report,
        'reported_by': report.reported_by,
        'message': slack_message
    }

    return render(request, 'slack/slack_message_report.html', context)


# Block Kit Views
def generate_modal(title, callback_id, blocks):
    """
    Generate a modal view object using Slack's BlockKit

    :param title: Title to display at the top of the modal view
    :param callback_id: Identifier used to help determine the type of modal view in future responses
    :param blocks: Blocks to add to the modal view
    :return: View object (Dictionary)
    """

    modal = {
        "type": "modal",
        "callback_id": callback_id,
        "title": {
            "type": "plain_text",
            "text": title,
            "emoji": False
        },
        "submit": {
            "type": "plain_text",
            "text": "Submit",
            "emoji": False
        },
        "close": {
            "type": "plain_text",
            "text": "Cancel",
            "emoji": False
        },
        "blocks": blocks
    }
    return modal


def tfed_modal():
    """
    Blocks for the TFed ticket submission form.
    Generated using the Block Kit Builder (https://app.slack.com/block-kit-builder)
    """

    blocks = [
        {
            "type": "input",
            "block_id": "subject",
            "element": {
                "type": "plain_text_input",
                "action_id": "subject-action",
                "placeholder": {
                    "type": "plain_text",
                    "text": "Short Summary",
                    "emoji": False
                },
                "max_length": 100
            },
            "label": {
                "type": "plain_text",
                "text": "Subject",
                "emoji": False
            }
        },
        {
            "type": "input",
            "block_id": "description",
            "element": {
                "type": "plain_text_input",
                "action_id": "description-action",
                "placeholder": {
                    "type": "plain_text",
                    "text": "What can we help you with today?",
                    "emoji": False
                },
                "multiline": True
            },
            "label": {
                "type": "plain_text",
                "text": "Please describe your problem or request, in detail",
                "emoji": False
            }
        },
        {
            "type": "input",
            "block_id": "rt_topic",
            "element": {
                "type": "static_select",
                "placeholder": {
                    "type": "plain_text",
                    "text": "Select",
                    "emoji": False
                },
                "options": [
                    {
                        "text": {
                            "type": "plain_text",
                            "text": "Web Services",
                            "emoji": False
                        },
                        "value": "Database"
                    },
                    {
                        "text": {
                            "type": "plain_text",
                            "text": "Equipment Repairs",
                            "emoji": False
                        },
                        "value": "Repairs"
                    }
                ],
                "action_id": "rt_topic-action"
            },
            "label": {
                "type": "plain_text",
                "text": "Topic",
                "emoji": False
            }
        }
    ]
    return generate_modal('New TFed Ticket', 'tfed-modal', blocks)


def tfed_ticket(ticket):
    """
    Generate blocks for TFed ticket response message.
    Generated using the Block Kit Builder (https://app.slack.com/block-kit-builder)
    """

    ticket_assignee = 'Nobody'
    if ticket.get('assignee', None):
        ticket_assignee = '@' + ticket['assignee']
    blocks = [
        {
            "type": "section",
            "block_id": ticket['id'] + '~' + ticket['reporter'],
            "text": {
                "type": "mrkdwn",
                "text": "\n*<" + ticket['url'] + "|Ticket #" + ticket['id'] + ": " + ticket['subject'] + ">*"
            }
        },
        {
            "type": "section",
            "text": {
                "type": "plain_text",
                "text": ticket['description'],
                "emoji": False
            }
        },
        {
            "type": "divider"
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "*Status* » " + ticket['status'] + "\n*Assignee* » " + ticket_assignee +
                            "\n*Reporter* » @" + ticket['reporter']
                }
            ]
        },
        {
            "type": "actions",
            "block_id": "ticket-actions",
            "elements": []
        }
    ]

    ticket_status = ticket['status']

    if ticket_status == "New":
        blocks[4]['elements'].append(generate_button("Open Ticket", "open", "primary", action_suffix="ticket"))
    elif ticket_status not in ["Resolved", "Deleted", "Rejected"]:
        blocks[4]['elements'].append(generate_button("Update Ticket", "update", action_suffix="ticket"))
        blocks[4]['elements'].append(generate_button("Close Ticket", "close", "danger", action_suffix="ticket"))
    else:
        del blocks[4]
    return blocks


def generate_button(text, value, style="default", emoji=False, action_suffix="action"):
    """
    Generate a Block Kit button

    :param text: The button text
    :param style: Style of button (Must be "default", "primary", or "danger")
    :param value: Button value
    :param emoji: Boolean indicating whether or not to permit emoji in the button text
    :param action_suffix: Defaults to "action". Will be appended to `value` to create ``action_id``
    :return: Button block dictionary
    """
    button = {
        "type": "button",
        "text": {
            "type": "plain_text",
            "text": text,
            "emoji": emoji
        },
        "value": value,
        "action_id": value + "-" + action_suffix
    }
    if style != "default":
        button['style'] = style
    return button


def ticket_update_modal(ticket_id, channel, timestamp, action):
    """
    Blocks for the TFed ticket update form.
    Generated using the Block Kit Builder (https://app.slack.com/block-kit-builder)

    :param ticket_id: The ticket # for the ticket being updated
    :param channel: The channel the ticket is being updated from
    :param timestamp: The timestamp of the message that triggered this action
    :param action: The type of update operation (Options: 'open', 'update', 'close')
    """

    blocks = [
        {
            "type": "section",
            "block_id": "ticket_status",
            "text": {
                "type": "mrkdwn",
                "text": "*Ticket Status*:"
            },
            "accessory": {
                "type": "static_select",
                "placeholder": {
                    "type": "plain_text",
                    "text": "Select an item",
                    "emoji": False
                },
                "options": [
                    {
                        "text": {
                            "type": "plain_text",
                            "text": "New",
                            "emoji": False
                        },
                        "value": "new"
                    },
                    {
                        "text": {
                            "type": "plain_text",
                            "text": "Open",
                            "emoji": False
                        },
                        "value": "open"
                    },
                    {
                        "text": {
                            "type": "plain_text",
                            "text": "Stall",
                            "emoji": False
                        },
                        "value": "stalled"
                    },
                    {
                        "text": {
                            "type": "plain_text",
                            "text": "Resolve",
                            "emoji": False
                        },
                        "value": "resolved"
                    },
                    {
                        "text": {
                            "type": "plain_text",
                            "text": "Reject",
                            "emoji": False
                        },
                        "value": "rejected"
                    },
                ],
                "initial_option": {
                    "text": {
                        "type": "plain_text",
                        "text": "Open",
                        "emoji": False
                    },
                    "value": "open"
                },
                "action_id": "ticket_status-action"
            }
        },
        {
            "type": "section",
            "block_id": "ticket_assignee",
            "text": {
                "type": "mrkdwn",
                "text": "*Assignee*:"
            },
            "accessory": {
                "type": "users_select",
                "placeholder": {
                    "type": "plain_text",
                    "text": "Select a user",
                    "emoji": False
                },
                "action_id": "ticket_assignee-action"
            },
        },
        {
            "type": "divider",
            "block_id": ticket_id + "#" + channel + "#" + timestamp,
        },
        {
            "type": "input",
            "block_id": "ticket_comment",
            "element": {
                "type": "plain_text_input",
                "action_id": "ticket_comment-action",
                "multiline": True
            },
            "label": {
                "type": "plain_text",
                "text": "Comments",
                "emoji": False
            },
            "optional": True
        },
        {
            "type": "actions",
            "block_id": "email_requestor",
            "elements": [
                {
                    "type": "checkboxes",
                    "options": [
                        {
                            "text": {
                                "type": "plain_text",
                                "text": "Send to requestor",
                                "emoji": False
                            },
                            "value": "send-email"
                        }
                    ],
                    "action_id": "email_requestor-action"
                }
            ]
        }
    ]
    if action == "open-ticket":
        del blocks[0]["accessory"]["options"][0]
    elif action == "update-ticket":
        del blocks[0]["accessory"]["initial_option"]
    else:
        del blocks[1]
        blocks[0]["accessory"]["initial_option"]["text"]["text"] = "Resolve"
        blocks[0]["accessory"]["initial_option"]["value"] = "resolved"
    return generate_modal("Update Ticket", "ticket-update-modal", blocks)


def welcome_message():
    """
    Blocks for the Welcome Message. This message will be displayed to new users joining the Slack workspace.
    Generated using the Block Kit Builder (https://app.slack.com/block-kit-builder)
    """

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "Welcome to the LNL Slack!",
                "emoji": False
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "We use Slack pretty heavily to communicate with one another (typically for more informal "
                        "communications). Here are some helpful tips and reminders to help you get started:"
            }
        },
        {
            "type": "divider"
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Default Channels*\n\n• #general - Used to announce general *LNL-related* information to the "
                        "entire club.\n\n• #random - If you would like to share anything that is not directly relevant "
                        "to our normal business, post it here.\n\n• #work-announcements - This is, as you may have "
                        "guessed, where we post work announcements for setups and strikes."
            }
        },
        {
            "type": "divider"
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Tips and Tricks*\n\n>*Please use threads when replying to messages!* This helps us keep the "
                        "number of notifications we all receive to a respectable level.\n\n>You can mention particular "
                        "users in your messages to get their attention. For instance, you could mention @lnl to notify "
                        "the LNL Laptop.\n\n>If your message is really important, you can get the attention of "
                        "everyone in a channel using @channel; however when possible, we recommend using @here instead."
            }
        },
        {
            "type": "divider"
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Need Help?",
                        "emoji": False
                    },
                    "style": "primary",
                    "url": "https://lnl.wpi.edu/help",
                    "action_id": "welcome-help"
                }
            ]
        }
    ]
    return blocks


def app_home(tickets):
    """
    Blocks for the App's Home tab.
    Generated using the Block Kit Builder (https://app.slack.com/block-kit-builder)

    :param tickets: A list of ticket ids
    """

    title = "*My Recent Tickets*"
    if len(tickets) == 0:
        title = "*You haven't submitted any tickets yet*"
    blocks = [
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": title
                }
            ]
        },
        {
            "type": "divider"
        }
    ]

    for ticket in tickets:
        blocks.append(
            {
                "type": "section",
                "block_id": str(ticket['id']),
                "text": {
                    "type": "mrkdwn",
                    "text": "\n*Ticket #" + str(ticket['id']) + ": " + ticket['Subject'] + "*\nStatus » " +
                            ticket['Status'].capitalize()
                },
                "accessory": {
                    "type": "overflow",
                    "options": [
                        {
                            "text": {
                                "type": "plain_text",
                                "text": "Comment",
                                "emoji": False
                            },
                            "value": "Comment"
                        }
                    ],
                    "action_id": "home-ticket-update"
                }
            }
        )
        blocks.append({"type": "divider"})

    return blocks


def ticket_comment_modal(ticket_id):
    """
    Blocks for the TFed ticket comment modal. Can be launched in the App Home tab.
    Generated using the Block Kit Builder (https://app.slack.com/block-kit-builder)
    """

    blocks = [
        {
            "type": "input",
            "block_id": str(ticket_id),
            "element": {
                "type": "plain_text_input",
                "action_id": "comment-action",
                "multiline": True
            },
            "label": {
                "type": "plain_text",
                "text": "Comment on this ticket",
                "emoji": False
            }
        }
    ]

    return generate_modal("Comments", "ticket-comment-modal", blocks)


def report_message_modal(message):
    """
    Blocks for the modal view that is displayed when a user reports a problematic Slack message.
    Generated using the Block Kit Builder (https://app.slack.com/block-kit-builder)

    :param message: A SlackMessage object representing the message
    """

    blocks = [
        {
            "type": "section",
            "block_id": str(message.pk),
            "text": {
                "type": "plain_text",
                "text": "This message will be flagged and sent to a moderator for review.",
                "emoji": False
            }
        },
        {
            "type": "input",
            "block_id": "report-comment",
            "element": {
                "type": "plain_text_input",
                "multiline": True,
                "action_id": "comment-action"
            },
            "label": {
                "type": "plain_text",
                "text": "Comments",
                "emoji": False
            },
            "optional": True
        }
    ]

    return generate_modal('Report a message', 'report-modal', blocks)


def reported_message_notification(sender, report):
    """
    Blocks for the notification sent to the Webmaster whenever a new report is submitted.
    Generated using the Block Kit Builder (https://app.slack.com/block-kit-builder)

    :param sender: The Slack ID for the user that sent the report
    :param report: The corresponding ReportedMessage object
    """

    reporter = "Someone"
    slack_user = user_profile(sender)
    if slack_user['ok']:
        reporter = "@" + slack_user['user']['name']

    link = message_link(report.message.posted_to, report.message.ts)

    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "%s has flagged a new message for review by a moderator." % reporter
            }
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": ":slack:  View in Slack",
                        "emoji": True
                    },
                    "style": "primary",
                    "url": link,
                    "action_id": "reported-message-slack"
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "View Report",
                        "emoji": False
                    },
                    "url": "https://lnl.wpi.edu" + reverse("slack:report", args=[report.pk]),
                    "action_id": "reported-message-report"
                }
            ]
        }
    ]

    if not link:
        del blocks[1]['elements'][0]

    return blocks


def cc_add_notification(cci):
    """
    Blocks for a Crew Chief add notification.
    Generated using the Block Kit Builder (https://app.slack.com/block-kit-builder)

    :param cci: EventCCInstance object
    """

    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "You've been added as a crew chief to the event *%s*. Your setup is currently scheduled for "
                        "*%s* in the *%s*." % (cci.event.event_name, cci.setup_start.strftime('%b %-d, %Y at %-I:%M %p'),
                                               cci.setup_location.name.strip())
            }
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Event Details",
                        "emoji": False
                    },
                    "style": "primary",
                    "url": "https://lnl.wpi.edu" + reverse("events:detail", args=[cci.event.pk]),
                    "action_id": "cc-add-%s" % cci.event.pk
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": ":calendar:  Add to calendar",
                        "emoji": True
                    },
                    "url": "https://lnl.wpi.edu" + reverse("events:ics", args=[cci.event.pk]),
                    "action_id": "ics-download-%s" % cci.event.pk
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": ":page_facing_up:  Submit CC Report",
                        "emoji": True
                    },
                    "url": "https://lnl.wpi.edu" + reverse("my:report", args=[cci.event.pk]),
                    "action_id": "cc-report-%s" % cci.event.pk
                }
            ]
        }
    ]

    return blocks


def cc_report_reminder(cci):
    """
    Blocks for a missing crew chief report reminder
    Generated using the Block Kit Builder (https://app.slack.com/block-kit-builder)

    :param cci: EventCCInstance object
    """

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "CC Report Reminder",
                "emoji": False
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "This is a reminder that you have a pending crew chief report for *%s*.\n\n\n"
                        "Submitting a crew chief report and recording crew hours are required parts of being a crew "
                        "chief. These tasks are expected to be completed shortly after an event while you still have "
                        "all the details of the event fresh in your mind. Delaying submitting your crew chief report "
                        "directly delays the billing of this event." % cci.event.event_name
            }
        },
        {
            "type": "divider"
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": ":page_facing_up:  Submit Report",
                        "emoji": True
                    },
                    "style": "primary",
                    "url": "https://lnl.wpi.edu" + reverse("my:report", args=[cci.event.pk]),
                    "action_id": "cc-report-%s" % cci.event.pk
                }
            ]
        }
    ]

    return blocks


def event_edited_notification(event, triggered_by, fields_changed):
    """
    Blocks for an event edited Slack notification.
    Generated using the Block Kit Builder (https://app.slack.com/block-kit-builder)

    :param event: The event object
    :param triggered_by: The user that edited the event
    :param fields_changed: A list of fields that have changed
    """

    user = triggered_by.get_full_name()
    slack_user = user_profile(lookup_user(triggered_by))
    if slack_user['ok']:
        user = "@" + slack_user['user']['name']

    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "The following event was just edited by %s" % user
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Fields changed*: %s\n\n> *%s*\n> _%s_\n> *Start*: %s\n> *End*: %s\n> *Services*: %s\n"
                        "> *Client*: %s" % (', '.join(fields_changed), event.event_name, event.location,
                                            event.datetime_start.strftime('%b %-d, %Y, %-I:%M %p'),
                                            event.datetime_end.strftime('%b %-d, %Y, %-I:%M %p'), event.short_services,
                                            event.org_to_be_billed)
            }
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "View Event",
                        "emoji": False
                    },
                    "style": "primary",
                    "url": "https://lnl.wpi.edu" + reverse('events:detail', args=[event.pk]),
                    "action_id": "edited-event-%s" % str(event.pk)
                }
            ]
        }
    ]

    return blocks
