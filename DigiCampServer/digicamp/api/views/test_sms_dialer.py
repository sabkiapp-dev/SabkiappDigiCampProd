import os
import django
from django.db.models import Q, F
from datetime import timedelta
import requests

from api.models import PhoneDialer, Campaign
import concurrent.futures
from api.views.gateway_status import fetch_gateway_status
from api.models import ActiveCampaignHosts
from api.models import UserHosts
from api.models import SimInformation
from src.mytime import get_mytime
from api.views.gateway_status import merge_sim_information
import json
import threading
from django.conf import settings
from src.phone_encrypter import encrypt_phone
from api.models import SmsCampaign
from api.models import SmsDialer  # Import the SmsDialer class
import time
from src.sms_sender import SmsSender


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'digicamp_server.settings')
django.setup()

def start_sending_sms_dialer():
    my_time = get_mytime()
    sms_dialers = SmsDialer.objects.filter(
        Q(sent_status=0) &
        (
            Q(sms_campaign_id=None) |
            (
                Q(sms_campaign_id__isnull=False) &
                Q(sms_campaign__campaign_status=1) &
                Q(sms_campaign__start_time__lte=my_time, sms_campaign__end_time__gte=my_time) &
                Q(sms_campaign__start_date__lte=my_time.date(), sms_campaign__end_date__gte=my_time.date())
            )
        )
    )
    sms_dialer_user_ids = sms_dialers.values_list('user_id', flat=True).distinct()

    active_hosts = UserHosts.objects.filter(
        Q(status=1) &
        Q(allow_sms=1) &
        Q(user_id__in=sms_dialer_user_ids)
    ).distinct()


    with concurrent.futures.ThreadPoolExecutor() as executor:
        for user_host in active_hosts:
            my_time = get_mytime()
            sms_dialers = SmsDialer.objects.filter(
                Q(user_id__in=UserHosts.objects.filter(
                    Q(status=1) &
                    Q(allow_sms=1) &
                    Q(host=user_host.host)
                ).values_list('user_id', flat=True)) &
                Q(sent_status=0) &
                (
                    Q(sms_campaign_id=None) |
                    (
                        Q(sms_campaign_id__isnull=False) &
                        Q(sms_campaign__campaign_status=1) &
                        Q(sms_campaign__start_time__lte=my_time, sms_campaign__end_time__gte=my_time) &
                        Q(sms_campaign__start_date__lte=my_time.date(), sms_campaign__end_date__gte=my_time.date())
                    )
                )
            ).annotate(priority=F('user_id__priority')).order_by('-priority')
        
            # Change status of the sms_dialer to 1
            sms_dialers.update(sent_status=1, sent_datetime=my_time)

 
            # Create a new instance of SmsSender for each instance
            sms_sender = SmsSender()

            if sms_dialers:
                sms_sender.send_sms(sms_dialers[0])

            for sms_dialer in sms_dialers[1:]:
                if sms_sender.shared_state['stop_thread']:
                    sms_dialer.sent_status = 0
                    sms_dialer.save()
                else:
                    threading.Thread(target=sms_sender.send_sms, args=(sms_dialer,)).start()
                    time.sleep(1)
            
                


start_sending_sms_dialer()