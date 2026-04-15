import json
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
# JWT auth for SabkiApp
from api.auth.service_jwt import ServiceJWTAuthentication
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import IsAuthenticated
from ..models.campaign import Campaign
from ..models.call_dtmf_status import CallDtmfStatus
from ..models.voices import Voices
from ..models.contacts import Contacts
from ..models.phone_dialer import PhoneDialer
from ..models.users import Users
from ..serializers import CampaignSerializer, UserHostsSerializer, DialPlanSerializer
from ..serializers import ApiPhoneDialerSerializer
from ..models.dial_plan import DialPlan
from ..models.user_hosts import UserHosts
from ..models.active_campaign_hosts import ActiveCampaignHosts
from django.core.exceptions import ValidationError
# Assuming the auth_wrapper returns the user_id
from ..utils import auth_wrapper 
from rest_framework.exceptions import ErrorDetail
from django.core.paginator import Paginator, EmptyPage
from django.db.models import Q
from django.http import JsonResponse
from django.core.exceptions import ObjectDoesNotExist
import requests
from django.forms.models import model_to_dict
from src.mytime import get_mytime
import re
from datetime import timedelta, datetime
from django.conf import settings
from ..models.misscall_management import MisscallManagement
from ..models.misscalls import Misscalls
from ..models.call_status import CallStatus
from ..models.sim_information import SimInformation
from src.sabkiapp_server import get_name
import threading
from django.db.models import Avg
from django.db.models import Max
from django.db.models import Count
from django.db.models import Subquery, OuterRef
from rest_framework.status import HTTP_200_OK, HTTP_400_BAD_REQUEST, HTTP_404_NOT_FOUND
import os
import pandas as pd
from django.http import FileResponse, HttpResponse
import csv
from collections import OrderedDict
from datetime import datetime
from src.sabkiapp_server import store_misscall_on_sabkiapp
from django.db.models import Prefetch
from django.db import transaction
from ..models.error_verify_phone_dialer import ErrorVerifyPhoneDialer



