from django.utils import timezone
from django.conf import settings
from django.http import HttpResponseRedirect
from django.shortcuts import render, get_object_or_404, reverse
from django.contrib.auth import get_user_model, PermissionDenied
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib.messages.views import messages
from spotipy.oauth2 import SpotifyOAuth
from spotipy import Spotify, SpotifyException

from events.models import Event2019
from .api import DjangoCacheHandler, scopes, get_spotify_session, queue_estimate, get_currently_playing, add_to_queue
from . import models, forms


@login_required
def login(request):
    """ Authenticate a user against the Spotify API """

    if settings.SPOTIFY_CLIENT_ID in [None, '']:
        messages.add_message(request, messages.WARNING, "Configuration Error: The Spotify integration is currently "
                                                        "unavailable. Please contact the Webmaster.")
        return HttpResponseRedirect(reverse("home"))

    # By default, the account will be linked to the current user. If an account already exists, grab its id.
    user = request.user
    existing_account = models.SpotifyUser.objects.filter(user=user).order_by('pk').first()
    account_id = None
    if existing_account:
        account_id = existing_account.pk

    # Admin site can login to an account directly
    if request.GET.get('user', None):
        user_id = request.GET.get('user')
        account = get_object_or_404(models.SpotifyUser, pk=user_id)
        user = account.user
        account_id = account.pk
    cache_handler = DjangoCacheHandler(user, account_id)
    state = "u%da" % user.pk
    if account_id:
        state += str(account_id)
    auth_manager = SpotifyOAuth(client_id=settings.SPOTIFY_CLIENT_ID, client_secret=settings.SPOTIFY_CLIENT_SECRET,
                                redirect_uri=settings.SPOTIFY_REDIRECT_URI, state=state, scope=' '.join(scopes),
                                cache_handler=cache_handler)

    endpoint = auth_manager.get_authorize_url()
    return HttpResponseRedirect(endpoint)


@login_required
def auth_callback(request):
    """ Handle Spotify authentication callback """

    state = request.GET.get('state', None)
    if not state:
        messages.add_message(request, messages.ERROR, "Spotify authentication failed. No state information.")
        return HttpResponseRedirect(reverse("home"))

    user_id = state.split('a')[0][1:]
    account_id = state.split('a')[1]
    if account_id == '':
        account_id = None
    user = get_object_or_404(get_user_model(), pk=user_id)
    cache_handler = DjangoCacheHandler(user, account_id)
    auth_manager = SpotifyOAuth(client_id=settings.SPOTIFY_CLIENT_ID, client_secret=settings.SPOTIFY_CLIENT_SECRET,
                                redirect_uri=settings.SPOTIFY_REDIRECT_URI, state=state, scope=' '.join(scopes),
                                cache_handler=cache_handler)
    api = Spotify(auth_manager=auth_manager)

    code = request.GET.get('code', None)
    if not code:
        error = request.GET.get('error', 'Unknown error')
        if error != "access_denied":
            messages.add_message(request, messages.ERROR, "Spotify authentication failed. {}"
                                 .format(error.replace("_", " ").capitalize()))
        return HttpResponseRedirect(reverse("home"))

    auth_manager.get_access_token(code=code)

    if account_id:
        account = get_object_or_404(models.SpotifyUser, pk=account_id)
    else:
        account = get_object_or_404(models.SpotifyUser, user=user)

    try:
        profile = api.current_user()
        account.display_name = profile['display_name']
        account.spotify_id = profile['id']
        account.save()
        messages.success(request, "Success! Your Spotify account is now connected.")
    except SpotifyException as error:
        messages.error(request, "Error: {}".format(error.msg))
    return HttpResponseRedirect(reverse("home"))


@login_required
def configure_session(request, event_id):
    """
    Set up a Spotify shared listening session and begin accepting song requests for an event

    :param event_id: The primary key value of the event the session is attached to
    """

    context = {'msg': 'Configure Spotify Session'}
    event = get_object_or_404(Event2019, pk=event_id)

    session = models.Session.objects.filter(event=event).first()

    if not request.user.has_perm('spotify.add_session', session) and \
            not request.user.has_perm('spotify.change_session', session):
        raise PermissionDenied

    if not event.approved or event.reviewed or event.closed or event.cancelled:
        messages.warning(request, "The Spotify integration cannot be used for this event at this time")
        return HttpResponseRedirect(reverse("events:detail", args=[event.pk]))

    if request.method == 'POST':
        form = forms.SpotifySessionForm(request.user, request.POST, instance=session)
        if form.is_valid():
            session = form.save(commit=False)
            session.event = event
            session.save()
            return HttpResponseRedirect(reverse("events:detail", args=[event.pk]) + "#apps")
    else:
        form = forms.SpotifySessionForm(request_user=request.user, instance=session)
    context['form'] = form
    context['session'] = session
    return render(request, 'form_crispy.html', context)


