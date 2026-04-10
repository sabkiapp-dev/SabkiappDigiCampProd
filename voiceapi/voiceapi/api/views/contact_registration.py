from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response
from rest_framework import status
from django.http import JsonResponse
from django.core.exceptions import ValidationError
from django.db.models import Q
import re

from ..models.contacts import Contacts, phone_number_validator
from ..models.phone_dialer import PhoneDialer
from ..models.campaign import Campaign
from ..models.api_key_mapping import ApiKeyMapping
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import IsAuthenticated
from ..utils import auth_wrapper
import secrets


def clean_phone_number(phone_number):
    """
    Clean phone number by removing prefixes:
    +91, 91, leading 0
    Returns cleaned 10-digit number or None if invalid
    """
    if not phone_number:
        return None

    phone_number = str(phone_number).strip()

    # Strip '+91' if length is 13
    if len(phone_number) == 13 and phone_number.startswith('+91'):
        phone_number = phone_number[3:]

    # Strip '91' if length is 12
    elif len(phone_number) == 12 and phone_number.startswith('91'):
        phone_number = phone_number[2:]

    # Strip leading '0' if length > 10
    elif len(phone_number) > 10 and phone_number.startswith('0'):
        phone_number = phone_number[1:]

    # Validate: must be exactly 10 digits, starting with 6-9
    if re.match(r'^[6-9]\d{9}$', phone_number):
        return phone_number

    return None


