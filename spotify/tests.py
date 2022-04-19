import logging
from django.shortcuts import reverse
from django.utils import timezone
from django.contrib.auth.models import Permission
from data.tests.util import ViewTestCase
from events.tests.generators import Event2019Factory
from .models import SpotifyUser, Session, SongRequest


logging.disable(logging.WARNING)


# Create your tests here.
class SpotifyTests(ViewTestCase):
    def setUp(self):
        super(SpotifyTests, self).setUp()

        self.account = SpotifyUser.objects.create(user=self.user, personal=False)
        self.event = Event2019Factory.create(event_name="Spotify Test Event", approved=False,
                                             datetime_end=timezone.now() + timezone.timedelta(minutes=-1),
                                             datetime_start=timezone.now() + timezone.timedelta(days=-1))
        self.session = Session.objects.create(event=self.event, user=self.account, slug="spotify-test-event")
        self.song_request = SongRequest.objects.create(session=self.session, name="Pacific Coast Cool",
                                                       identifier="6BDvEzgDediLAvCmW6bZhV", duration=229000,
                                                       submitted_by="Peter Parker")

    def test_configure_session(self):
        # User needs add or change session permissions
        self.assertOk(self.client.get(reverse("spotify:event-session", args=[self.event.pk])), 403)

        permission = Permission.objects.get(codename="change_session", content_type__app_label__contains="spotify")
        self.user.user_permissions.add(permission)

        # Will need view event permission for redirect
        permission = Permission.objects.get(codename="view_events")
        self.user.user_permissions.add(permission)

        # Check that page redirects if integration is not currently available for the event
        self.assertRedirects(self.client.get(reverse("spotify:event-session", args=[self.event.pk])),
                             reverse("events:detail", args=[self.event.pk]))

        self.event.approved = True
        self.event.save()

        # Page should load ok
        self.assertOk(self.client.get(reverse("spotify:event-session", args=[self.event.pk])))

        # Test form submission
        self.account.token_info = "Form will only show authenticated accounts (token information is encrypted)"
        self.account.save()

        valid_data = {
            "user": str(self.account.pk),
            "accepting_requests": True,
            "allow_explicit": False,
            "auto_approve": False,
            "require_payment": False,
            "private": False,
            "save": "Save Session"
        }

        self.assertRedirects(self.client.post(reverse("spotify:event-session", args=[self.event.pk]), valid_data),
                             reverse("events:detail", args=[self.event.pk]) + "#apps")

    def test_song_request(self):
        with self.settings(SPOTIFY_CLIENT_ID=None):
            # Test that song request form loads ok
            self.assertOk(self.client.get(reverse("spotify:request", args=[self.session.slug])))

            # Check that submission data requires email or phone number
            submission_data = {
                "first_name": "Peter",
                "last_name": "Parker",
                "email": "",
                "phone": "",
                "request_type": "track",
                "save": "6BDvEzgDediLAvCmW6bZhV"  # Track ID
            }

            self.assertOk(self.client.post(reverse("spotify:request", args=[self.session.slug]), submission_data))

            silence_data = {
                "first_name": "Peter",
                "last_name": "Parker",
                "email": "pp@wpi.edu",
                "phone": "",
                "request_type": "silence",
                "save": "Submit"
            }

            self.assertRedirects(self.client.post(reverse("spotify:request", args=[self.session.slug]), silence_data),
                                 reverse("spotify:payment", args=[self.session.pk]) + "?type=silence")

            # Skip testing most successful form submissions (Spotify auth not implemented for tests)

            # If session is private, non-LNL members should not be able to submit requests
            self.session.private = True
            self.session.save()

            self.assertRedirects(self.client.get(reverse("spotify:request", args=[self.session.slug])), reverse("home"))

    def test_pay_fee(self):
        # Check that the page loads ok
        self.assertOk(self.client.get(reverse("spotify:payment", args=[self.session.pk]) + "?type=silence"))

    def test_queue_manager(self):
        # Check required permissions
        self.assertOk(self.client.get(reverse("spotify:list", args=[self.session.pk])), 403)

        permission = Permission.objects.get(codename="view_session", content_type__app_label="spotify")
        self.user.user_permissions.add(permission)

        # Ensure API requests will fail so that Spotipy doesn't try to authenticate us
        with self.settings(SPOTIFY_CLIENT_ID=None):
            self.assertOk(self.client.get(reverse("spotify:list", args=[self.session.pk])))

    def test_approve(self):
        # Check that get requests are not permitted
        self.assertOk(self.client.get(reverse("spotify:approve-request", args=[self.song_request.pk])), 405)

        # Check that approval permissions are required
        self.assertOk(self.client.post(reverse("spotify:approve-request", args=[self.song_request.pk])), 403)

        permission = Permission.objects.get(codename="approve_song_request")
        self.user.user_permissions.add(permission)

        # Check that page redirects back to the list and request has been approved
        with self.settings(SPOTIFY_CLIENT_ID=None):
            # Will need view_session permission for redirect
            permission = Permission.objects.get(codename="view_session", content_type__app_label="spotify")
            self.user.user_permissions.add(permission)

            self.assertRedirects(self.client.post(reverse("spotify:approve-request", args=[self.song_request.pk])),
                                 reverse("spotify:list", args=[self.session.pk]))

            self.song_request.refresh_from_db()
            self.assertTrue(self.song_request.approved)

    def test_cancel(self):
        # Check that get requests are not permitted
        self.assertOk(self.client.get(reverse("spotify:cancel-request", args=[self.song_request.pk])), 405)

        # Check that approval permissions are required
        self.assertOk(self.client.post(reverse("spotify:cancel-request", args=[self.song_request.pk])), 403)

        permission = Permission.objects.get(codename="approve_song_request")
        self.user.user_permissions.add(permission)

        # Check that page redirects back to the list and request has been deleted
        with self.settings(SPOTIFY_CLIENT_ID=None):
            # Will need view_session permissions on redirect
            permission = Permission.objects.get(codename="view_session", content_type__app_label="spotify")
            self.user.user_permissions.add(permission)

            self.assertRedirects(self.client.post(reverse("spotify:cancel-request", args=[self.song_request.pk])),
                                 reverse("spotify:list", args=[self.session.pk]))

            self.assertFalse(SongRequest.objects.filter(name="Pacific Coast Cool").exists())

    def test_paid(self):
        # Check that get requests are not permitted
        self.assertOk(self.client.get(reverse("spotify:mark-paid", args=[self.song_request.pk])), 405)

        # Check that approval permissions are required
        self.assertOk(self.client.post(reverse("spotify:mark-paid", args=[self.song_request.pk])), 403)

        permission = Permission.objects.get(codename="approve_song_request")
        self.user.user_permissions.add(permission)

        # Will need view_session permission for redirect
        permission = Permission.objects.get(codename="view_session", content_type__app_label="spotify")
        self.user.user_permissions.add(permission)

        # Spotify authentication is not implemented for tests (Won't actually queue the track)
        with self.settings(SPOTIFY_CLIENT_ID=None):
            self.assertRedirects(self.client.post(reverse("spotify:mark-paid", args=[self.song_request.pk])),
                                 reverse("spotify:list", args=[self.song_request.session.pk]))

            self.song_request.refresh_from_db()
            self.assertTrue(self.song_request.paid)

    def test_queue_song(self):
        # Check that get requests are not permitted
        self.assertOk(self.client.get(reverse("spotify:queue", args=[self.song_request.pk])), 405)

        # Check that approval permissions are required
        self.assertOk(self.client.post(reverse("spotify:queue", args=[self.song_request.pk])), 403)

        permission = Permission.objects.get(codename="approve_song_request")
        self.user.user_permissions.add(permission)

        # Will need view_session permission for the redirect
        permission = Permission.objects.get(codename="view_session", content_type__app_label="spotify")
        self.user.user_permissions.add(permission)

        # Spotify authentication is not implemented for tests (Won't actually queue the track)
        with self.settings(SPOTIFY_CLIENT_ID=None):
            self.assertRedirects(self.client.post(reverse("spotify:queue", args=[self.song_request.pk])),
                                 reverse("spotify:list", args=[self.song_request.session.pk]))

    def test_qr_code(self):
        # Check that the page loads ok
        self.assertOk(self.client.get(reverse("spotify:qr", args=[self.session.pk])))
