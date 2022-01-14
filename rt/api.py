import requests
import filetype
from django.conf import settings
from base64 import b64encode
from urllib.parse import quote


# API Methods
host = 'https://lnl-rt.wpi.edu/rt/REST/2.0/'

# Documentation for most of the endpoints used here can be found at: https://github.com/bestpractical/rt-extension-rest2


def api_request(method, endpoint, data=None, token=None):
    """
    Send an API request to the RT server

    :param method: `GET`, `POST`, `PUT`, or `DELETE`
    :param endpoint: RT endpoint
    :param data: JSON data (if applicable)
    :param token: RT Auth Token (uses the General account token if `None`)
    :return: Response
    """

    if not token:
        token = settings.RT_TOKEN
    headers = {"Content-Type": "application/json", "Authorization": "token " + token}
    if method.lower() == 'get':
        response = requests.get(endpoint, headers=headers)
        if response.status_code != 500:
            return response.json()
        return {"message": "An unknown error occurred"}
    elif method.lower() == 'post':
        if data:
            response = requests.post(endpoint, json=data, headers=headers)
            if response.status_code != 500:
                return response.json()
            return {"message": "An unknown error occurred"}
        return {"message": "Bad request"}
    elif method.lower() == 'put':
        if data:
            response = requests.put(endpoint, json=data, headers=headers)
            if response.status_code != 500:
                return response.json()
            return {"message": "An unknown error occurred"}
        return {"message": "Bad request"}


def permission_error(response):
    """
    Check if a request to RT was rejected due to a lack of permissions

    :param response: The response from RT
    :return: True if the request was rejected
    """

    if any(message in "Permission Denied" for message in response):
        return True
    if type(response) is not list:
        if response.get('message', '') == 'Unauthorized':
            return True
    return False


def create_ticket(queue, reporter, subject, content, html=False, cc=None, attachments=None):
    """
    Create a new ticket in RT

    :param queue: The ticket queue to send the ticket to
    :param reporter: Email address of the user submitting the ticket
    :param subject: Brief subject line for quick reference
    :param content: The contents of the ticket
    :param html: If true, will set ContentType to text/html instead of text/plain
    :param cc: List of additional email addresses to include in the ticket [Optional]
    :param attachments: A list of attachments to include [Optional]
    :return: API response
    """

    endpoint = host + 'ticket'
    payload = {
        "Subject": subject,
        "Queue": queue,
        "Requestor": reporter,
        "Content": content,
        "ContentType": "text/plain"
    }
    if cc:
        payload["Cc"] = ','.join(cc)
    if html:
        payload["ContentType"] = "text/html"
    if attachments:
        files = []
        for attachment in attachments:
            ft = filetype.guess(attachment)
            if ft:
                mime_type = ft.mime
            else:
                mime_type = "application/octet-stream"
            attachment.seek(0)
            file_contents = b64encode(attachment.read()).decode('utf-8')
            files.append({"FileName": attachment.name, "FileType": mime_type, "FileContent": file_contents})
        payload["Attachments"] = files
    return api_request('POST', endpoint, payload)


def fetch_ticket(ticket_id):
    """
    Retrieve a ticket from RT

    :param ticket_id: The ticket's ID #
    :return: Dictionary of ticket information
    """

    endpoint = host + 'ticket/' + str(ticket_id)
    return api_request('GET', endpoint)


def update_ticket(ticket_id, token, status=None, owner=None):
    """
    Update a ticket's metadata in RT

    :param ticket_id: The ticket's ID #
    :param token: Auth token to authenticate the request with
    :param status: The new status to assign to the ticket (if applicable). Must match the available options in RT.
    :param owner: The email address of the user to assign the ticket to (if applicable)
    :return: API response
    """

    if not status and not owner:
        return ['No change']

    endpoint = host + 'ticket/' + str(ticket_id)
    payload = {
        "Owner": owner,
        "Status": status
    }
    return api_request('PUT', endpoint, payload, token=token)


def ticket_comment(ticket_id, comments, notify=False, token=None):
    """
    Comment on a ticket in RT

    :param ticket_id: The ticket's ID #
    :param comments: Comments to add to the ticket
    :param notify: If True, comments will also be sent to watchers via email
    :param token: Provide token if available (Comment will be posted anonymously otherwise)
    :return: API response
    """

    endpoint = host + 'ticket/' + str(ticket_id) + '/comment'
    if notify:
        endpoint = endpoint.replace('/comment', '/correspond')
    payload = {
        "Content": comments,
        "ContentType": "text/plain"
    }
    return api_request('POST', endpoint, payload, token=token)