@api_view(['POST'])
def add_contact(request):
    """
    API to add a contact to a campaign for auto-trigger calling.

    Request Body:
    {
        "api_key": "user_api_key",
        "phone_number": "9876543210",
        "name": "John Doe",           # optional
        "category_1": "Maharashtra",   # optional, default "Others"
        "category_2": "Mumbai",       # optional, default "Others"
        "category_3": "Worli",        # optional, default "Others"
        "category_4": "S28A001P0001", # optional, default "Others"
        "category_5": "ZFG0576132"    # optional, default "Others"
    }

    Response:
    {
        "status": "success",
        "message": "Contact added and queued for call",
        "phone_dialer_id": 12345
    }
    """

    # Step 1: Get api_key from request
    api_key = request.data.get('api_key')

    if not api_key:
        return Response(
            {"status": "error", "message": "api_key is required"},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Step 2: Look up api_key in database
    try:
        mapping = ApiKeyMapping.objects.get(api_key=api_key, is_active=True)
        user_id = mapping.user_id
        campaign_id = mapping.campaign_id
    except ApiKeyMapping.DoesNotExist:
        return Response(
            {"status": "error", "message": "Invalid or inactive API key"},
            status=status.HTTP_401_UNAUTHORIZED
        )

    # Step 3: Validate phone_number
    phone_number = clean_phone_number(request.data.get('phone_number'))

    if not phone_number:
        return Response(
            {"status": "error", "message": "Invalid phone number"},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Step 4: Check campaign is active
    try:
        campaign = Campaign.objects.get(id=campaign_id)
        if campaign.status != 1:
            return Response(
                {"status": "error", "message": "Associated campaign is not active"},
                status=status.HTTP_400_BAD_REQUEST
            )
    except Campaign.DoesNotExist:
        return Response(
            {"status": "error", "message": "Associated campaign not found"},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Step 5: Get optional fields
    name = request.data.get('name')
    category_1 = request.data.get('category_1', 'Others') or 'Others'
    category_2 = request.data.get('category_2', 'Others') or 'Others'
    category_3 = request.data.get('category_3', 'Others') or 'Others'
    category_4 = request.data.get('category_4', 'Others') or 'Others'
    category_5 = request.data.get('category_5', 'Others') or 'Others'

    # Step 6: Create or Update Contacts record
    existing_contact = Contacts.objects.filter(
        phone_number=phone_number,
        user_id=user_id
    ).first()

    if existing_contact:
        # Update existing contact if status is 0 (deleted)
        if existing_contact.status == 0:
            existing_contact.delete()
        else:
            # Update fields
            existing_contact.name = name if name else existing_contact.name
            # gender field removed
            existing_contact.category_1 = category_1
            existing_contact.category_2 = category_2
            existing_contact.category_3 = category_3
            existing_contact.category_4 = category_4
            existing_contact.category_5 = category_5
            existing_contact.status = 1
            existing_contact.save()
            contact = existing_contact
    else:
        # Create new contact
        contact = Contacts.objects.create(
            phone_number=phone_number,
            user_id=user_id,
            name=name,
            category_1=category_1,
            category_2=category_2,
            category_3=category_3,
            category_4=category_4,
            category_5=category_5,
            status=1
        )

    # Step 7: Delete existing PhoneDialer record if exists (to update + reset queue)
    PhoneDialer.objects.filter(
        campaign_id=campaign_id,
        phone_number=phone_number
    ).delete()

    # Step 8: Create PhoneDialer record
    phone_dialer = PhoneDialer.objects.create(
        phone_number=phone_number,
        user_id=user_id,
        campaign_id=campaign_id,
        sent_status=0,  # Queued for calling
        name=name,
        trials=campaign.allow_repeat,
        ref_no=None,
        channel_name=None,
        surveyor_name=None,
        call_through=None,
        block_trials=0
    )

    # Step 9: Return success
    return Response({
        "status": "success",
        "message": "Contact added and queued for call",
        "phone_dialer_id": phone_dialer.id
    }, status=status.HTTP_200_OK)


# =============================================================================
# API Key Management Endpoints (Admin)
# =============================================================================

@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def create_api_key(request):
    """
    Create a new API key mapping for a campaign.
    Requires JWT authentication.

    Request Body:
    {
        "user_id": 1,
        "campaign_id": 1000000001,
        "description": "My App"  // optional
    }

    Response:
    {
        "status": "success",
        "api_key": "abc123...",
        "user_id": 1,
        "campaign_id": 1000000001
    }
    """
    user_id = auth_wrapper(request)
    if not user_id:
        return Response({"message": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)

    user_id_param = request.data.get('user_id')
    campaign_id = request.data.get('campaign_id')
    description = request.data.get('description', '')

    if not user_id_param or not campaign_id:
        return Response(
            {"status": "error", "message": "user_id and campaign_id are required"},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        user_id_param = int(user_id_param)
        campaign_id = int(campaign_id)
    except (ValueError, TypeError):
        return Response(
            {"status": "error", "message": "user_id and campaign_id must be integers"},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Validate campaign exists and belongs to user
    try:
        campaign = Campaign.objects.get(id=campaign_id, user_id=user_id_param)
    except Campaign.DoesNotExist:
        return Response(
            {"status": "error", "message": "Campaign not found or does not belong to user"},
            status=status.HTTP_404_NOT_FOUND
        )

    # Generate API key
    api_key = secrets.token_hex(24)

    # Create mapping
    mapping = ApiKeyMapping.objects.create(
        api_key=api_key,
        user_id=user_id_param,
        campaign_id=campaign_id,
        description=description,
        is_active=True
    )

    return Response({
        "status": "success",
        "api_key": api_key,
        "user_id": user_id_param,
        "campaign_id": campaign_id,
        "description": description
    }, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def list_api_keys(request):
    """
    List all API key mappings for the authenticated user.
    Requires JWT authentication.

    Response:
    {
        "api_keys": [
            {"api_key": "...", "user_id": 1, "campaign_id": 1, "description": "...", "is_active": true}
        ]
    }
    """
    user_id = auth_wrapper(request)
    if not user_id:
        return Response({"message": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)

    # Get all mappings for any user (admin view) or just current user
    # For now, show all mappings
    mappings = ApiKeyMapping.objects.all().order_by('-id')

    result = []
    for m in mappings:
        result.append({
            "api_key": m.api_key,
            "user_id": m.user_id,
            "campaign_id": m.campaign_id,
            "description": m.description,
            "is_active": m.is_active
        })

    return Response({"api_keys": result})


@api_view(['DELETE'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def delete_api_key(request):
    """
    Delete an API key mapping.
    Requires JWT authentication.

    Request Body:
    {
        "api_key": "abc123..."
    }
    """
    user_id = auth_wrapper(request)
    if not user_id:
        return Response({"message": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)

    api_key = request.data.get('api_key')
    if not api_key:
        return Response(
            {"status": "error", "message": "api_key is required"},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        mapping = ApiKeyMapping.objects.get(api_key=api_key)
        mapping.delete()
        return Response({"status": "success", "message": "API key deleted"})
    except ApiKeyMapping.DoesNotExist:
        return Response(
            {"status": "error", "message": "API key not found"},
            status=status.HTTP_404_NOT_FOUND
        )
