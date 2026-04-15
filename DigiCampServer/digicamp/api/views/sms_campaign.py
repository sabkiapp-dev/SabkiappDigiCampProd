from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from src.sms_message import get_sms_message
from src.sms_counter import SmsCounter
from ..serializers import SmsCampaignSerializer, SmsDialerSerializer
from rest_framework_simplejwt.authentication import JWTAuthentication
from ..models.sms_campaign import SmsCampaign
from ..models.sms_template import SmsTemplate
from ..models.sms_dialer import SmsDialer
from django.db import IntegrityError
from django.core.paginator import Paginator, EmptyPage
from django.db.models import Q
from ..models.contacts import Contacts
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404
from ..models.sms_campaign import SmsCampaign
from django.db import IntegrityError
from rest_framework.exceptions import PermissionDenied
from django.http import Http404
from django.core.exceptions import ObjectDoesNotExist
from ..utils import auth_wrapper 

@api_view(['POST'])
@authentication_classes([JWTAuthentication])  
@permission_classes([IsAuthenticated])
def add_sms_campaign(request):
    serializer = SmsCampaignSerializer(data=request.data)
    if serializer.is_valid():
        print("validated_data : ", serializer.validated_data)
        try:
            # Check if contact_count is 0
            # if serializer.validated_data.get('contact_count', 0) == 0:
            #     return Response({"detail": "No contacts to add."}, status=status.HTTP_400_BAD_REQUEST)
            template_id = serializer.validated_data.get('template_id')
            # Check if template_id is valid
            if template_id is not None:
                if not SmsTemplate.objects.filter(id=template_id, user=request.user).exists():
                    return Response({"detail": "Invalid template_id."}, status=status.HTTP_400_BAD_REQUEST)
            

            # Save the campaign first to get its ID
            campaign = serializer.save(user=request.user)
            

            return Response({"detail": "Contacts saved successfully"}, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)





@api_view(['POST'])
@authentication_classes([JWTAuthentication])  
@permission_classes([IsAuthenticated])
def edit_sms_campaign(request):
    campaign_id = request.data.get('id')
    if not campaign_id:
        return Response({'message': 'id is required'}, status=status.HTTP_400_BAD_REQUEST)
    
    template_id = request.data.get('template_id')

    if template_id is not None:
        if not SmsTemplate.objects.filter(id=template_id, user=request.user).exists():
            return Response({'message': 'Invalid template_id'}, status=status.HTTP_400_BAD_REQUEST)
    else:
        return Response({'message': 'template_id is required'}, status=status.HTTP_400_BAD_REQUEST)
    
        
    # Get the SmsCampaign object
    campaign = get_object_or_404(SmsCampaign, id=campaign_id)

    # Check if the current user is the owner of the campaign
    if request.user != campaign.user:
        return Response({'message': 'You do not have permission to edit this campaign'}, status=status.HTTP_403_FORBIDDEN)

    try:
        # Update the fields
        for field, value in request.data.items():
            if field in [f.name for f in SmsCampaign._meta.get_fields()] and field != 'status' and field != 'template':
                setattr(campaign, field, value)

        campaign.template = SmsTemplate.objects.get(id=template_id)
        campaign.save()

    except IntegrityError:
        return Response({'message': 'A campaign with this name already exists for this user.'}, status=status.HTTP_400_BAD_REQUEST)

    return Response({'message': 'Campaign updated successfully'}, status=status.HTTP_200_OK)


