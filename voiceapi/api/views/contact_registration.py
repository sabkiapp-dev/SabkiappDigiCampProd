from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.http import JsonResponse
from django.core.exceptions import ValidationError
from django.db.models import Q
import re

from ..models.contacts import Contacts, phone_number_validator
from ..models.phone_dialer import PhoneDialer
from ..models.campaign import Campaign


# API Key to Campaign Mapping
# Each user has ONE fixed "Contact Registration" campaign
# Add entries as needed: "api_key": {"user_id": X, "campaign_id": Y}
API_KEY_TO_CAMPAIGN = {
    # Example:
    # "user1_api_key_abc123": {"user_id": 1001, "campaign_id": 1000000100},
    # "user2_api_key_xyz789": {"user_id": 1002, "campaign_id": 1000000101},
}


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
        "gender": "M",                # optional
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

    # Step 2: Validate api_key and get user_id, campaign_id
    if api_key not in API_KEY_TO_CAMPAIGN:
        return Response(
            {"status": "error", "message": "No associated campaign found"},
            status=status.HTTP_401_UNAUTHORIZED
        )

    mapping = API_KEY_TO_CAMPAIGN[api_key]
    user_id = mapping['user_id']
    campaign_id = mapping['campaign_id']

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
    gender = request.data.get('gender')
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
            existing_contact.gender = gender if gender else existing_contact.gender
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
            gender=gender,
            category_1=category_1,
            category_2=category_2,
            category_3=category_3,
            category_4=category_4,
            category_5=category_5,
            status=1
        )

    # Step 7: Create PhoneDialer record
    phone_dialer = PhoneDialer.objects.create(
        phone_number=phone_number,
        user_id=user_id,
        campaign_id=campaign_id,
        sent_status=0,  # Queued for calling
        name=name,
        gender=gender,
        trials=campaign.allow_repeat,
        ref_no=None,
        channel_name=None,
        surveyor_name=None,
        call_through=None,
        block_trials=0
    )

    # Step 8: Return success
    return Response({
        "status": "success",
        "message": "Contact added and queued for call",
        "phone_dialer_id": phone_dialer.id
    }, status=status.HTTP_200_OK)