def ticket_history(ticket_id, simple=True, token=None):
    """
    Retrieve ticket history information from RT

    :param ticket_id: The ticket's ID #
    :param simple: If False, the response will contain more detailed information
    :param token: RT Auth Token (uses the General account token if not provided)
    :return: Dictionary - Contains a list of dictionaries with ticket history information
    """

    if not token:
        token = settings.RT_TOKEN

    headers = {"Content-Type": "application/json", "Authorization": "token " + token}
    if simple:
        endpoint = host.replace('2.0', '1.0') + 'ticket/' + str(ticket_id) + '/history'
        response = requests.get(endpoint, headers=headers)

        # Parse the response
        try:
            records = response.content.split(b'\n\n')[2].split(b'\n')
            history = []
            for record in records:
                history.append({"id": record.split(b': ')[0], "description": record.split(b': ')[1]})
        except IndexError:
            # Return an error message
            try:
                if response.content.index(b'Error: ') == 0:
                    return {"message": response.content.split(b'Error: ')[1].replace(b'\n', b' ')}
            except ValueError:
                pass
            return {"message": "%s Unable to retrieve ticket history." % response.content.decode('utf-8')}
    else:
        endpoint = host.replace('2.0', '1.0') + 'ticket/' + str(ticket_id) + '/history?format=l'
        response = requests.get(endpoint, headers=headers)

        # Parse the response
        try:
            records = response.content.split(b'--\n\n#')
            history = []
            for record in records:
                data = {}
                fields = [("type", b"Type: "), ("description", b"Description: "), ("field", b"Field: "),
                          ("old", b"OldValue: "), ("new", b"NewValue: "), ("user", b"Creator: "), ("datetime", b"Created: ")]
                for key, field in fields:
                    data[key] = record[record.index(field):].split(b'\n')[0].split(b': ')[1]
                content = record[record.index(b'Content: '):].split(b'Creator: ')[0].split(b': ')[1]
                content = b" ".join(b" ".join(content.splitlines()).split())
                data["content"] = content
                history.append(data)
        except ValueError:
            # Return an error message
            try:
                if response.content.index(b'Error: ') == 0:
                    return {"message": response.content.split(b'Error: ')[1].replace(b'\n', b' ')}
            except ValueError:
                pass
            return {"message": "%s Unable to retrieve ticket history." % response.content.decode('utf-8')}
    return {"transactions": history}


def simple_ticket_search(requestor=None, owner=None, queue=None, status=None):
    """
    Search for tickets in RT. You must provide a value for at least one of the following: `requestor`, `owner`, `queue`

    :param requestor: Email address of the user that submitted the tickets
    :param owner: Email address of the user the tickets have been assigned to
    :param queue: Name of the RT queue (i.e. `Database`, `Repairs`, etc.)
    :param status: Filter by ticket status (i.e. `New`, `Open`, `__Active__`, etc.) [Optional]
    :return: A list of ticket ids
    """

    if not requestor and not owner and not queue:
        raise ValueError("1 or more required fields are missing")

    query = []

    if requestor:
        query.append("Requestor.EmailAddress = '" + requestor + "'")
    if owner:
        query.append("Owner.EmailAddress = '" + owner + "'")
    if queue:
        query.append("Queue = '" + queue + "'")
    if status:
        query.append("Status = '" + status + "'")

    return search_tickets(" AND ".join(query))


def search_tickets(query):
    """
    Obtain a list of RT tickets matching the specified query (works with pagination)

    :param query: The TicketSQL query to use for the search
    :return: A list of ticket ids
    """

    ids = []

    results = api_request('GET', host + "tickets?query=" + quote(query))
    if results.get('message', None):
        return []
    done = False
    while not done:
        for item in results['items']:
            ids.append(int(item['id']))
        if 'next_page' in results:
            results = api_request('GET', results['next_page'])
        else:
            done = True
    return sorted(ids)


def get_user(username, token):
    """
    Obtain user profile from RT

    :param username: Username to use in search
    :param token: Valid auth token with the proper permissions
    :return: User profile (JSON) or None if not found
    """

    query = [{
        "field": "Name",
        "operator": "=",
        "value": username
    }]

    try:
        results = api_request('POST', host + 'users', query, token=token)
        url = results['items'][0]['_url']
    except KeyError or IndexError:
        return None

    return api_request('GET', url, token=token)
