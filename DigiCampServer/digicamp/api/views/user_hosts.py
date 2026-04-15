from django.shortcuts import render

from django.contrib.auth import authenticate, login
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
from django.db import IntegrityError
from django.contrib.auth.hashers import check_password
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
import logging
from rest_framework.request import HttpRequest 
from ..models.user_hosts import UserHosts
from ..serializers import UserHostsSerializer, UserSerializer
from ..models.users import Users
from rest_framework import status
import requests
logger = logging.getLogger(__name__)




def change_password_for_all_hosts(new_password, hostname):
    # Update the system_password for all UserHosts where the host is the same
    UserHosts.objects.filter(host=hostname).update(system_password=new_password)

def update_password_in_machine(host, system_password, new_system_password):
    base_url = f"https://{host}.sabkiapp.com"
    api_endpoint = f"{base_url}/change_host_password"
    headers = {'Content-Type': 'application/json'}
    data = {
        "host": host,
        "system_password": system_password,
        "new_system_password": new_system_password
    }
    response = requests.post(api_endpoint, headers=headers, json=data)
 
    # Check if the API request was successful
    if response.status_code != 200:
        return Response({"message": "Failed to change host password."}, status=response.status_code)

    return Response({"message": "Host password changed successfully."}, status=status.HTTP_200_OK)


@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def user_host(request: HttpRequest):
    print("User host ")

    data = json.loads(request.body.decode("utf-8"))

    # From the token, check if user is a superuser
    if not request.user.is_superuser:
        print("Unauthorizedsss1")
        return Response({"message": "You are not authorized to add a host."}, status=400)
    
    user_id = data.get("user_id")
    host = data.get("host")
    system_password = data.get("system_password")


    # Check if the user exists
    user = Users.objects.filter(id=user_id).first()

    if not user:
        print("Unauthorizedsss2")
        return Response({"message": f"User with user_id={user_id} does not exist."}, status=400)

    # Check if the user is a superuser
    if user.is_superuser:
        print("Unauthorizedsss3")
        return Response({"message": f"Superusers are not allowed to update user hosts. Skipped for user_id={user_id}"}, status=400)

    # Check if the combination of user_id and host already exists
    user_host_instance = UserHosts.objects.filter(
        user_id=user_id,
        host=host
    ).first()

    if user_host_instance:
        print("Unauthorizedsss4")
        # Return with 400
        return Response({"message": f"Host with host={host} already exists for user_id={user_id}"}, status=400)

        # 
    else:
        # Is host exists even for another user
        existing_host = UserHosts.objects.filter(host=host).first()
        if existing_host:
          change_password_for_all_hosts(system_password, host)
          update_password_in_machine(host, existing_host.system_password, system_password)  
        # If it doesn't exist, create a new record
        serializer = UserHostsSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        return Response(serializer.data)


