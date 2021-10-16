import json
import requests
from django.utils import timezone
from django.conf import settings
from django.http import JsonResponse, HttpResponseRedirect
from django.shortcuts import render, get_object_or_404, reverse
from django.contrib.auth.decorators import permission_required, login_required
from django.contrib.messages.views import messages
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt

from . import models


# NOTE: Most of this is a temporary proof of concept, and will be pulled back after Wall of Sound.
# Pushing code like this without tests or documentation is bad practice. DO NOT DO THIS. I am a professional.
def auth(request):
    callback = "https%3A%2F%2Flnl.wpi.edu%2Fspotify%2Fauth%2Fcallback%2F"

    session = get_object_or_404(models.Session, pk=1)
    if not session.refresh_token:
        endpoint = "https://accounts.spotify.com/authorize?client_id=" + settings.SPOTIFY_CLIENT_ID + \
                   "&response_type=code&redirect_uri=" + callback + \
                   "&scope=user-read-currently-playing%20user-modify-playback-state"
        return HttpResponseRedirect(endpoint)
    else:
        return refresh_token(request)


def auth_callback(request):
    client_token = settings.SPOTIFY_TOKEN
    code = request.GET['code']
    session = get_object_or_404(models.Session, pk=1)

    endpoint = "https://accounts.spotify.com/api/token"
    headers = {"Authorization": "Basic " + client_token, "Content-Type": "application/x-www-form-urlencoded"}
    resp = requests.post(endpoint, {'grant_type': "authorization_code", 'code': code,
                                    'redirect_uri': 'https://lnl.wpi.edu/spotify/auth/callback/'}, headers=headers)
    data = json.loads(resp.content)
    if 'access_token' in data:
        session.auth_token = data['access_token']
    else:
        messages.warning(request, 'Failed to obtain token')
        print(data)
    if 'refresh_token' in data:
        session.refresh_token = data['refresh_token']
    session.save()
    return HttpResponseRedirect(reverse("spotify:list", args=[1]))


def refresh_token(request):
    client_token = settings.SPOTIFY_TOKEN

    session = get_object_or_404(models.Session, pk=1)
    endpoint = "https://accounts.spotify.com/api/token"
    headers = {"Authorization": "Basic " + client_token, "Content-Type": "application/x-www-form-urlencoded"}
    resp = requests.post(endpoint, {'grant_type': "refresh_token", 'refresh_token': session.refresh_token}, headers=headers)
    data = json.loads(resp.content)
    if 'access_token' in data:
        session.auth_token = data['access_token']
    else:
        messages.warning(request, 'Failed to refresh token')
        print(data)
    if 'refresh_token' in data:
        session.refresh_token = data['refresh_token']
    session.save()
    return HttpResponseRedirect(reverse("spotify:list", args=[1]))


@require_POST
@csrf_exempt
def obtain_token(request):
    """ TEMPORARY: For Wall of Sound """
    client_token = settings.SPOTIFY_TOKEN

    endpoint = "https://accounts.spotify.com/api/token"
    headers = {"Authorization": "Basic " + client_token}
    resp = requests.post(endpoint, {'grant_type': "client_credentials"}, headers=headers)
    data = json.loads(resp.content)
    data['runtime'] = queue_estimate()
    return JsonResponse(data)


@require_POST
@csrf_exempt
def song_request(request):
    """ TEMPORARY: Endpoint for accepting song requests """

    data = json.loads(request.body)
    session_id = data['session']
    song_id = data['resource']['id']
    song_name = data['resource']['name']
    duration = data['resource']['duration']
    name = data['first_name'] + ' ' + data['last_name']
    email = data['email']
    phone = data['phone']

    if not email and not phone:
        return JsonResponse({'status': 400, 'message': 'Email or phone number is required'})

    session = get_object_or_404(models.Session, pk=session_id)
    models.SongRequest.objects.create(session=session, identifier=song_id, duration=duration, submitted_by=name,
                                      email=email, phone=phone, name=song_name)
    return JsonResponse({'status': 201, 'qt': 0})


@login_required
@permission_required('spotify.approve_song_request', raise_exception=True)
def queue_manager(request, session):
    """ TEMPORARY: Manage song requests """

    current_session = get_object_or_404(models.Session, pk=session)

    est = queue_estimate()

    context = {'pending': current_session.requests.exclude(approved=True, paid=True),
               'paid': current_session.requests.filter(paid=True), 'queue_length': est}

    return render(request, 'song_requests.html', context)


def approve_request(request, pk):
    request = get_object_or_404(models.SongRequest, pk=pk)
    request.approved = True
    request.save()

    return HttpResponseRedirect(reverse("spotify:list", args=[request.session.pk]))


def cancel_request(request, pk):
    request = get_object_or_404(models.SongRequest, pk=pk)
    session = request.session.pk
    request.delete()

    return HttpResponseRedirect(reverse("spotify:list", args=[session]))


def paid(request, pk):
    r = get_object_or_404(models.SongRequest, pk=pk)

    if r.identifier not in ['Silence', 'Donation']:
        resp = queue_song(r.identifier)
        if 'error' in resp:
            messages.warning(request, resp['error']['message'])
        else:
            r.queued = timezone.now()
            r.paid = True
            r.save()
    else:
        r.queued = timezone.now()
        r.paid = True
        r.save()

    return HttpResponseRedirect(reverse("spotify:list", args=[r.session.pk]))


def queue_song(identifier):
    session = get_object_or_404(models.Session, pk=1)
    endpoint = "https://api.spotify.com/v1/me/player/queue?uri=spotify%3Atrack%3A" + identifier
    headers = {"Authorization": "Bearer " + session.auth_token, "Accept": "application/json",
               "Content-Type": "application/json"}
    resp = requests.post(endpoint, {}, headers=headers)
    if resp.content:
        return json.loads(resp.content)
    else:
        return {}


def queue_estimate():
    session = get_object_or_404(models.Session, pk=1)
    endpoint = "https://api.spotify.com/v1/me/player/currently-playing"
    if not session.auth_token:
        return None
    headers = {"Authorization": "Bearer " + session.auth_token, "Accept": "application/json",
               "Content-Type": "application/json"}
    resp = requests.get(endpoint, headers=headers)
    if resp.content:
        data = json.loads(resp.content)
        try:
            progress = data['progress_ms']
            item = data['item']['id']
            current_song = models.SongRequest.objects.filter(identifier=item).first()
            time_remaining = 0
            if current_song and current_song.queued:
                time_remaining += current_song.duration - progress
                upcoming = models.SongRequest.objects.filter(queued__gt=current_song.queued)
                for request in upcoming:
                    time_remaining += request.duration
                time_remaining = int(time_remaining / 60000)
                return time_remaining
        except KeyError:
            print(resp)
            pass
    else:
        print(resp)
    return None
