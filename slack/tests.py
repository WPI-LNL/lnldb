import json
import zoneinfo
import logging
import requests
from urllib.parse import urlencode
from django.test import TestCase
from data.tests.util import ViewTestCase
from django.contrib.auth.models import Permission
from django.utils import timezone
from django.conf import settings
from django.shortcuts import reverse

from events.tests.generators import CCInstanceFactory, Event2019Factory, LocationFactory, CategoryFactory, ServiceFactory
from events.models import ServiceInstance
from . import views, models
from .templatetags import slack


logging.disable(logging.WARNING)


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
        if requests.head("https://lnl-rt.wpi.edu/rt/Ticket/Display.html").status_code == 200:
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
        if requests.head("https://lnl-rt.wpi.edu/rt/Ticket/Display.html").status_code == 200:
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
        if settings.RT_TOKEN in [None, ''] and requests.head("https://lnl-rt.wpi.edu/rt/Ticket/Display.html").status_code == 200:
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
        if requests.head("https://lnl-rt.wpi.edu/rt/Ticket/Display.html").status_code == 200:
            self.assertOk(self.client.post(reverse("slack:interactive-endpoint"), urlencode(data),
                                        content_type="application/x-www-form-urlencoded"))

    def test_event_url_verification(self):
        # Slack may conduct a URL verification handshake to validate our server's identity
        validation_info = {
            "type": "url_verification",
            "token": "Abc1dEfGhI2JkLMnOpQRstUv",
            "challenge": "3wXyza4bCd5eFgHIJklM6789N0OP1qrsTUVWxYzaBC23dEFGHI4J"
        }

        # GET requests should not be permitted
        self.assertOk(self.client.get(reverse("slack:event-endpoint")), 405)

        resp = self.client.post(reverse("slack:event-endpoint"), validation_info, content_type="application/json")
        self.assertOk(resp)
        self.assertJSONEqual(
            str(resp.content, 'utf-8'),
            {"challenge": "3wXyza4bCd5eFgHIJklM6789N0OP1qrsTUVWxYzaBC23dEFGHI4J"}
        )

    def test_welcome_message(self):
        # If you wish to actually test this, replace "id" with your user id
        event_info = {
            "type": "event_callback",
            "event": {
                "type": "team_join",
                "user": {
                    "id": "UABCD1234",
                    "username": "lnl"
                }
            }
        }

        self.assertOk(self.client.post(reverse("slack:event-endpoint"), event_info, content_type="application/json"))


class SlackTemplateTags(TestCase):
    def test_slack_channel_tag(self):
        test_with_channel = "You should totally go join #webdev on Slack!"
        test_without_channel = "Priority #1: Safety"
        self.assertEqual(
            slack.slack(test_with_channel),
            "You should totally go join [#webdev](https://wpilnl.slack.com/app_redirect?channel=webdev) on Slack!"
        )
        self.assertEqual(slack.slack(test_without_channel), test_without_channel)


