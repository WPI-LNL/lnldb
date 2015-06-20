from django.contrib.auth import get_user_model
from events.perms import AssocUsersCustomPermissionLogic

# Begin Event

class EventUserPermLogic(AssocUsersCustomPermissionLogic):
    field_name = ['user__submitter__contact', 'user__submiter_crew_chief', 'user__submitter__ccinstances__crew_chief',
                  'user__event__submitted_by', 'user__event__crew_chief', 'user__event__ccinstances__crew_chief',
                  'user__ccinstances__event__submitted_by', 'user__ccinstances__event__contact',
                  'user__ccinstances__event_crew_chief',
                  'user__crewchiefx__contact', 'user__crewchiefx__submitted_by',
                  'user__crewchiefx__ccinstances__crew_chief']
    perms = ('acct.view_user',)


# Begin Intra-Org

class IntraOrgPermLogic(AssocUsersCustomPermissionLogic):
    field_name = ['user__orgusers__associated_users', 'user__orgowner__associated_users',
                  'user__orgusers__user_in_charge']
    perms = ('acct.view_user',)


# will only go one level. And that's a good thing.
class AssocOrgPermLogic(AssocUsersCustomPermissionLogic):
    field_name = ['user__orgusers__associated_orgs__associated_users',
                  'user__orgowner__associated_orgs__associated_users',
                  'user__orgusers__associated_orgs__user_in_charge',
                  'user__orgowner__associated_orgs__user_in_charge']
    perms = ('acct.view_user',)


PERMISSION_LOGICS = (
    ('acct.Profile', EventUserPermLogic()),
    ('acct.Profile', IntraOrgPermLogic()),
    ('acct.Profile', AssocOrgPermLogic()),
)
