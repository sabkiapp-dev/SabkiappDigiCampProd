from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response
from rest_framework import status
from ..models.dial_plan import DialPlan
from ..models.campaign import Campaign
from ..serializers import DialPlanSerializer, DialPlanUpdateSerializer, VoicesSerializer
from ..utils import auth_wrapper
from django.shortcuts import get_object_or_404
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import IsAuthenticated
import logging
from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError
from ..models.sms_template import SmsTemplate
@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def add_dial_plan(request):
    user = auth_wrapper(request)
    if not user:
        return Response({"message": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)
    campaign_id = request.query_params.get('campaign_id')
    # Validate if the campaign_id belongs to the user
    try:
        campaign = Campaign.objects.get(id=campaign_id, user=user)
        
    except ObjectDoesNotExist:
        return Response({"message": "The specified campaign does not belong to the user"}, status=status.HTTP_400_BAD_REQUEST)

    # If status of campaign is not 0, then return error "Dialpan Freezed"
    if campaign.status != 0:
        return Response({"message": "Dial Plan is freezed"}, status=status.HTTP_400_BAD_REQUEST)
    
    # Make extesnsion_id auto-increment based on campaign_id by checking highest extension_id for the campaign
    try:
        extension_id = DialPlan.objects.filter(campaign=campaign).latest('extension_id').extension_id + 1
    except ObjectDoesNotExist:
        extension_id = 1
        


    # Create a new DialPlan object
    dial_plan = DialPlan(campaign=campaign, extension_id=extension_id)
    dial_plan.save()

    # Serialize the DialPlan object
    serializer = DialPlanSerializer(dial_plan)

    return Response(serializer.data, status=status.HTTP_201_CREATED)
    

# @api_view(['GET'])
# @authentication_classes([JWTAuthentication])
# @permission_classes([IsAuthenticated])
# def dial_plan(request, campaign_id):
#     user = auth_wrapper(request)
#     if not user:
#         return Response({"message": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)

#     dial_plans = DialPlan.objects.filter(campaign__id=campaign_id, campaign__user=user)
#     serializer = DialPlanSerializer(dial_plans, many=True)
    
#     # Get no_key_voice and wrong_key_voice from Campaign table for the user and campaign_id
#     campaign = Campaign.objects.get(id=campaign_id, user=user)
#     no_key_voice = campaign.no_key_voice
#     wrong_key_voice = campaign.wrong_key_voice
#     # get the objects serializer of no_key_voice and wrong_key_voice
#     no_key_voice = VoicesSerializer(no_key_voice).data if no_key_voice else None
#     wrong_key_voice = VoicesSerializer(wrong_key_voice).data if wrong_key_voice else None
#     response_message = {
#         "message": "Dial Plan Retrieved Successfully",
#         "campaign": campaign_id,
#         "no_key_voice":no_key_voice,
#         "wrong_key_voice":wrong_key_voice,
#         "data": serializer.data,
#         }

#     return Response(response_message , status=status.HTTP_200_OK)

from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.db.models import Prefetch

@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def dial_plan(request, campaign_id):
    user = auth_wrapper(request)
    if not user:
        return Response({"message": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)

    # Fetch campaign scoped to the user, or 404 (not 500)
    campaign = get_object_or_404(Campaign, id=campaign_id, user=user)

    # If you expect zero dial plans sometimes, still return 200 with an empty list
    dial_plans = DialPlan.objects.filter(campaign_id=campaign.id, campaign__user=user)
    serializer = DialPlanSerializer(dial_plans, many=True)

    # Safely serialize optional voices
    no_key_voice = VoicesSerializer(campaign.no_key_voice).data if campaign.no_key_voice else None
    wrong_key_voice = VoicesSerializer(campaign.wrong_key_voice).data if campaign.wrong_key_voice else None

    response_message = {
        "message": "Dial Plan Retrieved Successfully",
        "campaign": campaign.id,
        "no_key_voice": no_key_voice,
        "wrong_key_voice": wrong_key_voice,
        "data": serializer.data,
    }
    return Response(response_message, status=status.HTTP_200_OK)


@api_view(['PATCH'])
@authentication_classes([JWTAuthentication])  
@permission_classes([IsAuthenticated])
def update_dial_plan(request):
    logger = logging.getLogger(__name__)
    logger.info(f'Incoming request data: {request.data}')

    user = auth_wrapper(request)
    if not user:
        return Response({"message": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)
    
    # Extract the dial_plan_id from the request data and extension_id
    dial_plan_id = request.data.get('id')
    extension_id = request.data.get('extension_id')
    template_id = request.data.get('template_id')
    continue_to = request.data.get('continue_to')
    
    print("User ID: ", user)
    print("Template ID: ", template_id)
    # check if template_id belongs to same user from SmsTemplate table

    if template_id:
        
        try:
            template = SmsTemplate.objects.get(id=template_id, user=user)
        except ObjectDoesNotExist:
            return Response({"message": "The specified template does not belong to the user"}, status=status.HTTP_400_BAD_REQUEST)
    
    # update the dial_plan on the basis of dial_plan_id, extension_id and user_id
    try:
        dial_plan = DialPlan.objects.get(id=dial_plan_id, campaign__user=user, extension_id=extension_id, campaign__id=request.data.get('campaign_id'))
    except ObjectDoesNotExist:
        return Response({"message": "Dial Plan not found"}, status=status.HTTP_404_NOT_FOUND) 

    
    # create a for each loop for dtmf 0 to 9 and theck the given dtmf's campaign_id and print
    for i in range(10):
        dtmf = f'dtmf_{i}'
        if dtmf in request.data:
            if request.data.get(dtmf) != None and request.data.get(dtmf) != 0:
                try:
                    DialPlan.objects.get(id=request.data.get(dtmf),campaign__id=request.data.get('campaign_id'))
                except ObjectDoesNotExist:
                    return Response({"message": f"{dtmf} does not belongs to given campaign id {request.data.get('campaign_id')}"}, status=status.HTTP_404_NOT_FOUND)
    
    # Check if the continue_to is present in the dial_plan
    if continue_to:
        try:
            DialPlan.objects.get(id=continue_to,campaign__id=request.data.get('campaign_id'))
        except ObjectDoesNotExist:
            return Response({"message": f"continue_to does not belongs to given campaign id {request.data.get('campaign_id')}"}, status=status.HTTP_404_NOT_FOUND)
    # If status of campaign is not 0, then return error "Dialpan Freezed"
    # Find the campaign status for the dial_plan
    campaign = Campaign.objects.get(id=request.data.get('campaign_id'))
    if campaign.status != 0:
        return Response({"message": "Dial Plan is freezed"}, status=status.HTTP_400_BAD_REQUEST)
    serializer = DialPlanSerializer(dial_plan, data=request.data, partial=True)
   
    if serializer.is_valid():
        try:
            serializer.save()
            return Response({"message": "Dial Plan updated successfully"}, status=status.HTTP_200_OK)
        except ValidationError as e:
            return Response({"message": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    else:
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)



   
