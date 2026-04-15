# views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.decorators import authentication_classes, permission_classes
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import IsAuthenticated
from ..serializers import VoicesSerializer, UpdateVoiceSerializer
from django.core.files.storage import default_storage
from ..models.campaign import Campaign
from ..models.voices import Voices
import os
from ..utils import auth_wrapper 
from django.db.models import Q
from django.core.paginator import Paginator, EmptyPage
from rest_framework.decorators import api_view
from django.db import IntegrityError
import sys



@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def add_audio(request):
    user = request.user
    # data = request.data.copy()
    data = request.data
    print("data--", data)
    data['user'] = user.id
    serializer = VoicesSerializer(data=data)
    print("serializer--", serializer)
    if serializer.is_valid():
        voice = serializer.save()
        print("voice--", voice)
        return Response({
            "message": "Voice Added Successfully",
            "voice": serializer.data
        }, status=status.HTTP_200_OK)
    # Extracting the first error message from the serializer errors
    error_message = list(serializer.errors.values())[0][0]
    print("error_message--", error_message)
    return Response({"message": error_message}, status=status.HTTP_400_BAD_REQUEST)



@api_view(['PUT'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def update_voice(request):
    user = request.user
    data = request.data.copy()
    data['user'] = user.id
    try:
        # Retrieve the voice instance
        voice = Voices.objects.get(id=data.get('id'), user=user)
    except Voices.DoesNotExist:
        return Response({"message": "Voice not found"}, status=status.HTTP_404_NOT_FOUND)
    
    # Get id, name and description from data json
    voice_id = data.get('id')
    voice_name = data.get('voice_name')

    voice_desc = data.get('voice_desc')
    print(voice_id, voice_name, voice_desc)
    if len(voice_name) > 255:
            return Response({"message": "Name greater than 255 characters limit"}, status=status.HTTP_400_BAD_REQUEST)
    # Check if the voice name and description are provided
    if voice_name is None or voice_desc is None:
        return Response({"message": "Voice name and description are required."}, status=status.HTTP_400_BAD_REQUEST)
    
    # Update the voice name and description
    voice.voice_name = voice_name
    voice.voice_desc = voice_desc
    try:
        voice.save(update_fields=['voice_name', 'voice_desc'])
    except IntegrityError:
        return Response({"message": "A voice with this name already exists for the user."}, status=status.HTTP_400_BAD_REQUEST)

    return Response({"message": "Voice Updated Successfully"}, status=status.HTTP_200_OK)


@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@api_view(['GET'])
def voices(request):
    search_query = request.GET.get('search', '')
    order = request.GET.get('order', 'id desc')
    page_number = request.GET.get('page', 1)
    page_size = request.GET.get('page_size', 25)
    status_param = request.GET.get('status', None)

    # Get the user_id from the token
    user_id = auth_wrapper(request)

    voices = Voices.objects.filter(user_id=user_id)
    if search_query:
        voices = voices.filter(
            Q(voice_name__icontains=search_query) | Q(voice_desc__icontains=search_query)
        )
    if status_param == '1':
        voices = voices.filter(status=1)

    # Split the order parameter into field and direction
    field, direction = order.split()

    # If direction is 'desc', prepend the field name with '-'
    if direction.lower() == 'desc':
        field = '-' + field

    voices = voices.order_by(field)

    paginator = Paginator(voices, page_size)  # Show 20 voices per page

    try:
        page = paginator.page(page_number)
    except EmptyPage:
        # If the page is out of range, return an empty list
        voices_list = []
    else:
        voices_list = list(page.object_list.values('id', 'voice_name', 'voice_desc', 'path', 'status'))

    return Response({
        'current_page': page.number if voices_list else None,
        'total_pages': paginator.num_pages,
        'data': voices_list,
        'message': "Voices Retrieved Successfully" if voices_list else "Data not found"
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def update_audio_status(request):
    # extract user_id from token
    user_id = auth_wrapper(request)
    if not user_id:
        return Response({"message": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)
    # Extract the voice_id and new_status from the request data
    voice_id = request.data.get('voice_id')
    new_status = request.data.get('status')

    # Check if the voice_id and new_status are provided
    if voice_id is None or new_status is None:
        return Response({"message": "Voice ID and status are required."}, status=status.HTTP_400_BAD_REQUEST)
    
    # Retrieve the voice with the given voice_id for the user
    try:
        voice = Voices.objects.get(id=voice_id, user_id=user_id)
    except Voices.DoesNotExist:
        return Response({"message": "Voice not found."}, status=status.HTTP_404_NOT_FOUND)
    
    # Update the voice's status
    voice.status = new_status
    voice.save(update_fields=['status'])

    # Return success response
    return Response({"message": "Voice status updated successfully."}, status=status.HTTP_200_OK)