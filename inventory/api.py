import re
import json
import requests
from django.conf import settings


def api_request(method, endpoint, data=None):
    """
    Send an API request to Snipe

    :param method: `GET`, `POST`, `PUT`, `PATCH` or `DELETE`
    :param endpoint: Snipe endpoint (Must start with `/` - i.e. `/users` or `/accessories/1`)
    :param data: JSON data (if applicable)
    :return: Response
    """

    if not settings.SNIPE_URL:
        return {"status": "error", "messages": "SNIPE_URL is not set"}
    if not settings.SNIPE_API_KEY:
        return {"status": "error", "messages": "SNIPE_API_KEY is not set"}

    response = requests.request(method, '%sapi/v1%s' % (settings.SNIPE_URL, endpoint), json=data, headers={
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'Authorization': "Bearer %s" % settings.SNIPE_API_KEY
    })

    if response.status_code == 200:
        data = json.loads(response.text)
        if data.get('status', 'OK') == 'error':
            return data
        data['status'] = 'OK'
        return data
    else:
        return {"status": "error", "messages": "An unknown error occurred - Error %s" % response.status_code}


def load_rental_clients():
    """
    Retrieves a list of users in the rental group (rental clients).

    :return: List of rental clients
    """

    response = api_request('GET', '/users?group_id=3')  # The rental group currently has an id of 3

    if response['status'] == 'OK':
        return [(user['id'], user['name']) for user in response['rows']]
    return None


def get_item_info(tag):
    """
    Retrieve information about an item in LNL's inventory (supports both assets and accessories)

    :param tag: The item's asset tag number (String)
    :return: Dictionary - Item details
    """

    match = re.match('LNLACC([0-9]+)', tag)
    if match:
        # Item is an accessory
        item_id = match.group(1)
        response = api_request('GET', '/accessories/%s' % item_id)
        if response['status'] == "OK":
            response['resource_type'] = "accessory"
            response['asset_tag'] = "LNLACC" + str(response.get('id', ""))
            response['rental_cost'] = response['order_number'] if response['order_number'] is not None else "0"
    else:
        # Item is an asset
        response = api_request('GET', '/hardware/bytag/%s' % tag)
        response['resource_type'] = "asset"
        rental_price = "0"
        try:
            rental_price = response['custom_fields']['Rental Price']['value']
            if rental_price in [None, ""]:
                rental_price = "0"
        except Exception:
            pass
        response['rental_cost'] = rental_price
    return response


def checkout(item_id, renter_id, accessory=False):
    """
    Check an asset or accessory out to a user

    :param item_id: The item's Snipe ID number
    :param renter_id: The Snipe ID number for the user checking out the item
    :param accessory: Must be True if the item is an accessory
    :return: API Response
    """

    if accessory:
        return api_request('POST', '/accessories/%s/checkout' % item_id, {'assigned_to': renter_id})
    else:
        return api_request('POST', '/hardware/%s/checkout' % item_id, {'checkout_to_type': 'user',
                                                                       'assigned_user': renter_id})