class SlackViews(ViewTestCase):
    def setUp(self):
        super(SlackViews, self).setUp()
        self.user.first_name = "Test"
        self.user.last_name = "User"

        # Create an event and CC instance
        tz = zoneinfo.ZoneInfo('US/Eastern')
        setup_start = timezone.datetime.strptime('2020-01-01T01:00:00', '%Y-%m-%dT%H:%M:%S').replace(tzinfo=tz)
        event_location = LocationFactory.create(name="Quad")
        category = CategoryFactory.create(name="Lighting")
        service = ServiceFactory.create(shortname="L1", category=category)
        self.event = Event2019Factory.create(event_name="Test Event", location=event_location,
                                             datetime_start=setup_start, datetime_end=setup_start)
        ServiceInstance.objects.create(event=self.event, service=service)
        setup_location = LocationFactory.create(name="Office", setup_only=True)
        self.cci = CCInstanceFactory.create(event=self.event, crew_chief=self.user, setup_start=setup_start,
                                            setup_location=setup_location)

        self.slack_message = models.SlackMessage.objects.create(posted_to='ABC123', posted_by='U123456789',
                                                                ts='1516229207.000133', content="A bad message")
        self.report = models.ReportedMessage.objects.create(message=self.slack_message, reported_by="U987654321")

    def test_reports_list(self):
        # By default, users should not have permission to view these reports
        self.assertOk(self.client.get(reverse('slack:moderate')), 403)

        permission = Permission.objects.get(codename="view_reportedmessage")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse('slack:moderate')))

        # On POST, mark a task as complete
        data = {
            "report_id": 1
        }

        self.assertRedirects(self.client.post(reverse('slack:moderate'), data), reverse('slack:moderate'))

        self.report.refresh_from_db()
        self.assertTrue(self.report.resolved)

    def test_report_view(self):
        # By default, user should not have permission to view the report
        self.assertOk(self.client.get(reverse('slack:report', args=[self.report.pk])), 403)

        permission = Permission.objects.get(codename="view_reportedmessage")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse('slack:report', args=[self.report.pk])))

        # On POST, mark a task as complete
        self.assertRedirects(self.client.post(reverse('slack:report', args=[self.report.pk])),
                             reverse('slack:moderate'))

        self.report.refresh_from_db()
        self.assertTrue(self.report.resolved)

    def test_ticket_message_generator(self):
        expected_new = [
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

        expected_update = [
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
                        "text": "*Status* » Open\n*Assignee* » @lnl\n*Reporter* » @testuser"
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
                            "text": "Update Ticket",
                            "emoji": False
                        },
                        "value": "update",
                        "action_id": "update-ticket"
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Close Ticket",
                            "emoji": False
                        },
                        "value": "close",
                        "action_id": "close-ticket",
                        "style": "danger"
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

        update_ticket_info = {
            "url": "https://lnl.wpi.edu/",
            "id": "123",
            "subject": "Some Example Ticket",
            "description": "This is an example ticket.",
            "status": "Open",
            "assignee": "lnl",
            "reporter": "testuser"
        }
        self.assertEqual(expected_new, views.tfed_ticket(ticket_info))
        self.assertEqual(expected_update, views.tfed_ticket(update_ticket_info))

    def test_app_home(self):
        expected = [
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "*My Recent Tickets*"
                    }
                ]
            },
            {
                "type": "divider"
            },
            {
                "type": "section",
                "block_id": "123",
                "text": {
                    "type": "mrkdwn",
                    "text": "\n*Ticket #123: Test Ticket*\nStatus » Open"
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
            },
            {
                "type": "divider"
            },
            {
                "type": "section",
                "block_id": "456",
                "text": {
                    "type": "mrkdwn",
                    "text": "\n*Ticket #456: Another Ticket*\nStatus » New"
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
            },
            {
                "type": "divider"
            }
        ]

        tickets = [{'id': 123, 'Subject': "Test Ticket", 'Status': "Open"},
                   {'id': 456, 'Subject': "Another Ticket", 'Status': "New"}]

        self.assertEqual(expected, views.app_home(tickets))

    def test_ticket_comment_modal(self):
        expected = {
            "type": "modal",
            "callback_id": "ticket-comment-modal",
            "title": {
                "type": "plain_text",
                "text": "Comments",
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
            "blocks": [
                {
                    "type": "input",
                    "block_id": "123",
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
        }

        self.assertEqual(expected, views.ticket_comment_modal(123))

    def test_cc_add_message(self):
        expected = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "You've been added as a crew chief to the event *Test Event*. Your setup is currently "
                            "scheduled for *Jan 1, 2020 at 1:00 AM* in the *Office*."
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
                        "url": "https://lnl.wpi.edu" + reverse("events:detail", args=[self.event.pk]),
                        "action_id": "cc-add-1"
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": ":calendar:  Add to calendar",
                            "emoji": True
                        },
                        "url": "https://lnl.wpi.edu" + reverse("events:ics", args=[self.event.pk]),
                        "action_id": "ics-download-1"
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": ":page_facing_up:  Submit CC Report",
                            "emoji": True
                        },
                        "url": "https://lnl.wpi.edu" + reverse("my:report", args=[self.event.pk]),
                        "action_id": "cc-report-1"
                    }
                ]
            }
        ]

        self.assertEqual(expected, views.cc_add_notification(self.cci))

    def test_cc_report_message(self):
        expected = [
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
                    "text": "This is a reminder that you have a pending crew chief report for *Test Event*.\n\n\n"
                            "Submitting a crew chief report and recording crew hours are required parts of being a "
                            "crew chief. These tasks are expected to be completed shortly after an event while you "
                            "still have all the details of the event fresh in your mind. Delaying submitting your "
                            "crew chief report directly delays the billing of this event."
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
                        "url": "https://lnl.wpi.edu" + reverse("my:report", args=[self.event.pk]),
                        "action_id": "cc-report-1"
                    }
                ]
            }
        ]

        self.assertEqual(expected, views.cc_report_reminder(self.cci))

    def test_event_edited_message(self):
        expected = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "The following event was just edited by Test User"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Fields changed*: location, description\n\n> *Test Event*\n> _Quad_\n"
                            "> *Start*: Jan 1, 2020, 1:00 AM\n> *End*: Jan 1, 2020, 1:00 AM\n> *Services*: L1\n"
                            "> *Client*: None"
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
                        "url": "https://lnl.wpi.edu" + reverse('events:detail', args=[self.event.pk]),
                        "action_id": "edited-event-1"
                    }
                ]
            }
        ]

        self.assertEqual(expected, views.event_edited_notification(self.event, self.user, ['location', 'description']))

    def test_report_message_modal(self):
        expected = {
            "type": "modal",
            "callback_id": "report-modal",
            "title": {
                "type": "plain_text",
                "text": "Report a message",
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
            "blocks": [
                {
                    "type": "section",
                    "block_id": "1",
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
        }

        self.assertEqual(expected, views.report_message_modal(self.slack_message))

    def test_reported_message_notification(self):
        expected = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "Someone has flagged a new message for review by a moderator."
                }
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "View Report",
                            "emoji": False
                        },
                        "url": "https://lnl.wpi.edu" + reverse("slack:report", args=[self.slack_message.pk]),
                        "action_id": "reported-message-report"
                    }
                ]
            }
        ]

        self.assertEqual(expected, views.reported_message_notification('U987654321', self.report))
