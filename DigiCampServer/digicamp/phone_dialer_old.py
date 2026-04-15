import os
import django
from django.db.models import Q

from datetime import timedelta
from digicamp_server.mytime import get_mytime


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'digicamp_server.settings')
django.setup()

from api.models import PhoneDialer, Campaign
from django.db.models import F

from api.views.gateway_status import fetch_gateway_status
from api.models import ActiveCampaignHosts
from api.models import UserHosts

# Get all PhoneDialer objects where sent_status equals 0
one_hour_ago = get_mytime() - timedelta(hours=1)

my_time = get_mytime()
print("My Time : ", my_time)


def hello():
    print("Hello")


def process_user(user_id):
    phone_dialers = PhoneDialer.objects.filter(
        Q(sent_status=0) & 
        (Q(sent_datetime=None) | Q(sent_datetime__lt=one_hour_ago)) & 
        Q(campaign__allow_repeat__gte=F('trials')) &
        Q(user_id=user_id) & 
        Q(campaign__status=1) &
        Q(campaign__start_time__lte=my_time, campaign__end_time__gte=my_time) &
        Q(campaign__start_date__lte=my_time.date(), campaign__end_date__gte=my_time.date())   
    )
    phone_dialer = phone_dialers.order_by('-campaign__campaign_priority', 'id').first()
    if phone_dialer:
        print(f"PhoneDialer : {phone_dialer.id}, Phone Number : {phone_dialer.phone_number}, User ID : {phone_dialer.user_id}, Campaign ID : {phone_dialer.campaign_id}, Priority : {phone_dialer.campaign.campaign_priority}")
    
        hosts = fetch_gateway_status(phone_dialer.user_id, None, None, None)

        # Filter the hosts to only include those that are active in the ActiveCampaignHosts table
        active_hosts = []
        for host in hosts:
            user_host = UserHosts.objects.get(host=host['host'])
            if ActiveCampaignHosts.objects.filter(host=user_host, status=1).exists():
                active_hosts.append({
                    'id': user_host.id,
                    'host': host['host'],
                    'number_of_sims_ready': host['number_of_sims_ready'],
                    'port_data': host['port_data']
                })

        total_ready_sims = sum(host['number_of_sims_ready'] for host in active_hosts)

        for host in active_hosts:
            print("Host : ", host['host'])
            ready_ports = [port for port in host['port_data'] if port['final_status'] == 'Ready']
            if ready_ports:
                port_with_lowest_call_time_today = min(ready_ports, key=lambda port: port['call_time_today'])
                print("Port with lowest call_time_today: ", port_with_lowest_call_time_today)
                
                
        print("Total Ready SIMs: ", total_ready_sims)
        print("Phone Number : ", phone_dialer.phone_number)
        phone_number = phone_dialer.phone_number
        hello(phone_number)
        if total_ready_sims > 1:
            process_user(user_id)
    else:
        print("No phone dialer found")


user_ids = Campaign.objects.filter(
    Q(status=1) &
    Q(start_time__lte=my_time, end_time__gte=my_time) &
    Q(start_date__lte=my_time.date(), end_date__gte=my_time.date())
).values_list('user_id', flat=True).distinct()

for user_id in user_ids:
    process_user(user_id)