from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import IsAuthenticated
from django.http import JsonResponse
from ..models import Campaign, UserHosts, ActiveCampaignHosts, Users
from src.phone_dialer import get_machine_status, process_response, update_sim_information
from api.views.machine_status import merge_sim_information 
import requests

@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def check_sample_call(request):
    # Get user_id from token
    user_id = request.user.id

    # Get data from request
    data = request.data
    campaign_id = data.get('campaign_id')
    host_id = data.get('host_id')
    phone_number = data.get('phone_number')
    name = data.get('name')


    # Check if campaign_id is associated with user_id
    try:
        campaign = Campaign.objects.get(id=campaign_id, user_id=user_id)
    except Campaign.DoesNotExist:
        return JsonResponse({'message': 'Campaign not found or not associated with this user'}, status=404)

    #find name from users object
    if not name:
        user = Users.objects.get(id=user_id)
        name = user.name
        if not name:
            name = "test name"

    # Check if host_id is associated with user_id
    try:
        user_host = UserHosts.objects.get(id=host_id, user_id=user_id, status=1)
    except UserHosts.DoesNotExist:
        return JsonResponse({'message': 'Host not found or not associated with this user'}, status=404)

    # Check if campaign_id and host_id are in active campaign host with status 1
    try:
        active_campaign_host = ActiveCampaignHosts.objects.get(campaign_id=campaign_id, host_id=host_id, status=1)
    except ActiveCampaignHosts.DoesNotExist:
        return JsonResponse({'message': 'Campaign and Host not found or not associated with this user'}, status=404)
    
    # Check if phone_number is provided
    if phone_number is None:
        return JsonResponse({'message': 'Phone number is required'}, status=400)
    

    response = get_machine_status(user_host)
    if response:
        #print("Step 5, merge_sim_information ", user_host.host)
        response = merge_sim_information([response])
        #print("Response : ", response)
        number_of_sims_ready, ready_sims = process_response(response)
        sim_with_lowest_call_time_today = ready_sims[0] if ready_sims else None
        if sim_with_lowest_call_time_today:
            #print("Step 6, update_sim_information ", user_host.host)
            update_sim_information(user_host.host, sim_with_lowest_call_time_today["sim_imsi"])

            port = sim_with_lowest_call_time_today["port"]
            url = f"https://{user_host.host}.sabkiapp.com/make_call"
            headers = {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer {{bearerToken}}'  # replace {{bearerToken}} with your actual token
            }
            data = {
            "host": user_host.host,
            "system_password": user_host.system_password,
            "phone_number": phone_number,
            "port": port,
            "user_id": user_id,
            "campaign_id": campaign_id,
            "name": name,
            "name_spell": campaign.name_spell
            }
            # Make the API call
            response = requests.post(url, headers=headers, json=data)

            # Check the response
            if response.status_code == 200:
                print("API call successful")
                return JsonResponse({'message': 'Called successfully'}, status=200)
            else:
                print(f"API call failed with status code {response.status_code}")
                return JsonResponse({'message': f"Call failed with status code {response.status_code}"}, status=400)
        else:
            return JsonResponse({'message': 'No ready sim found to make call, please try again later'}, status=400)
        
    else:
        return JsonResponse({'message': 'Machine is not online'}, status=400)