@api_view(['POST'])
@authentication_classes([JWTAuthentication])  
@permission_classes([IsAuthenticated])
def add_contacts_to_sms_campaign(request):
    campaign_id = request.data.get('campaign_id')
    print("here : ", campaign_id)
    if not campaign_id:
        return Response({'message': 'campaign_id is required'}, status=status.HTTP_400_BAD_REQUEST)

    # Get the SmsCampaign object
    campaign = get_object_or_404(SmsCampaign, id=campaign_id, status__in=[1, 2, 3])

    # Check if the current user is the owner of the campaign
    if request.user != campaign.user:
        return Response({'message': 'You do not have permission to add contacts to this campaign'}, status=status.HTTP_403_FORBIDDEN)

    # get template_id from campaign
    template_id = campaign.template_id
    print("template_id : ", template_id)
    if template_id is None:
        return Response({'message': 'Template not found'}, status=status.HTTP_400_BAD_REQUEST)
    # Extract categories from request data
    categories = {f'category_{i}': request.data.get(f'category_{i}', []) for i in range(1, 6)}

    # Initialize the base query with user_id and contact_status
    base_query = Q(user_id=request.user.id, status=1)

    # Build the category conditions
    for key, values in categories.items():
        if values:
            category_query = Q(**{key: values[0]})
            for val in values[1:]:
                category_query |= Q(**{key: val})
            base_query &= category_query
    
    # Filter Contacts based on base_query
    contacts = Contacts.objects.filter(base_query)

    # Extract phone_number and name
    contact_info = contacts.values('phone_number', 'name')

    # count contacts before adding
    count_before = SmsDialer.objects.filter(sms_campaign=campaign).count()

    
    for contact in contact_info:
        phone_number = contact['phone_number']
        exists = SmsDialer.objects.filter(phone_number=phone_number, sms_campaign=campaign).exists()

        if not exists:
            try:
                sms_message = get_sms_message(request.user.id, template_id, phone_number)
                sms_count = SmsCounter.count(sms_message)["sms_count"]
                SmsDialer.objects.create(
                    phone_number=contact['phone_number'],
                    name=contact['name'],
                    sms_campaign=campaign,
                    user=request.user,
                    sms_sent=sms_message,
                    sms_count=sms_count
                )
                print(f"Contact created: {contact}")
            except Exception as e:
                print(f"Error creating contact: {e}")


    # count contacts after adding
    count_after = SmsDialer.objects.filter(sms_campaign=campaign).count()

    campaign.contact_count = count_after
    if (count_after > count_before) and (campaign.status == 3):
        campaign.status = 1
    campaign.save()
   
    return Response({'message': 'Contacts added successfully'}, status=status.HTTP_200_OK)


@api_view(['GET'])
@authentication_classes([JWTAuthentication])  
@permission_classes([IsAuthenticated])
def get_sms_campaigns(request):
    search_query = request.GET.get('search', '')
    order = request.GET.get('order', 'id desc')
    page_number = request.GET.get('page', 1)
    page_size = request.GET.get('page_size', 25)

    if search_query:
        campaigns = SmsCampaign.objects.filter(
            Q(name__icontains=search_query) | 
            Q(description__icontains=search_query) |
            Q(priority__icontains=search_query),
            user=request.user
        )
    else:
        print("request.user : ", request.user)
        campaigns = SmsCampaign.objects.filter(user=request.user)
    print("campaigns : ", campaigns)
    # Split the order parameter into field and direction
    field, direction = order.split()

    # If direction is 'desc', prepend the field name with '-'
    if direction.lower() == 'desc':
        field = '-' + field

    campaigns = campaigns.order_by(field)

    paginator = Paginator(campaigns, page_size)


    try:
        page = paginator.page(page_number)
    except EmptyPage:
        # If the page is out of range, return an empty list
        campaigns_list = []
    else:
        serializer = SmsCampaignSerializer(page.object_list, many=True)
        campaigns_list = serializer.data
    
   

    return Response({
        'current_page': page.number if campaigns_list else None,
        'total_pages': paginator.num_pages,
        'data': campaigns_list,
        'message': "Campaigns Retrieved Successfully" if campaigns_list else "Data not found",
        
    }, status=status.HTTP_200_OK)





@api_view(['POST'])
@authentication_classes([JWTAuthentication])  
@permission_classes([IsAuthenticated])
def update_sms_campaign_status(request):
    # Get the user from the bearer token
    user = request.user

    # Get the campaign_id and new_status from the JSON body
    data = request.data
    campaign_id = data.get('id')
    new_status = data.get('status')

    # Ensure both campaign_id and new_status are provided
    if not campaign_id or not new_status:
        return JsonResponse({"message": 'id and status are required in the JSON body.'}, status=400)

    # Retrieve the campaign object
    try:
        campaign = SmsCampaign.objects.get(id=campaign_id)
    except SmsCampaign.DoesNotExist:
        raise Http404("No SmsCampaign matches the given query.")

    # Check if the campaign belongs to the user
    if campaign.user != user:
        raise PermissionDenied("You do not have permission to change this campaign's status.")

    print(" campaign.status : ", campaign.status)
    print(" new_status : ", new_status)
    # Check if the new status is valid based on the current status
    # If campaign.status = 3, then return an error message
    if int(campaign.status) == 3:
        return JsonResponse({"message": 'Campaign is already completed.'}, status=400)
    # If campaign.status = 1, then new_status can be 2 or campaign.status = 2 and new_status =1, then update
    if (int(campaign.status) == 1 and int(new_status) == 2) or (int(campaign.status) == 2 and int(new_status) == 1):
        campaign.status = new_status
        campaign.save()
        return JsonResponse({'message': 'Campaign status changed successfully.'})
    # if new campaign status = 4, then update
    if int(new_status) == 4:
        campaign.status = new_status
        campaign.save()
        # Update in the SmsDialer table
        SmsDialer.objects.filter(sms_campaign=campaign, sent_status=0).update(sent_status=4)
        return JsonResponse({'message': 'Campaign status changed successfully.'})

    # If the campaign.status is 4 and new_status is 1 or 2, then update the campaign status
    if int(campaign.status) == 4 and int(new_status) in [1, 2]:
        campaign.status = new_status
        campaign.save()
        # Update in sms_dialer table
        SmsDialer.objects.filter(sms_campaign=campaign, sent_status=4).update(sent_status=0)
        return JsonResponse({'message': 'Campaign status changed successfully.'})

    # If the new status is not valid for the current status, return an error message
    return JsonResponse({"message": 'Invalid status transition.'}, status=400)

