from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response
from rest_framework import status
from ..models.sms_template import SmsTemplate
from ..models.user_hosts import UserHosts
from ..utils import auth_wrapper 
from ..models.contacts import Contacts
from django.shortcuts import get_object_or_404
from django.db import transaction
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.permissions import AllowAny
from ..views.gateway_status import fetch_gateway_status
from src.mytime import get_mytime
import re
from django.conf import settings
import requests
from src.sabkiapp_server import get_name
import json
from django.core.exceptions import ObjectDoesNotExist
from ..models import SmsDialer
from datetime import timedelta
from django.db.models import Q
from rest_framework.renderers import JSONRenderer
from ..views.sms_dialer import sms_dialer_instant
import time
import threading
from src.sms_message import get_sms_message
from src.sms_counter import SmsCounter





def send_sms_thread():
    time.sleep(1)
    sms_dialer_instant()

@api_view(['POST'])
def send_sms(request):
    user_id = request.data.get('user_id')
    host = request.data.get('host')
    system_password = request.data.get('system_password')
    template_id = request.data.get('template_id')
    phone_number = request.data.get('phone_number')

    if not re.match(r'^[9|8|7|6]\d{9}$', str(phone_number)):
        return Response({"message": "Invalid phone number"}, status=status.HTTP_400_BAD_REQUEST)

    print(f"user_id={user_id}, host={host}, system_password={system_password}, message={template_id}, phone_number={phone_number}")

    # Validate the data
    if not all([user_id, host, system_password, template_id, phone_number]):
        return Response({"message": "All fields are required"}, status=status.HTTP_400_BAD_REQUEST)

    # Check if the user_id, host, and system_password combination exists in the UserHosts table
    try:
        user_host = UserHosts.objects.get(user_id=user_id, host=host, system_password=system_password, status=1)
    except ObjectDoesNotExist:
        return Response({"message": "Invalid user_id, host, or system_password"}, status=status.HTTP_400_BAD_REQUEST)
    
    # Check status of template_id from sms_template table
    try:
        sms_template = SmsTemplate.objects.get(user_id=user_id, id=template_id, status=1)
    except ObjectDoesNotExist:
        return Response({"message": "Invalid template_id"}, status=status.HTTP_400_BAD_REQUEST)
    
    
    print("user_host --: ", user_host)
    try:
        sms_sent = SmsDialer.objects.filter(
            Q(phone_number=phone_number, sms_template_id=template_id, sms_campaign_id=None, sent_status=0) |
            (Q(phone_number=phone_number, sms_template_id=template_id, sms_campaign_id=None, sent_datetime__gte=get_mytime() - timedelta(hours=1)) & ~Q(sent_status=0))
        ).exists()
        
        if sms_sent:
            # Create a new thread and start it
            thread = threading.Thread(target=send_sms_thread)
            thread.start()
            return Response({"message": "SMS already sent to this number"}, status=status.HTTP_400_BAD_REQUEST)
        else:
            print("sms_sent-- 2: ", sms_sent)
            sms_message = get_sms_message(user_id, template_id, phone_number)
            sms_count = SmsCounter.count(sms_message)["sms_count"]
            SmsDialer.objects.create(phone_number=phone_number, sms_template_id=template_id, user_id=user_id, sms_sent=sms_message, sms_count=sms_count)

            # Create a new thread and start it
            thread = threading.Thread(target=send_sms_thread)
            thread.start()
            return Response({"message": "SMS added to the queue"}, status=status.HTTP_200_OK)
    except Exception as e:
        print(f"Exception occurred while fetching sms_dialer: {e}")
        return Response({"message": "Error occurred while fetching sms_dialer"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)








