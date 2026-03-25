from django.shortcuts import render
from django.contrib.auth import authenticate, login
from django.http import JsonResponse



from ..models.users import Users
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
from django.contrib.auth.hashers import make_password
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.tokens import UntypedToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from ..utils import auth_wrapper 
from rest_framework import status
from django.http import JsonResponse, HttpResponseNotAllowed
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from rest_framework.exceptions import NotFound
from django.db import transaction
from src.sabkiapp_server import get_user_id


@api_view(['POST'])
@csrf_exempt
@authentication_classes(())
@permission_classes([])
@transaction.atomic
def signup(request):
    if request.method == "POST":
        data = json.loads(request.body.decode('utf-8'))
        
        mobile_number = data.get('mobile_number')
        password = data.get('password')
        name = data.get('name')
        status = data.get('status')
        
        # Get the Authorization header
        auth_header = request.headers.get('Authorization')
        referred_by = None
        
        if auth_header:
            # Extract the token
            token = auth_header.split(' ')[1]
            try:
                # Validate the token
                UntypedToken(token)
                # Get the user associated with the token
                jwt_auth_class = JWTAuthentication()
                validated_token = jwt_auth_class.get_validated_token(token)
                referred_by = jwt_auth_class.get_user(validated_token)
                if not referred_by.is_superuser:
                    return JsonResponse({"message": "You are not a superuser"}, status=401)
            except (InvalidToken, TokenError):
                return JsonResponse({"message": "Invalid token"}, status=401)
        else:
            return JsonResponse({"message": "Authorization header is required"}, status=401)
        
        user_id = get_user_id(mobile_number)
        print("user_id : ", user_id)
        if not user_id:
            return JsonResponse({"message": "User id not found in sabkiapp"}, status=400)
        
        # If the user is already registered, return an error
        if Users.objects.filter(mobile_number=mobile_number).exists():
            return JsonResponse({"message": "A user with this mobile number already exists."}, status=400)
        
        # If the user)id is already found in Users table then return an error
        if Users.objects.filter(id=user_id).exists():
            return JsonResponse({"message": f"A user with user_id {user_id} already exists."}, status=400)
        


        try: 
            user = Users.objects.create_user(
                id=user_id,
                mobile_number=mobile_number, 
                password=password, 
                name=name, 
                status=status,
                ref_id=referred_by
            )
            return JsonResponse({"message": "User created successfully!"})
        except IntegrityError:
            return JsonResponse({"message": "A user with this mobile number already exists."}, status=400)
        
from rest_framework.decorators import api_view



@csrf_exempt
@api_view(['POST'])

def signin(request):
    print("Signin In...")
    if request.method == "POST":
        data = json.loads(request.body.decode('utf-8'))
        
        mobile_number = data.get('mobile_number')
        password = data.get('password')
        
        # Try to fetch the user by mobile_number
        try:
            user = Users.objects.exclude(status=0).get(mobile_number=mobile_number)
        except Users.DoesNotExist:
            return JsonResponse({"message": "Invalid credentials, please contact admin!"}, status=400)

        # Check if the provided password matches the user's password
        if check_password(password, user.password):
            # User is authenticated, now generate JWT tokens
            refresh = RefreshToken.for_user(user)
            access_token = str(refresh.access_token)
            
            is_superuser = user.is_superuser
            return JsonResponse({"message": "Login successful!", "is_superuser": is_superuser, "access_token": access_token})
        else:
            return JsonResponse({"message": "Invalid credentials, please contact admin!"}, status=400)
    else:
        # Handle any non-POST requests here
        return HttpResponseNotAllowed(['POST'], "This endpoint only supports POST requests.")

@csrf_exempt
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def reset_password(request):
    if request.method == "POST":
        data = json.loads(request.body.decode('utf-8')) 
        
        mobile_number = data.get('mobile_number')
        new_password = data.get('password')
        
        try:
            user = Users.objects.get(mobile_number=mobile_number)
        except Users.DoesNotExist:
            return JsonResponse({"message": "User does not exist"}, status=400)
        
        # Hash the new password before saving it to the database
        hashed_password = make_password(new_password)
        user.password = hashed_password
        user.save()
        
        return JsonResponse({"message": "Password reset successfully!"})
    



@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def change_password(request):
    if request.method == "POST":
        user_id = auth_wrapper(request)
    if not user_id:
        return Response({"message": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)
    
    user = Users.objects.get(id = user_id)

    data = json.loads(request.body.decode('utf-8')) 
    old_password     = data.get("old_password")
    new_password = data.get("new_password")

    print ("user.password : "+ user.password)
    if not check_password(old_password, user.password):
        return JsonResponse({"message": "Invalid Old Password"}, status=400)
    

    # Hash the new password before saving it to the database
    hashed_password = make_password(new_password)
    user.password = hashed_password
    user.save()
    
    return JsonResponse({"message": "Password reset successfully!"})



@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def generate_api_key(request):
    # Get the user from the bearer token
    user = request.user

    # Generate a new token
    token_generator = PasswordResetTokenGenerator()
    api_key = token_generator.make_token(user)

    # Store the token in the user's api_key field
    user.api_key = api_key
    user.save()

    # Return the token in the response
    return Response({'api_key': api_key})



@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def get_api_key(request):
    # Get the user from the bearer token
    user = request.user

    # Check if the user has an api_key
    if not user.api_key:
        raise NotFound('API key not found for this user.')

    # Return the user's api_key in the response
    return Response({'api_key': user.api_key})