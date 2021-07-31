import requests
import filetype
from django.conf import settings
from base64 import b64encode


# API Methods
host = 'https://lnl-rt.wpi.edu/rt/REST/2.0/'


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
        return None

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
