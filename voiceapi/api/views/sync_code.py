import requests
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import IsAuthenticated
from api.models.user_hosts import UserHosts
from django.core.exceptions import ObjectDoesNotExist


def call_zip_entire_code_api(host, system_password):
    url = f"https://{host}.sabkiapp.com/zip_entire_code"
    params = {
        'host': host,
        'system_password': system_password
    }

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()  # Raise an exception for 4XX or 5XX status codes
        return response.json()  # Assuming the response is JSON
    except requests.RequestException as e:
        print(f"Error calling API: {e}")
        return None  # Or handle the error as needed


def call_update_code_api(zip_file_url, host, system_password):
    # Prepare the API endpoint
    api_endpoint = f"https://{host}.sabkiapp.com/update_code"

    # Prepare the payload
    payload = {
        "zip_file_url": zip_file_url,
        "host": host,
        "system_password": system_password
    }

    # Make the POST request
    response = requests.post(api_endpoint, data=payload)

    # Return the response
    return response.json()


def get_tunnel_status(host):
    # Prepare the API endpoint
    api_endpoint = f"https://{host}.sabkiapp.com/tunnel_status"

    # Make the GET request
    response = requests.get(api_endpoint)

    # Check if the response code is 200
    if response.status_code != 200:
        return False

    # Return the response
    return response.json()

@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def sync_code(request):
    # Verify user is a superuser
    if not request.user.is_superuser:
        return Response({"message": "You are not authorized to perform this action"}, status=status.HTTP_403_FORBIDDEN)
    
    sync_from = request.data.get('sync_from')
    sync_to = request.data.get('sync_to')

    print(sync_from, sync_to)


    if not sync_from or not sync_to:
        return Response({"message": "Both sync_from and sync_to are required"}, status=status.HTTP_400_BAD_REQUEST)


    
    try:
        # Get the first object that matches the filter condition for sync_from
        first_sync_from = UserHosts.objects.filter(host=sync_from, status=1).first()
        
        # Get the first object that matches the filter condition for sync_to
        first_sync_to = UserHosts.objects.filter(host=sync_to).first()
    

        if not first_sync_from:
            return Response({"message": f"{sync_from} does not exist in UserHost table"}, status=status.HTTP_400_BAD_REQUEST)
        elif not first_sync_to:
            return Response({"message": f"{sync_to} does not exist in UserHost table"}, status=status.HTTP_400_BAD_REQUEST)
        
        
        # Get system_password for sync_from
        sync_from_system_password = first_sync_from.system_password

        # Get system_password for sync_to
        sync_to_system_password = first_sync_to.system_password

        # Get tunnel_status for sync_from
        sync_from_status = get_tunnel_status(sync_from)

        # Check if sync_from is active
        if not sync_from_status or not sync_from_status.get('status'):
            return Response({"message": f"{sync_from} is not active"}, status=status.HTTP_400_BAD_REQUEST)

        # Get tunnel_status for sync_to
        sync_to_status = get_tunnel_status(sync_to)

        # Check if sync_to is active
        if not sync_to_status or not sync_to_status.get('status'):
            return Response({"message": f"{sync_to} is not active"}, status=status.HTTP_400_BAD_REQUEST)


        # Call the zip_entire_code API
        response = call_zip_entire_code_api(sync_from, sync_from_system_password)
        if response is None:
            return Response({"message": "An error occured in calling the API"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        

        # Extract the URL from the response
        zip_file_url = response.get('url')

        print(zip_file_url)

        # Call the update_code API
        response = call_update_code_api(zip_file_url, sync_to, sync_to_system_password)
        print(response)
        
    except Exception:
        return Response({"message", "An error occured in getting sync_from or sync_to"})
    return Response({"message": "Code synced successfully"}, status=status.HTTP_200_OK)