@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def campaign_detail(request, campaign_id):
    user_id = auth_wrapper(request)
    if not user_id:
        return Response({"message": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)

    try:
        campaign = Campaign.objects.get(id=campaign_id, user_id=user_id)
        user_hosts = UserHosts.objects.filter(user_id=user_id, status=1)
        
        if not user_hosts.exists():
            return Response({"message": "No hosts found for this user"}, status=status.HTTP_204_NO_CONTENT)

        campaign_serializer = CampaignSerializer(campaign)

        hosts = []
        for host in user_hosts:
            host_data = {'id': host.id, 'host': host.host}
            try:
                active_campaign_host = ActiveCampaignHosts.objects.get(campaign=campaign, host=host)
                host_data['status'] = active_campaign_host.status
            except ActiveCampaignHosts.DoesNotExist:
                host_data['status'] = 0
            hosts.append(host_data)

        campaign_data = campaign_serializer.data
        campaign_data['hosts'] = hosts
      

        return Response(campaign_data, status=status.HTTP_200_OK)

    except ObjectDoesNotExist:
        return Response({"message": "Data not found"}, status=status.HTTP_204_NO_CONTENT)


@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def add_campaign(request):
    print("Add Campaign")
    user_id = auth_wrapper(request)
    if not user_id:
        return Response({"message": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)
    
    data = request.data
    data["user"] = user_id  # Change "user_id" to "user"
    # if status is in the data then remove it from the data
    if 'status' in request.data:
        del request.data['status']
    serializer = CampaignSerializer(data=data)

    if serializer.is_valid():
        try:
            serializer.save()
            return Response({"message": "Campaign Added Successfully", "data": serializer.data}, status=status.HTTP_200_OK)
        except ValidationError as e:
            if 'name' in str(e) and 'user' in str(e):
                return Response({"message": f"This Campaign name {data['name']}, already exists"}, status=status.HTTP_400_BAD_REQUEST)
    else:
        if 'non_field_errors' in serializer.errors:
            for error in serializer.errors['non_field_errors']:
                if 'name' in error and 'user' in error:
                    error = {'non_field_errors': [str(ErrorDetail(string='This campaign name already exists.', code='unique'))]}
                    return Response(error, status=status.HTTP_400_BAD_REQUEST)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['PUT'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def update_campaign(request):
    user_id = auth_wrapper(request)
    if not user_id:
        return Response({"message": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)

    data = request.data
    campaign_id = data.get("id")
    # if status is in the data then remove it from the data
    if 'status' in request.data:
        del request.data['status']
    try:
        campaign = Campaign.objects.get(id=campaign_id, user_id=user_id)
    except Campaign.DoesNotExist:
        return Response({"message": "Campaign not found"}, status=status.HTTP_404_NOT_FOUND)

    serializer = CampaignSerializer(campaign, data=data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response({"message": "Campaign updated successfully"}, status=status.HTTP_200_OK)
    else:
        if 'non_field_errors' in serializer.errors:
            return Response({"message": "The campaign name already exists"}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({"message": "Invalid data"}, status=status.HTTP_400_BAD_REQUEST)



@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def campaigns(request):
    user_id = auth_wrapper(request)
    if not user_id:
        return Response({"message": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)

    search_query = request.GET.get('search', '')
    order = request.GET.get('order', 'id desc')
    page_number = request.GET.get('page', 1)
    page_size   = request.GET.get('page_size', 25)
    
    if search_query:
        campaigns = Campaign.objects.filter(
            Q(user_id=user_id) & 
            (Q(name__icontains=search_query) | Q(campaign_priority__icontains=search_query))
        )
    else:
        campaigns = Campaign.objects.filter(user_id=user_id)

    # Split the order parameter into field and direction
    field, direction = order.split()

    # If 'priority' is sent, consider it 'campaign_priority'
    if field.lower() == 'priority':
        field = 'campaign_priority'

    # If direction is 'desc', prepend the field name with '-'
    if direction.lower() == 'desc':
        field = '-' + field
    campaigns = campaigns.order_by(field)

    paginator = Paginator(campaigns, page_size)  # Show 20 campaigns per page

    try:
        page = paginator.page(page_number)
    except EmptyPage:
        # If the page is out of range, return an empty list
        campaigns_list = []
    else:
        campaigns_list = []
    for campaign in page.object_list:
        campaigns_list.append({
            'id': campaign.id,
            'name': campaign.name,
            'campaign_priority': campaign.campaign_priority,
            'description': campaign.description,
            'created_at': campaign.created_at,
            'modified_at': campaign.modified_at,
            'start_date': campaign.start_date,
            'end_date': campaign.end_date,
            'start_time': campaign.start_time,
            'end_time': campaign.end_time,
            'call_cut_time': campaign.call_cut_time,
            'status': campaign.status,
            'language': campaign.get_language_display(),
            'name_spell': campaign.name_spell,
            'contacts_count': campaign.contacts_count,
            'allow_repeat': campaign.allow_repeat,
        })
    return Response({
        'current_page': page.number if campaigns_list else None,
        'total_pages': paginator.num_pages,
        'data': campaigns_list,
        'message': "Campaign Retrieved Successfully" if campaigns_list else "Data not found"
    }, status=status.HTTP_200_OK)

 

@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def update_campaign_audio(request):
    user_id = auth_wrapper(request)
    if not user_id:
        return Response({"message": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)

    data = request.data
    campaign_id = data.get('campaign_id')

    # check if the campaign exists for the user
    try:
        campaign = Campaign.objects.get(id=campaign_id, user_id=user_id)
    except Campaign.DoesNotExist:
        return Response({"message": "Campaign not found"}, status=status.HTTP_404_NOT_FOUND)
    
    # Check if wrong_key_voice and no_key_voice in Voices table for the user
    if 'wrong_key_voice' in data:
        wrong_key_voice = data['wrong_key_voice']
        try:
            if wrong_key_voice:
                voice = Voices.objects.get(id=wrong_key_voice, user_id=user_id)
                campaign.wrong_key_voice = voice
            else:
                campaign.wrong_key_voice = None
        except Voices.DoesNotExist:
            return Response({"message": "Wrong Key Voice not found"}, status=status.HTTP_404_NOT_FOUND)

    if 'no_key_voice' in data:
        no_key_voice = data['no_key_voice']
        try:
            if no_key_voice:
                voice = Voices.objects.get(id=no_key_voice, user_id=user_id)
                campaign.no_key_voice = voice
            else:
                campaign.no_key_voice = None
        except Voices.DoesNotExist:
            return Response({"message": "No Key Voice not found"}, status=status.HTTP_404_NOT_FOUND)

    
    campaign.save(update_fields=['wrong_key_voice', 'no_key_voice'])

    return Response({"message": "Campaign Audio updated successfully"}, status=status.HTTP_200_OK)

@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def update_campaign_status(request):
    user_id = auth_wrapper(request)
    if not user_id:
        return Response({"message": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)

    data = request.data
    campaign_id = data.get('id')
    campaign_status = data.get('status')

    # If campaign_status not between 1 and 5, return error
    if campaign_status not in [0, 1, 2, 4, 5]:
        return Response({"message": "Invalid status"}, status=status.HTTP_400_BAD_REQUEST)
    # check if the campaign exists for the user
    try:
        campaign = Campaign.objects.get(id=campaign_id, user_id=user_id)
    except Campaign.DoesNotExist:
        return Response({"message": "Campaign not found"}, status=status.HTTP_404_NOT_FOUND)
    
    # conditions to update the status 
    # If status is not 0 and campaign_status is 0, do not update the status

    if campaign_status == 0 and campaign.status != 0:
        return Response({"message": "Campaign status cannot be updated to 0"}, status=status.HTTP_400_BAD_REQUEST)
    

    if campaign_status == 5 and campaign.status != 0:
        return Response({"message": "Campaign status cannot be updated to 5"}, status=status.HTTP_400_BAD_REQUEST)
    
    
    if campaign_status == 4:
        PhoneDialer.objects.filter(campaign_id=campaign_id, sent_status=0).update(sent_status=4)

    # If campaign_status is 2, and campaign.status !=1, return error
    if campaign_status == 2 and campaign.status != 1:
        return Response({"message": "Campaign status cannot be updated to 2"}, status=status.HTTP_400_BAD_REQUEST) 
    # Check if campaign.status is 0 and campaign_status is 5
    
    # If campaign status is 1 and campaign_status is 0, return error
    if campaign_status == 1 and campaign.status == 0:
        return Response({"message": "Campaign status cannot be updated to 1"}, status=status.HTTP_400_BAD_REQUEST)
    
    if campaign_status == 1 and campaign.status == 4:
        PhoneDialer.objects.filter(campaign_id=campaign_id, sent_status=4).update(sent_status=0) 
        
    # If campaign status 
    if campaign_status == 5 and campaign.status == 0 :
        # Find in DialPlan for the campaign_id
        dialplans = DialPlan.objects.filter(campaign_id=campaign.id)
        name_spell_values = [dialplan.name_spell for dialplan in dialplans]

        # Check name_spell column
        if all(value == 0 for value in name_spell_values):
            # If all are 0, do nothing
            pass
        elif all(value in [0, 1] for value in name_spell_values):
            # If all 0 or 1, update 1 in campaigns table
            campaign.name_spell = 1
        elif all(value in [0, 2] for value in name_spell_values):
            # If all 0 or 2, update 2 in campaigns table
            campaign.name_spell = 2
        elif any(value == 1 for value in name_spell_values) and any(value == 2 for value in name_spell_values):
            # If both 1 and 2 are present, update 3 in campaigns table
            campaign.name_spell = 3
        
        # If any dialplan is empty, that is if main voice and option voice are both null, delete that dialplan
        DialPlan.objects.filter(campaign_id=campaign.id, main_voice_id=None, option_voice_id=None, name_spell=0).delete()


    # update the status of the campaign
    campaign.status = campaign_status
    campaign.save()

    return Response({"message": "Campaign status updated successfully"}, status=status.HTTP_200_OK)

from multiprocessing import Pool
from itertools import islice
from functools import partial

from django import db

from concurrent.futures import ThreadPoolExecutor

def process_contact(campaign_id, contact_id):
    db.connections.close_all()
    campaign = Campaign.objects.get(id=campaign_id)
    contact = Contacts.objects.get(id=contact_id)
    if not PhoneDialer.objects.filter(phone_number=contact.phone_number, campaign=campaign).exists():
        PhoneDialer.objects.create(
            phone_number=contact.phone_number,
            user_id=contact.user_id, 
            campaign=campaign,
            name=contact.name,
        )


@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def add_contacts_to_campaign(request):
    user_id = auth_wrapper(request)
    if not user_id:
        return Response({"message": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)

    # Extract data from request
    campaign_id = request.data.get('campaign_id')
    categories = {f'category_{i}': request.data.get(f'category_{i}', []) for i in range(1, 6)}

    # Check if the campaign exists for the user
    try:
        campaign = Campaign.objects.exclude(status__in=[0, 4]).get(id=campaign_id, user_id=user_id)
    except Campaign.DoesNotExist:
        return Response({"message": "Campaign not found"}, status=status.HTTP_404_NOT_FOUND)

    # Prepare category queries
    category_queries = []
    for category, values in categories.items():
        category_query = Q()
        for value in values:
            category_query |= Q(**{f'{category}__exact': value.strip()})
        category_queries.append(category_query)

    # Combine category queries with AND condition
    final_query = category_queries[0]
    for query in category_queries[1:]:
        final_query &= query


    # Get contacts based on categories and add them to PhoneDialer
    contacts = Contacts.objects.filter(user_id=user_id, status=1).filter(final_query)
 

    # Count the number of PhoneDialer entries with the same campaign_id before adding contacts
    contacts_count_before = PhoneDialer.objects.filter(campaign=campaign).count()

    
    with ThreadPoolExecutor() as executor:
        for contact in contacts:
            executor.submit(process_contact, campaign.id, contact.id)


    # Count the number of PhoneDialer entries with the same campaign_id after adding contacts
    contacts_count_after = PhoneDialer.objects.filter(campaign=campaign).count()

    # Update contacts_count in the Campaign table
    campaign.contacts_count = contacts_count_after
    # If any contact was added, update campaign status to 1
    if contacts_count_after > contacts_count_before:
        campaign.status = 1
    campaign.save()
    # return contacts added message 
    return Response({"message": "Contacts added to campaign successfully", "contacts_count":campaign.contacts_count}, status=status.HTTP_200_OK)





@authentication_classes([])
@permission_classes([])
@api_view(['GET'])
def add_to_phone_dialer(request):
    def process_request(request):
        # Extract data from request
        api_key = request.GET.get('api_key')
        phone_number = request.GET.get('phone_number')
        name = request.GET.get('name')
        # print("hello adding to phone_dialer : ", api_key, phone_number)c
        # If api key is not present, return error
        if not api_key:
            return JsonResponse({"message":"API Key not found"})

        
        
        phone_number = request.GET.get('phone_number')

        if not phone_number:
            return JsonResponse({"message": "Phone number not found"})

        # --- NEW PHONE NUMBER CLEANING LOGIC ---
        
        # 1. Strip '+91' if the length is exactly 13
        if len(phone_number) == 13 and phone_number.startswith('+91'):
            phone_number = phone_number[3:]
            
        # 2. Strip '91' if the length is exactly 12
        elif len(phone_number) == 12 and phone_number.startswith('91'):
            phone_number = phone_number[2:]
            
        # 3. Strip leading '0' (Your original logic)
        elif len(phone_number) > 10 and phone_number.startswith('0'):
            phone_number = phone_number[1:]

        # --- END CLEANING LOGIC ---

        # Now check if the remaining string is a valid 10-digit Indian number
        if not re.match(r'^[6-9]\d{9}$', phone_number):
            # If using threading, remember to use print() or logging.error() here instead!
            return JsonResponse({"message": "Invalid phone number. Must have 10 digits and start with a digit greater than 5"})
       
       
        # send misscall to sabkiapp
        operator = request.GET.get('operator')
        if not operator:
            return JsonResponse({"message":"Operator is required"}, status=400)
            # If operator equals to 07941050749  then check in sim_info table for the operator
        if operator == "07941050749":
            sim_info = SimInformation.objects.filter(phone_no=phone_number).first()
            if sim_info:
                SimInformation.objects.filter(phone_no=phone_number).update(today_block_status=0)
                return JsonResponse({"message":"Status updated to 0 successfully"})
        if api_key == settings.API_KEY_RETURN_MISS_CALL:
            sim_info = SimInformation.objects.filter(phone_no=phone_number).first()
            if sim_info:
                SimInformation.objects.filter(phone_no=phone_number).update(today_block_status=0)
                return JsonResponse({"message":"Status updated to 0 successfully"})
            else:
                phone_dialer = PhoneDialer.objects.filter(sent_status__in=[2,5], phone_number=phone_number, sent_datetime__isnull=False, sent_datetime__gte=get_mytime()-timedelta(days=2)).order_by('-sent_datetime').first()
                if not phone_dialer:
                    return JsonResponse({"message":"No data found"}, status=400)
                campaign_id = phone_dialer.campaign_id
                #if phone_dialers has a status=0,1,3,4,5 for campaign_id, return error
                if PhoneDialer.objects.filter(campaign_id=campaign_id, phone_number=phone_number, sent_status__in=[1, 3, 4]).exists():
                    return JsonResponse({"message":"Data already exists with sent_status 0, 1, 3, 4."})
                try:
                    campaign = Campaign.objects.exclude(status__in=[0, 4]).get(id=campaign_id)
                except Campaign.DoesNotExist:
                    return Response({"message": "Campaign not found"}, status=status.HTTP_404_NOT_FOUND)

                
                # Check if the phone_number with same campaign_id and sent_status=0 already exists
                existing_phone_dialer = PhoneDialer.objects.filter(phone_number=phone_number, campaign_id=campaign_id, sent_status=0).first()
                if existing_phone_dialer:
                    # delete existing_phone_dialer
                    existing_phone_dialer.delete()

                phone_dialer.sent_status = 0
                phone_dialer.sent_datetime = get_mytime()
                phone_dialer.save()

                # Count the number of PhoneDialer entries with the same campaign_id before adding contacts
                contacts_count_before = PhoneDialer.objects.filter(campaign=campaign).count()

                # Count the number of PhoneDialer entries with the same campaign_id after adding contacts
                contacts_count_after = PhoneDialer.objects.filter(campaign=campaign).count()

                # Update contacts_count in the Campaign table
                campaign.contacts_count = contacts_count_after
                # If any contact was added, update campaign status to 1
                if campaign.status == 3:
                    campaign.status = 1
                campaign.save()
                return JsonResponse({"message":"Data added successfully"})
        
        else:

            try:
                user = Users.objects.get(api_key=api_key)
            except Users.DoesNotExist:
                
                return JsonResponse({"message":"Invalid API Key"})
            
            if(user):
                user_id = user.id
            else:
                return JsonResponse({"message":"User not found"})

            campaign_id = request.GET.get('campaign_id')
           
            try:
                misscall_management = MisscallManagement.objects.filter(user_id=user_id,operator=operator, status=1).latest('id')
                campaign_id = misscall_management.campaign_associated.id
                misscall_management_id = misscall_management.management_id
            except MisscallManagement.DoesNotExist:
                misscall_management_id = 0
                store_misscall_response = store_misscall_on_sabkiapp(phone_number, misscall_management_id, operator, user.id)
                return JsonResponse({"message":"Operator not found"})
            
            if not campaign_id:
                campaign_id = misscall_management.campaign_associated.id
            
            # If user is None or user.id is not matching with misscall_management.user_id, return error
            if not user or user.id != misscall_management.user_id:
                return JsonResponse({"message":"User not found or unauthorized"})
            
            store_misscall_response = store_misscall_on_sabkiapp(phone_number, misscall_management_id, operator, user.id)
    
            
            # Find campaign from Campaigns table using campaign_id
            try:
                campaign = Campaign.objects.exclude(status__in=[0, 4]).get(id=campaign_id, user_id=user.id)
            except Campaign.DoesNotExist:
                return Response({"message": "Campaign not found"}, status=status.HTTP_404_NOT_FOUND)

            try:
                existing_phone_dialer = PhoneDialer.objects.get(phone_number=phone_number, campaign=campaign, sent_status=0)
                if(existing_phone_dialer):
                    existing_phone_dialer.sent_datetime = get_mytime()
                    existing_phone_dialer.save()
                    misscall = Misscalls(phone_number=phone_number, datetime=get_mytime(), misscall_management=misscall_management, campaign_id=None)
                    misscall.save()
                    return JsonResponse({"message":"Data already exists with sent_status 0."})
            except PhoneDialer.DoesNotExist:
                pass  # If PhoneDialer does not exist, do nothing
                
            # If name is empty or None, check the name from the contacts table with the phone_number amd user_id and status=1
            if not name:
                try:
                    contact = Contacts.objects.get(phone_number=phone_number, user_id=user.id, status=1)
                    name = contact.name
                    print("name1 : ", name)
                    # If still name is None, send an api request to get the name and if response not 200, pass
                    if not name:
                        names = get_name(user.id, [phone_number])
                        name = names.get(phone_number)
                        print("name2 : ", name)
                except Contacts.DoesNotExist:
                    name = None
            

            # Add contact to misscalls table
            misscall = Misscalls(phone_number=phone_number, datetime=get_mytime(), misscall_management=misscall_management, campaign_id=campaign_id)
            misscall.save()

            # Check if the phone_number is in Contacts table, if not add it
            if not Contacts.objects.filter(phone_number=phone_number, user_id=user.id).exists():
                # if name is none, make it empty
                if not name:
                    name = ""
                contact = Contacts(phone_number=phone_number, user_id=user.id, name=name, status=1, category_1="misscall", category_2=operator, category_3=get_mytime().date(), category_4=campaign_id, category_5="Others")
                contact.save()
            else:
                # if status =0, update name if name is none in object and status = 1 
                contact = Contacts.objects.get(phone_number=phone_number, user_id=user.id)
                if contact.status == 0:
                    # delete the contact and add it again
                    contact.delete()
                    contact = Contacts(phone_number=phone_number, user_id=user.id, name=name, status=1, category_1="misscall", category_2=operator, category_3=get_mytime().date(), category_4=campaign_id, category_5="Others")
                    contact.save()
                elif contact.status == 1 and not contact.name:
                    contact.name = name
                    print("name3 ", name)
                    contact.save()
            # Count the number of PhoneDialer entries with the same campaign_id before adding contacts
            contacts_count_before = PhoneDialer.objects.filter(campaign=campaign).count()

            phone_dialer = PhoneDialer(phone_number=phone_number, user=user, campaign=campaign, name=name, trials=campaign.allow_repeat)
            phone_dialer.save()

            # Count the number of PhoneDialer entries with the same campaign_id after adding contacts
            contacts_count_after = PhoneDialer.objects.filter(campaign=campaign).count()

            # Update contacts_count in the Campaign table
            campaign.contacts_count = contacts_count_after
            # If any contact was added, update campaign status to 1
            if contacts_count_after > contacts_count_before and campaign.status == 3:
                campaign.status = 1
            campaign.save()

            return JsonResponse({"message":"Data added successfully"})
    # Create a thread that processes the request
    thread = threading.Thread(target=process_request, args=(request,))
    thread.start()

    # Return a response
    return JsonResponse({"message": "Api hit successfully."})


@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def update_active_campaign_host(request):
    user_id = auth_wrapper(request)
    if not user_id:
        return Response({"message": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)

    campaign_id = request.data.get('campaign_id')
    host_id = request.data.get('host_id')
    active_status = request.data.get('status')

    if not all([campaign_id, host_id, active_status is not None]):
        return Response({"message": "Missing required data"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        campaign = Campaign.objects.get(id=campaign_id, user_id=user_id)
        print("campaign : ", campaign)
        host = UserHosts.objects.get(id=host_id, user_id=user_id, status=1)
        print("host : ", host)

        if active_status == 1:    
            serializer = CampaignSerializer(campaign)
            
            dial_plans = DialPlan.objects.filter(campaign__id=campaign_id, campaign__user=user_id)
            dp_serializer = DialPlanSerializer(dial_plans, many=True)
        
            body = {
                "host": host.host,
                "system_password": UserHostsSerializer(host).data["system_password"],
                "campaign": serializer.data["id"],
                "timeout":serializer.data["call_cut_time"],
                "no_key_voice": serializer.data["no_key_voice"],
                "wrong_key_voice": serializer.data["wrong_key_voice"],
                "data": dp_serializer.data,
            }
            
            print("body : ", json.dumps(body, indent=4))
            
            response = requests.post(f"https://{host.host}.sabkiapp.com/save_dial_plan", json=body)

            if response.status_code != 200:
                return Response({"message": "Machine is offline"}, status=400)

        active_campaign_host, created = ActiveCampaignHosts.objects.get_or_create(
            campaign=campaign, host=host, defaults={'status': active_status})

        if not created:
            active_campaign_host.status = active_status
            active_campaign_host.save()

        print("active_campaign_host : ", active_campaign_host)

        return Response({"message": "Active campaign host updated successfully"}, status=status.HTTP_200_OK)

    except ObjectDoesNotExist:
        return Response({"message": "Data not found"}, status=status.HTTP_204_NO_CONTENT)

@api_view(['POST'])
@authentication_classes([ServiceJWTAuthentication])
@permission_classes([])
def verify_add_to_phone_dialer(request):
    """
    Ingests call request JSON, requiring:
      - name
      - phone_number (10 digits, starts with 6-9)
      - channel_name
      - surveyor_name
      - language
    
    Authenticated via SabkiApp RS-256 service JWT.
    """
    data = request.data.copy()

    # 1) Required field validation
    required_fields = [
        'ref_no',          # idempotency key (can be empty but must exist)
        'name',
        'phone_number',
        'channel_name',
        'surveyor_name',
        'language',
    ]
    missing_fields = [f for f in required_fields if f not in data]
    if missing_fields:
        return Response(
            {'detail': f'Missing required fields: {", ".join(missing_fields)}'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # 2) Phone-number format validation (10 digits, starts with 6-9)
    if not re.match(r'^[6-9]\d{9}$', str(data['phone_number'])):
        return Response(
            {'detail': 'phone_number must be 10 digits and start with 6-9.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # 3) Field-length constraints
    length_errors = {}
    if data.get("ref_no") and len(str(data["ref_no"])) > 255:
        length_errors["ref_no"] = "Must be ≤ 255 characters."
    for field in ("name", "channel_name", "surveyor_name"):
        if data.get(field) and len(str(data[field])) > 60:
            length_errors[field] = "Must be ≤ 60 characters."
    if length_errors:
        return Response(
            {"detail": "Invalid data", "errors": length_errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # 4) De-duplicate by ref_no (if provided)
    ref_no = data.get('ref_no')
    if ref_no and PhoneDialer.objects.filter(ref_no=ref_no).exists():
        return Response(
            {'detail': f'Reference number already exists: {ref_no}'},
            status=status.HTTP_200_OK
        )

    # 5) Language validation & mapping
    LANGUAGE_CAMPAIGN_MAP = {
        'en': 1000000089, 'hi': 1000000088, 'or': 1000000087,
        'mr': 1000000086, 'ta': 1000000085, 'te': 1000000084,
        'gu': 1000000083, 'kn': 1000000082, 'ml': 1000000081,
        'pa': 1000000080, 'bn': 1000000079, 'as': 1000000078,
    }
    lang = data['language']
    camp = LANGUAGE_CAMPAIGN_MAP.get(lang)
    if camp is None:
        return Response(
            {'detail': f'Unsupported language code: {lang}'},
            status=status.HTTP_400_BAD_REQUEST
        )
    data['campaign'] = camp  # match the model FK name
    SABKIAPP_USER_ID = 10006666
    data['user'] = SABKIAPP_USER_ID

    # 9) Serialize & save
    serializer = ApiPhoneDialerSerializer(data=data)
    if not serializer.is_valid():
        return Response(
            {'detail': 'Invalid data', 'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    serializer.save()
    return Response(serializer.data, status=status.HTTP_200_OK)

def extensions_pressed_recent(campaign_id):
    dialplans = DialPlan.objects.filter(campaign_id=campaign_id)
    extensions_pressed_recent = {}
    for dialplan in dialplans:
        extension_info = {}
        for i in range(10):
            dtmf_value = getattr(dialplan, f'dtmf_{i}')
            if dtmf_value is not None:
                # Count the number of dtmf pressed from CallDtmfStatus table
                count = CallDtmfStatus.objects.filter(
                    call_id__campaign_id=campaign_id,
                    extension=dialplan.extension_id,
                    dtmf_response=i
                ).count()
                extension_info[f'dtmf_{i}'] = count
        # Only add the extension if extension_info is not empty
        if extension_info:
            extensions_pressed_recent[f'extension_{dialplan.extension_id}'] = extension_info
    return extensions_pressed_recent

def extension_possible_values(campaign_id):
    dialplans = DialPlan.objects.filter(campaign_id=campaign_id)
    extensions_pressed_recent = {}
    for dialplan in dialplans:
        extension_info = {}
        for i in range(10):
            dtmf_value = getattr(dialplan, f'dtmf_{i}')
            if dtmf_value is not None:
                extension_info[f'dtmf_{i}'] = 0
        # Only add the extension if extension_info is not empty
        if extension_info:
            extensions_pressed_recent[f'extension_{dialplan.extension_id}'] = extension_info

    return extensions_pressed_recent

def average_call_duration(campaign_id):
    return PhoneDialer.objects.filter(sent_status=5, campaign_id=campaign_id).aggregate(Avg('duration'))['duration__avg'] or 0

@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def campaign_summary_report(request):
    # Get the user_id from the request
    user_id = auth_wrapper(request)
    if not user_id:
        return Response({"message": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)
    # Get campaign_id from request data
    campaign_id = request.data.get('campaign_id')
    if not campaign_id:
        return Response({"message": "Campaign ID not found"}, status=status.HTTP_400_BAD_REQUEST)
    
    # If campaign_id not associated with the user 
    try:
        campaign = Campaign.objects.get(id=campaign_id, user_id=user_id)
    except Campaign.DoesNotExist:
        return Response({"message": "Campaign not found or not associated with this user"}, status=status.HTTP_404_NOT_FOUND)
    

    phone_dialers = PhoneDialer.objects.filter(campaign_id=campaign_id)
    average_call_duration_answered = average_call_duration(campaign_id=campaign_id)
    total_calls_unique = phone_dialers.aggregate(unique_phone_count=Count('phone_number', distinct=True))['unique_phone_count']
    answered_calls_unique = phone_dialers.filter(sent_status=5).annotate(unique_phone=Count('phone_number', distinct=True)).count()
    ongoing_calls = phone_dialers.filter(Q(sent_status=1) | Q(sent_status=3)).count()
    grouped_phone_dialers = phone_dialers.values('phone_number').annotate(sent_status=Max('sent_status'))
    unanswered_calls = grouped_phone_dialers.filter(sent_status=2).count()
    to_be_dialed = phone_dialers.filter(sent_status=0).count()
    cancelled_calls = phone_dialers.filter(sent_status=4).count()

    
    calls_duration_0_to_10 = PhoneDialer.objects.filter(sent_status=5, campaign_id=campaign_id, duration__range=(0, 10)).count()
    calls_duration_11_to_20 = PhoneDialer.objects.filter(sent_status=5, campaign_id=campaign_id,duration__range=(11, 20)).count()
    calls_duration_21_to_30 = PhoneDialer.objects.filter(sent_status=5, campaign_id=campaign_id, duration__range=(21, 30)).count()
    calls_duration_31_to_40 = PhoneDialer.objects.filter(sent_status=5, campaign_id=campaign_id, duration__range=(31, 40)).count()
    calls_duration_41_to_50 = PhoneDialer.objects.filter(sent_status=5, campaign_id=campaign_id, duration__range=(41, 50)).count()
    calls_duration_51_to_60 = PhoneDialer.objects.filter(sent_status=5, campaign_id=campaign_id, duration__range=(51, 60)).count()
    calls_duration_61_to_90 = PhoneDialer.objects.filter(sent_status=5, campaign_id=campaign_id, duration__range=(61, 90)).count()
    calls_duration_91_to_120 = PhoneDialer.objects.filter(sent_status=5, campaign_id=campaign_id, duration__range=(91, 120)).count()
    calls_duration_121_plus = PhoneDialer.objects.filter(sent_status=5, campaign_id=campaign_id, duration__gt=120).count()
    
       
    


    # Update the summary_report dictionary
    summary_report = {
        "total_calls_unique": total_calls_unique,
        "answered_calls_unique": answered_calls_unique,
        "ongoing_calls": ongoing_calls,
        "unanswered_calls": unanswered_calls,
        "to_be_dialed": to_be_dialed,
        "cancelled_calls": cancelled_calls,
        "average_call_duration_answered": average_call_duration_answered,
        "calls_duration_0_to_10": calls_duration_0_to_10,
        "calls_duration_11_to_20": calls_duration_11_to_20,
        "calls_duration_21_to_30": calls_duration_21_to_30,
        "calls_duration_31_to_40": calls_duration_31_to_40,
        "calls_duration_41_to_50": calls_duration_41_to_50,
        "calls_duration_51_to_60": calls_duration_51_to_60,
        "calls_duration_61_to_90": calls_duration_61_to_90,
        "calls_duration_91_to_120": calls_duration_91_to_120,
        "calls_duration_121_plus": calls_duration_121_plus,
        "extensions_pressed_recent": extensions_pressed_recent(campaign_id)
    }

    data = {
        "summary_report": summary_report
    }

    # return the data
    return Response(data, status=status.HTTP_200_OK)






def get_campaign_detail_data(campaign_id, page_number=None, page_size=None, complete_data=False):
    phone_dialers = PhoneDialer.objects.filter(campaign_id=campaign_id)
    total_pages = 0
    if not complete_data:
        paginator = Paginator(phone_dialers, page_size)
        total_pages = paginator.num_pages
        try:
            phone_dialers = paginator.page(page_number)
        except EmptyPage:
            phone_dialers = paginator.page(paginator.num_pages)
        phone_dialers_list = list(phone_dialers)
        phone_dialers = PhoneDialer.objects.filter(id__in=[pd.id for pd in phone_dialers_list])

    phone_dialers = phone_dialers.prefetch_related(Prefetch('calldtmfstatus_set', queryset=CallDtmfStatus.objects.only('extension', 'dtmf_response')))

    sent_status_dict = {
        0: 'Not sent',
        1: 'In progress',
        2: 'Unanswered',
        3: 'In progress',
        4: 'Cancelled',
        5: 'Completed'
    }

    phone_dialers_data = []
    for phone_dialer in phone_dialers:
        sent_datetime = phone_dialer.sent_datetime
        if sent_datetime:
            sent_datetime = sent_datetime.strftime('%d-%b-%Y %H:%M:%S')

        sent_status = phone_dialer.sent_status
        if sent_status == 0:
            sent_datetime = None
            call_through = None
            duration = 0
        else:
            call_through = phone_dialer.call_through
            duration = phone_dialer.duration

        sent_status = sent_status_dict[sent_status]

        phone_dialer_dict = {
            'name': phone_dialer.name,
            'phone_number': phone_dialer.phone_number,
            'sent_status': sent_status,
            'sent_datetime': sent_datetime,
            'call_through': call_through,
            'duration': duration,
            'dtmf_report': [
                {
                    'extension': calldtmfstatus.extension,
                    'dtmf_response': calldtmfstatus.dtmf_response,
                }
                for calldtmfstatus in phone_dialer.calldtmfstatus_set.all()
            ],
        }
        phone_dialers_data.append(phone_dialer_dict)

    # implement here
    # Extension possible values here 
    extension_keys = extension_possible_values(campaign_id)
    for item in phone_dialers_data:
        dtmf_report = item.pop('dtmf_report', [])
        # Add all extension_keys to the item
        for key in extension_keys:
            item[key] = None
        if complete_data:
            item['S.No.'] = phone_dialers_data.index(item) + 1
        else:
            item['S.No.'] = (int(page_number) - 1) * int(page_size) + phone_dialers_data.index(item) + 1
        if dtmf_report:    
            for report in dtmf_report:
                extension_number = report.get('extension')
                dtmf_response = report.get('dtmf_response')
                # Match the extension number with the field extension_{number}
                extension_field = f'extension_{extension_number}'
                if extension_field in extension_keys:
                    item[extension_field] = dtmf_response
    data = {
        "total_pages": total_pages,
        "current_page": page_number,
        "data": phone_dialers_data
    }

    return data
  

@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def campaign_detail_report(request):
    # Get the user_id from the request
    user_id = auth_wrapper(request)
    if not user_id:
        return Response({"message": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)
    # Get campaign_id from request data
    campaign_id = request.data.get('campaign_id')
    if not campaign_id:
        return Response({"message": "Campaign ID not found"}, status=status.HTTP_400_BAD_REQUEST)
    
    # If campaign_id not associated with the user 
    try:
        campaign = Campaign.objects.get(id=campaign_id, user_id=user_id)
    except Campaign.DoesNotExist:
        return Response({"message": "Campaign not found or not associated with this user"}, status=status.HTTP_404_NOT_FOUND)
    
    page_number = request.data.get('page')
    page_size = request.data.get('page_size')
    if not page_number:
        # get from query param
        page_number = request.GET.get('page', 1)
    if not page_size:
        # get from query param
        page_size = request.GET.get('page_size', 25)

    data = get_campaign_detail_data(campaign_id, page_number, page_size)

    return Response(data, status=status.HTTP_200_OK)


def generate_csv_report(campaign_id, data):
    # Define the headers for the CSV file
    extensions = extension_possible_values(campaign_id)


    headers = ['S.No.', 'name', 'phone_number', 'sent_status',  'sent_datetime', 'call_through', 'duration']

    # Add the keys from the extensions dictionary to the headers list
    headers.extend(extensions.keys())
    data = data.get('data', [])

    # Open the CSV file in write mode
    with open(f'campaign_report_{campaign_id}.csv', 'w', newline='') as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=headers)

        # Write the headers to the CSV file
        writer.writeheader()

      
        for index, row in enumerate(data, start=1):
            # Add the serial number to the row
            row['S.No.'] = index



            # Write the row to the CSV file
            writer.writerow(row)

    return Response({"message": "CSV file generated"}, status=HTTP_200_OK)


def generate_excel_response(campaign_id, data):
    # Generate the CSV report
    csv_response = generate_csv_report(campaign_id, data)

    # Read the CSV file into a pandas DataFrame
    df = pd.read_csv(f'campaign_report_{campaign_id}.csv')

    # Write the DataFrame to an Excel file
    df.to_excel(f'campaign_report_{campaign_id}.xlsx', index=False)

    # Open the Excel file in binary mode and return it as a response
    excel_file = open(f'campaign_report_{campaign_id}.xlsx', 'rb')
    response = FileResponse(excel_file, as_attachment=True, filename=f'campaign_report_{campaign_id}.xlsx')
    return response


@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def download_campaign_report(request):
    # Get the user_id from the request
    user_id = request.user.id

    # Get campaign_id and type from the query parameters
    campaign_id = request.GET.get('campaign_id')
    report_type = request.GET.get('type')

    if not campaign_id:
        return Response({"message": "Campaign ID not provided"}, status=HTTP_400_BAD_REQUEST)

    # Check if campaign_id is associated with the user 
    try:
        campaign = Campaign.objects.get(id=campaign_id, user_id=user_id)
    except Campaign.DoesNotExist:
        return Response({"message": "Campaign not found or not associated with this user"}, status=HTTP_404_NOT_FOUND)
    
    # delete all the .xlsx and .csv files from the directory starting with campaign_report_
    files = [f for f in os.listdir('.') if os.path.isfile(f) and f.startswith('campaign_report_')]
    for file in files:
        os.remove(file)

    data = get_campaign_detail_data(campaign_id, complete_data=True)

    if report_type == 'excel':
        return generate_excel_response(campaign_id, data)
    elif report_type == 'csv':
        # Generate the CSV report
        generate_csv_report(campaign_id, data)

        # Open the CSV file in binary mode
        csv_file = open(f'campaign_report_{campaign_id}.csv', 'rb')

        # Return the CSV data as a bytes stream
        return FileResponse(csv_file, as_attachment=True, filename=f'campaign_report_{campaign_id}.csv')
    # return the data
    return Response(data, status=HTTP_200_OK)


@api_view(['DELETE'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def delete_campaign_contact(request):
    # Get the user_id from the request
    user_id = auth_wrapper(request)
    if not user_id:
        return Response({"message": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)
    
    # Find id from the request data
    id = request.data.get('id')
    if not id:
        return Response({"message": "ID not found"}, status=status.HTTP_400_BAD_REQUEST)
    
    # Get the campaign_id from the request data
    campaign_id = request.data.get('campaign_id')

    # Get the delete_all flag from the request data
    delete_all = request.data.get('delete_all', 0)

    if delete_all == 1:
        # Delete all PhoneDialer instances with sent_status=0
        PhoneDialer.objects.filter(campaign_id=campaign_id, user_id=user_id, sent_status=0).delete()
        # update campaign status to 3 using update
        Campaign.objects.filter(id=campaign_id, user_id=user_id).update(status=3)
    else:
        # Now, filter for the PhoneDialer with the given id and user_id and sent_status=0
        try:
            phone_dialer = PhoneDialer.objects.get(id=id, campaign_id=campaign_id, user_id=user_id, sent_status=0)
        except PhoneDialer.DoesNotExist:
            return Response({"message": "Unable to delete"}, status=status.HTTP_400_BAD_REQUEST)
        
        # Delete the PhoneDialer
        phone_dialer.delete()

    # Get the campaign from the PhoneDialer
    campaign = Campaign.objects.get(id=campaign_id, user_id=user_id)

    # Count the number of PhoneDialer entries with the same campaign_id
    contacts_count = PhoneDialer.objects.filter(campaign=campaign).count()

    # Update contacts_count in the Campaign table
    campaign.contacts_count = contacts_count 
    campaign.save()
    return Response({"message": "Data deleted successfully"}, status=status.HTTP_200_OK)



@api_view(['POST'])
@authentication_classes([ServiceJWTAuthentication])
@permission_classes([])
@transaction.atomic
def cancel_ref_no(request):
    """
    Cancel ALL phone-dialer rows for the given ref_no (set sent_status = 4)
    and clear any verify error-queue rows for that ref_no.
    Body: { "ref_no": "ABC123" }
    Auth: SabkiApp RS-256 service JWT
    """
    ref_no = (request.data.get('ref_no') or '').strip()
    if not ref_no:
        return Response({"detail": "ref_no is required"}, status=status.HTTP_400_BAD_REQUEST)

    # 1) Cancel all phone-dialer rows with this ref_no
    cancelled = PhoneDialer.objects.filter(ref_no=ref_no).update(sent_status=4)

    # 2) Clear verify retry-queue entries for this ref_no (if any)
    deleted_count, _ = ErrorVerifyPhoneDialer.objects.filter(ref_no=ref_no).delete()

    return Response({
        "ok": True,
        "ref_no": ref_no,
        "phone_dialer_rows_cancelled": cancelled,
        "verify_queue_rows_cleared": deleted_count,
    }, status=status.HTTP_200_OK)
