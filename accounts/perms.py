from events.perms import AssocUsersCustomPermissionLogic


class EventUserPermLogic(AssocUsersCustomPermissionLogic):
    field_name = ['submitter__contact', 'submitter__crew_chief', 'submitter__ccinstances__crew_chief',
                  'event__submitted_by', 'event__lnl_contact', 'event__crew_chief', 'event__ccinstances__crew_chief',
                  'ccinstances__event__submitted_by', 'ccinstances__event__contact', 'ccinstances__event__crew_chief',
                  'crewchiefx__contact', 'crewchiefx__submitted_by', 'crewchiefx__ccinstances__crew_chief',
                  'contact__ccinstances__crew_chief', 'contact__crew_chief', 'contact__submitted_by']
    perms = ('accounts.view_user',)


# Begin Intra-Org

class IntraOrgPermLogic(AssocUsersCustomPermissionLogic):
    field_name = ['orgusers__associated_users', 'orgowner__associated_users',
                  'orgusers__user_in_charge']
    perms = ('accounts.view_user',)


# will only go one level. And that's a good thing.
class AssocOrgPermLogic(AssocUsersCustomPermissionLogic):
    field_name = ['orgusers__associated_orgs__associated_users',
                  'orgowner__associated_orgs__associated_users',
                  'orgusers__associated_orgs__user_in_charge',
                  'orgowner__associated_orgs__user_in_charge']
    perms = ('accounts.view_user',)


PERMISSION_LOGICS = (
    ('accounts.User', EventUserPermLogic()),
    ('accounts.User', IntraOrgPermLogic()),
    ('accounts.User', AssocOrgPermLogic()),
)
