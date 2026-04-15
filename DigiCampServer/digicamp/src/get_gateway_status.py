
import requests


def get_gateway_status(user_host):
    # print("Step 4, get_gateway_status ", user_host.host)
    try:
        response = requests.get(f'https://{user_host.host}.sabkiapp.com/gateway_status', params={'host': user_host.host, 'password': user_host.system_password}, timeout=10)
        return response.json()  # return the response from the server
    except requests.exceptions.RequestException as e:
        return None
    