@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def get_hosts_by_user(request, user_id):
    # Ensure the request is authenticated
    if not request.user.is_authenticated:
        return Response({"message": "Authentication credentials were not provided."}, status=status.HTTP_401_UNAUTHORIZED)

    # Get the user by ID
    try:
        user = Users.objects.get(id=user_id)
    except Users.DoesNotExist:
        return Response({"message": "User not found."}, status=status.HTTP_404_NOT_FOUND)

    
    # Check if the requesting user is authorized to view hosts of the specified user
    if (not request.user.is_superuser) or (request.user.id == user.id):
        return Response({"message": "You are not authorized to view hosts for this user."}, status=status.HTTP_403_FORBIDDEN)

    # Serialize the user with hosts using UserSerializer
    result = UserHosts.objects.filter(user_id=user_id)
    serializer = UserHostsSerializer(result, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


# A DELETE METHOD to delete a host which accepts a host id and deletes the host
@api_view(['PUT'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def change_host_status(request):
    # Ensure the request is authenticated
    if not request.user.is_authenticated:
        return Response({"message": "Authentication credentials were not provided."}, status=status.HTTP_401_UNAUTHORIZED)

    host_id = request.query_params.get('host_id')
    # Get the host by ID
    try:
        host = UserHosts.objects.get(id=host_id)
    except UserHosts.DoesNotExist:
        return Response({"message": "Host not found."}, status=status.HTTP_404_NOT_FOUND)

    # Check if the requesting user is authorized to view hosts of the specified user
    if (not request.user.is_superuser) or (request.user.id == host.user_id.id):
        return Response({"message": "You are not authorized to view hosts for this user."}, status=status.HTTP_403_FORBIDDEN)

    # Get the new status from the query parameters
    new_status = request.query_params.get('status')
    if new_status is None:
        return Response({"message": "New status not provided."}, status=status.HTTP_400_BAD_REQUEST)

    # Update the host status
    host.status = new_status
    host.save()

    # Return the serialized data
    return Response({"message": "Host status updated successfully."}, status=status.HTTP_200_OK)



@api_view(['PUT'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def edit_host(request, host_id):
    # Ensure the request is authenticated
    if not request.user.is_authenticated:
        return Response({"message": "Authentication credentials were not provided."}, status=status.HTTP_401_UNAUTHORIZED)

    # Get the data from the request
    priority = request.data.get('priority')
    system_password = request.data.get('system_password')
    allow_sms = request.data.get('allow_sms')

    # get the host from host_id. If no host found return 404
    user_host = UserHosts.objects.filter(id=host_id)
    if not user_host:
        return Response({"message": "Host not found."}, status=status.HTTP_404_NOT_FOUND)

    # Validate the data
    if not host_id or not priority or not system_password:
        return Response({"message": "Host ID, priority, and system password are required."}, status=status.HTTP_400_BAD_REQUEST)

    user_host_instance = user_host.first()
    if user_host_instance:
        existing_host = UserHosts.objects.filter(host=user_host_instance, priority=priority, user_id=user_host_instance.user_id).first()
        if existing_host:
            user = existing_host.user
            return Response({"message": f"This priority is assigned to {user.id} and {user.name}"}, status=status.HTTP_400_BAD_REQUEST)

    # Check if the requesting user is authorized to view hosts of the specified user
    if (not request.user.is_superuser) or (request.user.id == user_host_instance.user_id):
        return Response({"message": "You are not authorized to view hosts for this user."}, status=status.HTTP_403_FORBIDDEN)

    # Check if duplicate entry is not present for userHost and priority together
    is_duplicate_priority = UserHosts.objects.exclude(user_id=user_host_instance.user_id).filter(host=user_host_instance.host, priority=priority).exists()
    if is_duplicate_priority:
        return Response({"message": "Same priority already exists for another user."}, status=status.HTTP_400_BAD_REQUEST)
    
    user_host_instance.priority = priority  # Update the priority
    user_host_instance.allow_sms = allow_sms  # Update the allow_sms
    user_host_instance.save()  # Save the changes to the database

    # Get the old host and password
    old_password = user_host_instance.system_password

    # Prepare the password
    new_password = system_password if system_password is not None and system_password != '' else old_password
    # If the password is different, update the password in the machine
    if new_password != old_password:
        response = update_password_in_machine(user_host_instance.host, old_password, new_password)
        
        # If status code is not 200, return the error message
        if response.status_code != 200:
            return response
        # Edit the host
        change_password_for_all_hosts(new_password, user_host_instance.host)
        
    # Return the serialized data
    serializer = UserHostsSerializer(user_host_instance)
    response_data = serializer.data
    response_data['system_password'] = new_password
    return Response(response_data, status=status.HTTP_200_OK)


@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def get_host_password(request):
    # Get the hostname from the query parameters
    hostname = request.query_params.get('hostname')
    if not hostname:
        return Response({"message": "Hostname not provided."}, status=status.HTTP_400_BAD_REQUEST)
    
    # check if the user is a superuser
    if not request.user.is_superuser:
        return Response({"message": "You are not authorized to view the host password."}, status=status.HTTP_403_FORBIDDEN)
    
    try:
        # Get the UserHost instance for the given hostname
        user_host_instance = UserHosts.objects.filter(host=hostname).first()
        if not user_host_instance:
            return Response({"password": ""}, status=status.HTTP_404_NOT_FOUND)
    except UserHosts.DoesNotExist:
        # If the UserHost instance does not exist, return a 404 error
        return Response({"password": ""}, status=status.HTTP_404_NOT_FOUND)

    # Return the password
    return Response({"password": user_host_instance.system_password}, status=status.HTTP_200_OK)

from threading import Thread



@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def active_hosts_status(request):
    # Get the user id from the bearer token
    user_id = request.user.id
    
    # Check if user_id is None
    if user_id is None:
        return Response({"message": "User ID not provided."}, status=status.HTTP_400_BAD_REQUEST)
    
    # List all the active hosts for the user
    user_hosts = UserHosts.objects.filter(user_id=user_id, status=1)
    print("user_hosts", user_hosts)
    
    # Define a function to fetch the status of a host
    def fetch_host_status(user_host, results):
        host = user_host.host
        print("host", host)
        # Call the API to get the host status
        response = requests.get(f'https://{host}.sabkiapp.com/tunnel_status', timeout=2)
        # Return the host status
        if response.status_code == 200:
            results.append({"host": host, "status": 1})
        else:
            results.append({"host": host, "status": 0})
    
    # Use threading to fetch the host status in parallel
    threads = []
    results = []
    for user_host in user_hosts:
        thread = Thread(target=fetch_host_status, args=(user_host, results))
        thread.start()
        threads.append(thread)

    # Wait for all threads to complete
    for thread in threads:
        thread.join()

    print("responses", results)
    return Response(results, status=status.HTTP_200_OK)