@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def sms_campaign_report(request):
    user = request.user
    # Get sms_campaign_id from request data
    sms_campaign_id = request.data.get('sms_campaign_id')
    if not sms_campaign_id:
        sms_dialers = SmsDialer.objects.filter(user_id=user.id).order_by('-id')
    
    # Get All contacts of PhoneDialer for the given campaign_id and user_id in ascending order of id
    sms_dialers = SmsDialer.objects.filter(sms_campaign_id=sms_campaign_id, user_id=user.id).order_by('-id')
    print("sms_dialers : ", sms_dialers)
    serializer = SmsDialerSerializer(sms_dialers, many=True)
    # Fetch the data from the SmsDialer model
    sms_dialers = SmsDialer.objects.all()

    # Calculate the unique_sms_sent, total_sms_sent, and to_be_sent
    unique_sms_sent = sms_dialers.filter(sent_status=5, sms_campaign_id=sms_campaign_id).values('phone_number').distinct().count()
    total_sms_sent = sms_dialers.filter(sent_status=5, sms_campaign_id=sms_campaign_id).count()
    to_be_sent = sms_dialers.filter(sent_status=0, sms_campaign_id=sms_campaign_id).count()

    # Update the summary_report dictionary
    summary_report = {
        "unique_sms_sent": unique_sms_sent,
        "total_sms_sent": total_sms_sent,
        "to_be_sent": to_be_sent,
    }

    data = {
        "summary_report": summary_report,
        "data": serializer.data
    }

    # return the data
    return Response(data, status=status.HTTP_200_OK)


@api_view(['DELETE'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def delete_sms_campaign_contact(request):
    # Get the user_id from the request
    user_id = auth_wrapper(request)
    if not user_id:
        return Response({"message": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)
    
    # Find id from the request data
    id = request.data.get('id')
    if not id:
        return Response({"message": "ID not found"}, status=status.HTTP_400_BAD_REQUEST)
    
    # Get the campaign_id from the request data
    sms_campaign_id = request.data.get('sms_campaign_id')

    # Get the delete_all flag from the request data
    delete_all = request.data.get('delete_all', 0)

    if delete_all == 1:
        # Delete all PhoneDialer instances with sent_status=0
        SmsDialer.objects.filter(sms_campaign_id=sms_campaign_id, user_id=user_id, sent_status=0).delete()
        # update campaign_status to 3
        SmsCampaign.objects.filter(id=sms_campaign_id, user_id=user_id).update(status=3)
    else:
        # Now, filter for the PhoneDialer with the given id and user_id and sent_status=0
        try:
            sms_dialer = SmsDialer.objects.get(id=id, sms_campaign_id=sms_campaign_id, user_id=user_id, sent_status=0)
        except SmsDialer.DoesNotExist:
            return Response({"message": "Unable to delete"}, status=status.HTTP_400_BAD_REQUEST)
        
        # Delete the PhoneDialer
        sms_dialer.delete()


    try:
        print("sms_campaign_id : ", sms_campaign_id)
        sms_campaign = SmsCampaign.objects.get(id=sms_campaign_id, user_id=user_id)
    except SmsCampaign.DoesNotExist:
        return JsonResponse({'status': "message", 'message': 'SmsCampaign does not exist'}, status=400)

    # Count the number of PhoneDialer entries with the same campaign_id
    contacts_count = SmsDialer.objects.filter(sms_campaign_id=sms_campaign_id).count()

    # Update contacts_count in the Campaign table
    sms_campaign.contacts_count = contacts_count 
    sms_campaign.save()
    return Response({"message": "Data deleted successfully"}, status=status.HTTP_200_OK)