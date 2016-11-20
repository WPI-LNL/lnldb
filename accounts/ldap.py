import ldap3
import sys
try:
    from django.contrib.auth import get_user_model
    from django.conf.settings import CCC_PASS
except:
    # there's a chance we won't get some results, but it still goes through
    CCC_PASS = None

NAME_LENGTH = 30
# the size of first_name and last_name fields

server_pool = ldap3.ServerPool(('ldaps://ldapv2back.wpi.edu', 'ldaps://vmldapalt.wpi.edu', 'ldaps://ldapv2.wpi.edu'), pool_strategy=ldap3.FIRST, active=True, exhaust=True)


def get_ldap_settings():
    conn_args = {}
    conn_args['client_strategy'] = ldap3.SYNC
    conn_args['read_only'] = True
    conn_args['raise_exceptions'] = True
    if CCC_PASS:
        conn_args['user'] = 'wpieduPersonUUID=a7188b7da454ce4e2396e0e09abd3333,ou=People,dc=WPI,dc=EDU'  # ie. the lnl CCC account dn
        conn_args['password'] = CCC_PASS
    return conn_args


def search_users(q):
    ldap_q = "(& " + "".join(map(lambda tok: "(|(uid=%s*)(givenName=%s*)(sn=%s*))" % (tok, tok, tok), q.split(" "))) + ")"
    conn_args = get_ldap_settings()

    with ldap3.Connection(server_pool, **conn_args) as conn:
        conn.search(search_base='ou=People,dc=wpi,dc=edu', search_filter=ldap_q, search_scope=ldap3.LEVEL, attributes=('givenName', 'sn', 'mail', 'uid'), paged_size=15)
        resp = conn.response
    return resp


def search_or_create_users(q):
    ldap_resp = search_users(q)
    objs = []
    for ldap_u in ldap_resp:
        ldap_u = ldap_u['attributes']
        if 'uid' not in ldap_u:
            continue
        u, created = get_user_model().objects.get_or_create(
            username=ldap_u['uid'][0],
            defaults={
                'email': ldap_u.get('mail', [False])[0] or ldap_u['uid'][0] + "@wpi.edu",
                'first_name': ldap_u.get('givenName', [''])[0][0:NAME_LENGTH - 1],
                'last_name': ldap_u.get('sn', [''])[0][0:NAME_LENGTH - 1]
            }
        )
        objs.append(u)
    return objs


def fill_in_user(user):
    if user.first_name and user.last_name:
        return user
    conn_args = get_ldap_settings()

    with ldap3.Connection(server_pool, **conn_args) as conn:
        conn.search(search_base='ou=People,dc=wpi,dc=edu', search_filter=("(uid=%s)" % user.username), search_scope=ldap3.LEVEL, attributes=('givenName', 'sn'), paged_size=1)
        resp = conn.response
    if len(resp):
        resp = resp[0]['attributes']
        if not user.first_name:
            user.first_name = resp.get('givenName', [''])[0][0:NAME_LENGTH - 1]
        if not user.last_name:
            user.last_name = resp.get('sn', [''])[0][0:NAME_LENGTH - 1]
        if not user.email:
            user.email = resp.get('mail', [False])[0][0] or user.username + "@wpi.edu",
    return user


if __name__ == "__main__":
    if len(sys.argv) == 1:
        print("No argument")
        exit()
    print(search_or_create_users(" ".join(sys.argv[1:])))
