"""
Examples to display in the Documentation
"""


notification_response = {
    "id": "SWA001",
    "format": "notification",
    "type": "advisory",
    "class": 2,
    "title": "Upcoming Maintenance",
    "message": "All Lens and Lights web services will be temporarily unavailable on January 5 from 2:00-2:45 AM EST "
               "as we perform routine upgrades and maintenance. We apologize for the inconvenience.",
    "expires": "2020-01-05T07:00:00Z"
}

spotify_playback_state = {
    "id": "test-event",
    "event": {
        "id": 1,
        "event_name": "Test Event",
        "description": "This is a test",
        "location": "Odeum All",
        "datetime_start": "2022-01-01T00:00:00-0400",
        "datetime_end": "2022-01-01T02:00:00-0400"
    },
    "allow_explicit": True,
    "require_payment": False,
    "accepting_requests": True,
    "is_playing": True,
    "runtime_ms": 159148,
    "current_track": {
        "album": {
            "album_type": "album",
            "artists": [
                {
                    "external_urls": {
                        "spotify": "https://open.spotify.com/artist/4bEFYZDTVnBQvQqo6AYL8x"
                    },
                    "href": "https://api.spotify.com/v1/artists/4bEFYZDTVnBQvQqo6AYL8x",
                    "id": "4bEFYZDTVnBQvQqo6AYL8x",
                    "name": "Rik Pfenninger",
                    "type": "artist",
                    "uri": "spotify:artist:4bEFYZDTVnBQvQqo6AYL8x"
                }
            ],
            "available_markets": [],
            "external_urls": {
                "spotify": "https://open.spotify.com/album/1mKOHB2oWtYBx5QkwZiUrI"
            },
            "href": "https://api.spotify.com/v1/albums/1mKOHB2oWtYBx5QkwZiUrI",
            "id": "1mKOHB2oWtYBx5QkwZiUrI",
            "images": [
                {
                    "height": 640,
                    "url": "https://i.scdn.co/image/ab67616d0000b273493628931c8845964ee4e9bc",
                    "width": 640
                },
                {
                    "height": 300,
                    "url": "https://i.scdn.co/image/ab67616d00001e02493628931c8845964ee4e9bc",
                    "width": 300
                },
                {
                    "height": 64,
                    "url": "https://i.scdn.co/image/ab67616d00004851493628931c8845964ee4e9bc",
                    "width": 64
                }
            ],
            "name": "That's Kool",
            "release_date": "2008-06-12",
            "release_date_precision": "day",
            "total_tracks": 14,
            "type": "album",
            "uri": "spotify:album:1mKOHB2oWtYBx5QkwZiUrI"
        },
        "artists": [
            {
                "external_urls": {
                    "spotify": "https://open.spotify.com/artist/4bEFYZDTVnBQvQqo6AYL8x"
                },
                "href": "https://api.spotify.com/v1/artists/4bEFYZDTVnBQvQqo6AYL8x",
                "id": "4bEFYZDTVnBQvQqo6AYL8x",
                "name": "Rik Pfenninger",
                "type": "artist",
                "uri": "spotify:artist:4bEFYZDTVnBQvQqo6AYL8x"
            }
        ],
        "available_markets": [],
        "disc_number": 1,
        "duration_ms": 228906,
        "explicit": False,
        "external_ids": {
            "isrc": "uscgj0874461"
        },
        "external_urls": {
            "spotify": "https://open.spotify.com/track/6BDvEzgDediLAvCmW6bZhV"
        },
        "href": "https://api.spotify.com/v1/tracks/6BDvEzgDediLAvCmW6bZhV",
        "id": "6BDvEzgDediLAvCmW6bZhV",
        "is_local": False,
        "name": "Pacific Coast Cool",
        "popularity": 1,
        "preview_url": "https://p.scdn.co/mp3-preview/92f261da97b77f5dde92800b51f34b1be885cf90?cid=b602002be1d54f1885fcbebd415e57b9",
        "track_number": 9,
        "type": "track",
        "uri": "spotify:track:6BDvEzgDediLAvCmW6bZhV"
    },
    "urls": {
        "request_form": "https://lnl.wpi.edu/spotify/request/test-event/",
        "qr_code": "https://lnl.wpi.edu/spotify/session/1/qr-code/"
    }
}

song_request = [
    {
        "id": 1,
        "session": "test-event",
        "name": "Pacific Coast Cool",
        "duration": 229000,
        "approved": False,
        "queued_ts": None,
        "requestor": {
            "name": "Barry Allen",
            "email": "flash@starlabs.net",
            "phone": None
        },
        "urls": {
            "spotify_url": "https://open.spotify.com/track/6BDvEzgDediLAvCmW6bZhV"
        }
    }
]
