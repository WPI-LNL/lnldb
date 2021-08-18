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