def song_request(request, session_id):
    """
    Page for accepting song requests

    :param session_id: The unique slug for the corresponding session
    """
    session = get_object_or_404(models.Session, slug=session_id)
    form = forms.SongRequestForm(session)
    verified = False
    complete = False
    runtime = queue_estimate(session)
    tracks = []
    albums = []
    artists = []

    if request.user.is_authenticated:
        if session.private and not request.user.is_lnl:
            messages.add_message(request, messages.WARNING, "Unable to join private Spotify session")
            return HttpResponseRedirect(reverse("home"))

        form = forms.SongRequestForm(session, {
            "first_name": request.user.first_name,
            "last_name": request.user.last_name,
            "email": request.user.email,
            "phone": request.user.phone,
            "request_type": "track"
        })

        if not session.allow_silence and request.user.first_name and request.user.last_name and \
                (request.user.email or request.user.phone):
            verified = True
    elif session.private:
        next_url = reverse("spotify:request", args=[session.slug])
        return HttpResponseRedirect(reverse("accounts:login") + "?next=" + next_url)

    if request.method == 'POST':
        form = forms.SongRequestForm(session, request.POST)
        if form.is_valid():
            try:
                # If the user is given the option to request silence, handle the first step accordingly
                if request.POST['save'] == "Submit":
                    if request.POST['request_type'] == "silence":
                        new_request = form.save(commit=False)
                        new_request.session = session
                        new_request.submitted_by = request.POST['first_name'] + " " + request.POST['last_name']
                        new_request.identifier = "Silence"
                        new_request.name = "1 Minute of Silence"
                        new_request.duration = 60000
                        new_request.save()
                        return HttpResponseRedirect(reverse("spotify:payment", args=[session.pk]) + "?type=silence")
                    verified = True

                # Search Spotify's API for a tracks, albums, and artists matching a given query
                elif request.POST['save'] == "Search":
                    api = get_spotify_session(session.user, request.user)
                    verified = True
                    results = api.search(request.POST['search_q'], type="track,album,artist")
                    tracks = results['tracks']['items']
                    albums = results['albums']['items']
                    artists = results['artists']['items']
                else:
                    # Submit request and redirect to payment page if necessary
                    api = get_spotify_session(session.user, request.user)
                    track_info = api.track(request.POST['save'])
                    new_request = form.save(commit=False)
                    new_request.session = session
                    new_request.submitted_by = request.POST['first_name'] + " " + request.POST['last_name']
                    new_request.identifier = request.POST['save']
                    new_request.name = track_info['name']
                    new_request.duration = track_info['duration_ms']
                    if session.auto_approve:
                        new_request.approved = True
                        if not session.require_payment:
                            try:
                                api.add_to_queue(request.POST['save'])
                                new_request.queued = timezone.now()
                            except SpotifyException:
                                pass
                    new_request.save()
                    complete = True
                    if session.require_payment:
                        return HttpResponseRedirect(reverse("spotify:payment", args=[session.pk]))
            except SpotifyException as error:
                messages.add_message(request, messages.ERROR, "Spotify API Error: %s" % error.msg.split(':')[-1])

    context = {'form': form, 'LIGHT_THEME': True, 'tracks': tracks, 'albums': albums, 'artists': artists,
               'session': session, 'verified': verified, 'complete': complete, 'runtime': runtime}
    return render(request, 'song_request_form.html', context)


def pay_fee(request, session_id):
    """
    If payment is required when making a song request, this page should be displayed.

    :param session_id: The primary key value of the session object
    """

    session = get_object_or_404(models.Session, pk=session_id)

    amount = 1

    options = request.GET.get('type', 'track')
    if options == "silence":
        amount = 5

    return render(request, 'pay.html', {'session': session, 'amount': amount, 'LIGHT_THEME': True})


@login_required
def queue_manager(request, session):
    """
    Manage or view song requests

    :param session: The primary key value of the session object
    """

    current_session = get_object_or_404(models.Session, pk=session)

    if not request.user.has_perm('spotify.view_session', current_session):
        raise PermissionDenied

    est = queue_estimate(current_session)

    currently_playing = get_currently_playing(current_session)

    context = {'pending': current_session.requests.exclude(queued__isnull=False), 'session': current_session,
               'paid': current_session.requests.filter(queued__isnull=False), 'queue_length': est,
               'current_track': currently_playing}

    return render(request, 'song_requests.html', context)


@require_POST
@login_required
def approve_request(request, pk):
    """ Approve a song request (POST only) """
    r = get_object_or_404(models.SongRequest, pk=pk)

    if not request.user.has_perm('spotify.approve_song_request', r):
        raise PermissionDenied

    r.approved = True
    r.save()

    return HttpResponseRedirect(reverse("spotify:list", args=[r.session.pk]))


@require_POST
@login_required
def cancel_request(request, pk):
    """ Deny a song request (POST only) """
    r = get_object_or_404(models.SongRequest, pk=pk)

    if not request.user.has_perm('spotify.approve_song_request', r):
        raise PermissionDenied

    session = r.session.pk
    r.delete()

    return HttpResponseRedirect(reverse("spotify:list", args=[session]))


@require_POST
@login_required
def paid(request, pk):
    """ Mark a song request as paid (if applicable). POST only. """
    r = get_object_or_404(models.SongRequest, pk=pk)

    if not request.user.has_perm('spotify.approve_song_request', r):
        raise PermissionDenied

    r.paid = True
    r.save()

    if r.identifier == "Silence":
        r.queued = timezone.now()
        r.save()
        messages.add_message(request, messages.INFO, "Reminder: You will need to handle the minute of silence manually")
    else:
        error = add_to_queue(r, request.user)
        if error:
            messages.add_message(request, messages.ERROR, error.msg.split(':')[-1])

    return HttpResponseRedirect(reverse("spotify:list", args=[r.session.pk]))


@require_POST
@login_required
def queue_song(request, pk):
    """
    Add a song to the Spotify session queue (POST only)

    :param pk: The primary key value of the corresponding song request
    """
    r = get_object_or_404(models.SongRequest, pk=pk)

    if not request.user.has_perm('spotify.approve_song_request', r):
        raise PermissionDenied

    if r.identifier != "Silence":
        error = add_to_queue(r, request.user)
        if error:
            messages.add_message(request, messages.ERROR, error.msg.split(':')[-1])
    else:
        r.queued = timezone.now()
        r.save()
        messages.add_message(request, messages.INFO, "Reminder: You will need to handle the minute of silence manually")

    return HttpResponseRedirect(reverse("spotify:list", args=[r.session.pk]))
