from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.http import JsonResponse
from ..models import Users, UserHosts
from ..serializers import UserSerializer , UserHostsSerializer
import json
from django.views.decorators.http import require_http_methods
from rest_framework.permissions import IsAuthenticated
from django.views.decorators.csrf import csrf_exempt
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.tokens import RefreshToken


@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([])
def get_referred_users(request):
    # Ensure the request is authenticated
    if not request.user.is_authenticated:
        return JsonResponse({"message": "Authentication credentials were not provided."}, status=401)
    
    # Ensure the requesting user is a superuser
    if not request.user.is_superuser:
        return JsonResponse({"message": "You are not a superuser."}, status=403)
    
    # Get the list of users referred by the requesting user
    referred_users = Users.objects.filter(ref_id=request.user.id)
    
    # Serialize the list of referred users
    serializer = UserSerializer(referred_users, many=True)
    for user in serializer.data:
        queryset = UserHosts.objects.filter(user_id = user["id"])
        user["hosts"] = UserHostsSerializer(queryset,many=True).data
    # Return the serialized data
    return Response(serializer.data) 


@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([])
def change_user_status(request):
    # Ensure the request is authenticated
    if not request.user.is_authenticated:
        return JsonResponse({"message": "Authentication credentials were not provided."}, status=401)
    
    # Ensure the requesting user is a superuser
    if not request.user.is_superuser:
        return JsonResponse({"message": "You are not a superuser."}, status=403)

    # Parse request body
    try:
        mobile_number = request.data.get('mobile_number')
        new_status = request.data.get('status')
        
        if mobile_number is None or new_status is None:
            return JsonResponse({"message": "Mobile number and status are required."}, status=400)

        # Retrieve the user with the given mobile_number
        try:
            user = Users.objects.get(mobile_number=mobile_number)
        except Users.DoesNotExist:
            return JsonResponse({"message": "User not found."}, status=404)
        
        # Update the user's status
        user.status = new_status
        user.save(update_fields=['status'])

        # Return success response
        return JsonResponse({"message": "User status updated successfully."}, status=200)

    except Exception as e:
        # Handle unexpected errors
        return JsonResponse({"message": str(e)}, status=500)




@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def change_host(request):
    try:
        data = request.data
        mobile_number = data.get('mobile_number')
        new_host = data.get('host')

        if not mobile_number or not new_host:
            return Response({"message": "Mobile number and new host are required."}, status=400)

        if request.user.mobile_number != mobile_number:
            return Response({"message": "You do not have permission to change this user's host."}, status=403)

        try:
            user = Users.objects.get(mobile_number=mobile_number)
            user.host = new_host
            user.save()
            return Response({"message": "Host updated successfully."})
        except Users.DoesNotExist:
            return Response({"message": "User not found."}, status=404)
    except json.JSONDecodeError:
        return Response({"message": "Invalid JSON."}, status=400)
    


@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def get_user_token(request, user_id):
    # Get the Authorization header
    auth_header = request.headers.get('Authorization')
    if auth_header:
        # Extract the token
        token = auth_header.split(' ')[1]
        try:
            # Validate the token
            jwt_auth_class = JWTAuthentication()
            validated_token = jwt_auth_class.get_validated_token(token)
            # Get the user associated with the token
            user = jwt_auth_class.get_user(validated_token)
            if not user.is_superuser:
                return JsonResponse({"message": "Invalid token"}, status=401)
        
            # Get the user with the given user_id
            try:
                user = Users.objects.get(id=user_id)
         
                refresh = RefreshToken.for_user(user)
                access_token = refresh.access_token
                # Return the new token
                return JsonResponse({"token": str(access_token), "name":user.name}, status=200)
            except Users.DoesNotExist:
                return JsonResponse({"message": "User not found"}, status=404)

        except InvalidToken:
            return JsonResponse({"message": "Invalid token"}, status=401)
    else:
        return JsonResponse({"message": "Authorization header is required"}, status=401)