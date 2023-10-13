import json
import requests
import msal

from django.contrib.auth import get_user_model
from django.conf import settings


app = msal.ConfidentialClientApplication(
    settings.GRAPH_API_CLIENT_ID, authority=settings.GRAPH_API_AUTHORITY,
    client_credential=settings.GRAPH_API_SECRET,
)

def acquire_graph_access_token():
    result = None

    # Firstly, looks up a token from cache
    # Since we are looking for token for the current app, NOT for an end user,
    # notice we give account parameter as None.
    result = app.acquire_token_silent(settings.GRAPH_API_SCOPE, account=None)

    if not result:
        print("No suitable token exists in cache. Let's get a new one from AAD.")
        result = app.acquire_token_for_client(scopes=[settings.GRAPH_API_SCOPE])

    if "access_token" in result:
        return result['access_token']
    else:
        print(result.get("error"))
        print(result.get("error_description"))
        print(result.get("correlation_id"))  # You may need this when reporting a bug
        return None

def search_users(q):
    token = acquire_graph_access_token()
    results = requests.get(
        settings.GRAPH_API_ENDPOINT,
        headers={
            'Authorization': f'Bearer {token}',
            'ConsistencyLevel': 'eventual'
        },
        params={
            '$select': 'givenName,surname,mail,mailNickname,employeeId,OnPremisesExtensionAttributes',
            #'$search': f'displayName:{q}'
            '$search': "\"displayName:" + q + "\""
        }
    )
    return results

def search_or_create_users(q):
    objs = []
    graph_resp = search_users(q)
    graph_resp = json.loads(graph_resp.text)
    for graph_u in graph_resp["value"]:
        if graph_u.get('givenName', '') is not None and graph_u.get('surname', '') is not None:
            try:
                class_year = graph_u.get('onPremisesExtensionAttributes').get('extensionAttribute2', [None])
            except IndexError:
                class_year = None
            try:
                class_year = int('20' + class_year)  #Graph only provides final two digits of class year 
            except (ValueError, TypeError):
                class_year = None
            given_name = graph_u.get('givenName', '')
            last_name = graph_u.get('surname', '')
            u, created = get_user_model().objects.get_or_create(
                username=graph_u['mailNickname'],
                defaults={
                    'email': graph_u.get('mail', [False]) or graph_u['mailNickname'][0] + "@wpi.edu",
                    'first_name': given_name,
                    'last_name': last_name,
                    'class_year': class_year,
                }
            )
            objs.append(u)
    return objs
