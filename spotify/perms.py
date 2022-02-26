from events.perms import AssocUsersCustomPermissionLogic


class CrewChiefSessionPermLogic(AssocUsersCustomPermissionLogic):
    field_name = ['event__ccinstances__crew_chief']
    perms = ('spotify.view_session', 'spotify.change_session', 'spotify.add_session')


class CrewChiefSongRequestPermLogic(AssocUsersCustomPermissionLogic):
    field_name = ['session__event__ccinstances__crew_chief']
    perms = ('spotify.approve_song_request',)


PERMISSION_LOGICS = (
    ('spotify.Session', CrewChiefSessionPermLogic()),
    ('spotify.SongRequest', CrewChiefSongRequestPermLogic())
)
