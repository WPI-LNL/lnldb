# helper for auth
def is_officer(user):
    if user:
        return user.groups.filter(name="Officer").count() != 0
    else:
        return False
