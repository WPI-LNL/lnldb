import json
from urllib.parse import urlencode
from data.tests.util import ViewTestCase
from django.conf import settings
from django.shortcuts import reverse
from . import views


class SlackAPITests(ViewTestCase):
    def test_interaction_handler(self):
        # NOTE: Running this test could send messages to the LNL Laptop. That is ok.

        # Check that GET requests are not permitted
        self.assertOk(self.client.get(reverse("slack:interactive-endpoint")), 405)

        # Test TFed global shortcut (unused fields omitted)
        shortcut_data = {
            "type": "shortcut",
            "callback_id": "tfed",
            "trigger_id": "944799105734.773906753841.38b5894552bdd4a780554ee59d1f3638"
        }

        data = {
            "payload": json.dumps(shortcut_data)
        }

        # Expect 500 since trigger will be expired (Launch from within Slack to test 200 response)
        self.assertOk(self.client.post(reverse("slack:interactive-endpoint"), urlencode(data),
                                       content_type="application/x-www-form-urlencoded"), 500)

        # Test TFed ticket submission (most unused fields omitted)
        submission_data = {
            "type": "view_submission",
            "user": {
                "id": "U7W4C4PUP",
                "username": "lnl"
            },
            "view": {
                "callback_id": "tfed-modal",
                "state": {
                    "values": {
                        "subject": {
                            "subject-action": {
                                "value": "Example Ticket"
                            }
                        },
                        "description": {
                            "description-action": {
                                "value": "Something broke so I would like to submit a ticket please."
                            }
                        },
                        "rt_topic": {
                            "rt_topic-action": {
                                "type": "static_select",
                                "selected_option": {
                                    "text": {
                                        "text": 'Web Services'
                                    },
                                    "value": "Database"
                                }
                            }
                        }
                    }
                }
            }
        }

        data = {
            "payload": json.dumps(submission_data)
        }
        if settings.SLACK_TOKEN not in ['', None]:
            if settings.RT_TOKEN in ['', None]:  # Only run if RT token is not provided
                self.assertOk(self.client.post(reverse("slack:interactive-endpoint"), urlencode(data),
                                               content_type="application/x-www-form-urlencoded"))
        else:
            # Should fail on user lookup
            self.assertOk(self.client.post(reverse("slack:interactive-endpoint"), urlencode(data),
                                           content_type="application/x-www-form-urlencoded"), 500)

        # Test TFed ticket update form submission (unused fields omitted)
        new_ticket_data = {
            "type": "view_submission",
            "user": {
                "id": "UABCD1234",
                "username": "lnl"
            },
            "view": {
                "callback_id": "ticket-update-modal",
                "blocks": [
                    {"block_id": "ticket_status"},
                    {"type": "section", "block_id": "ticket_assignee"},
                    {"type": "divider", "block_id": "620#C01JW25M3J9#1626923790.000100"}  # Ticket no., channel id, ts
                ],
                "state": {
                    "values": {
                        "ticket_status": {
                            "ticket_status-action": {
                                "selected_option": {
                                    "value": "open"
                                }
                            }
                        },
                        "ticket_assignee": {
                            "ticket_assignee-action": {
                                "selected_user": "U7W4C4PUP"
                            }
                        },
                        "ticket_comment": {
                            "ticket_comment-action": {
                                "value": "This is a comment that would be added to the ticket."
                            }
                        },
                        "email_requestor": {
                            "email_requestor-action": {
                                "selected_options": [{
                                    "value": "send-email"
                                }]
                            }
                        }
                    }
                }
            }
        }

        data = {
            "payload": json.dumps(new_ticket_data)
        }
        if settings.RT_TOKEN in [None, '']:
            self.assertOk(self.client.post(reverse("slack:interactive-endpoint"), urlencode(data),
                                           content_type="application/x-www-form-urlencoded"))

        # Test TFed ticket message button actions (unused fields omitted)
        action_data = {
            "type": "block_actions",
            "user": {
                "id": "UABCD1234",
                "username": "lnl"
            },
            "channel": {
                "id": settings.SLACK_TARGET_TFED_DB
            },
            "message": {
                "ts": "1626923790.000100",  # Example message timestamp (This message no longer exists)
                "blocks": [
                    {
                        "block_id": "620~lnl"  # Ticket ID and reporter username separated by ~
                    },
                    {
                        "text": {
                            "text": "This is the contents of the ticket."
                        }
                    }
                ]

            },
            "actions": [{
                "action_id": "close-ticket"
            }],
        }

        data = {
            "payload": json.dumps(action_data)
        }
        self.assertOk(self.client.post(reverse("slack:interactive-endpoint"), urlencode(data),
                                       content_type="application/x-www-form-urlencoded"))

    def test_ticket_message_generator(self):
        expected = [
            {
                "type": "section",
                "block_id": "123~testuser",
                "text": {
                    "type": "mrkdwn",
                    "text": "\n*<https://lnl.wpi.edu/|Ticket #123: Some Example Ticket>*"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "plain_text",
                    "text": "This is an example ticket.",
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
                        "text": "*Status* » New\n*Assignee* » Nobody\n*Reporter* » @testuser"
                    }
                ]
            },
            {
                "type": "actions",
                "block_id": "ticket-actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Open Ticket",
                            "emoji": False
                        },
                        "value": "open",
                        "action_id": "open-ticket",
                        "style": "primary"
                    }
                ]
            }
        ]

        # Set up the ticket information that should be passed in
        ticket_info = {
            "url": "https://lnl.wpi.edu/",
            "id": "123",
            "subject": "Some Example Ticket",
            "description": "This is an example ticket.",
            "status": "New",
            "assignee": None,
            "reporter": "testuser"
        }
        self.assertEqual(expected, views.tfed_ticket(ticket_info))
