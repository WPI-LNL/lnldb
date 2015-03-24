# helper for auth
def is_officer(user):
    if user:
        return user.groups.filter(name="Officer").count() != 0
    else:
        return False


def is_lnlmember(user):
    if user:
        return user.groups.filter(name="Default").count() == 0
    else:
        return False