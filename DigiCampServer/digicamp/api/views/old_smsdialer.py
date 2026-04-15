import os
import django
from django.db.models import Q, F
from datetime import timedelta
from src.mytime import get_mytime
import requests
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'digicamp_server.settings')
django.setup()
from api.models import PhoneDialer, Campaign
import concurrent.futures
from api.views.gateway_status import fetch_gateway_status
from api.models import ActiveCampaignHosts
from api.models import UserHosts
from api.models import SimInformation
from api.views.gateway_status import merge_sim_information
from django.db.models import Max
import threading
from django.conf import settings
from src.phone_encrypter import encrypt_phone
from api.models import SmsCampaign
from api.models import SmsDialer  # Import the SmsDialer class
import time
from src.sms_sender import SmsSender



def start_sending_sms_dialer():
    my_time = get_mytime()
        
    try:
        sms_dialers = SmsDialer.objects.filter(
            Q(sent_status=0),
            (
                Q(sms_campaign_id=None) 
                | 
                (
                    Q(sms_campaign_id__isnull=False) 
                    & Q(sms_campaign__status__exact=1)  # Replace 'status' with the correct field name
                    & Q(sms_campaign__start_time__lte=my_time, sms_campaign__end_time__gte=my_time) 
                    & Q(sms_campaign__start_date__lte=my_time.date(), sms_campaign__end_date__gte=my_time.date())
                )
            )
        )
        print("sms_dialers : ", sms_dialers)
    except Exception as e:
        print("An error occurred during filter: ", e)

    try:
        sms_dialer_user_ids = sms_dialers.values_list('user_id', flat=True).distinct()
        print("sms_dialer_user_ids : ", sms_dialer_user_ids)
    except Exception as e:
        print("An error occurred during values_list: ", e)

    active_hosts = UserHosts.objects.filter(
        Q(status=1) &
        Q(allow_sms=1) &
        Q(user_id__in=sms_dialer_user_ids)
    ).distinct()
    print("active_hosts : ", active_hosts)

    with concurrent.futures.ThreadPoolExecutor() as executor:
        for user_host in active_hosts:
            sms_dialers = None
            try:
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
                            Q(sms_campaign__status__exact=1) &
                            Q(sms_campaign__start_time__lte=my_time, sms_campaign__end_time__gte=my_time) &
                            Q(sms_campaign__start_date__lte=my_time.date(), sms_campaign__end_date__gte=my_time.date())
                        )
                    )
                ).annotate(priority=Max('user_id__userhosts__priority')).order_by('-priority')  # Adjusted here
            except Exception as e:
                print("An error occurred during filter: ", e)
            finally:
                print("sms_dialers new : ", sms_dialers)
            try:
                # Change status of the sms_dialer to 1
                sms_dialers.update(sent_status=1, sent_datetime=my_time)
            except Exception as e:
                print("An error occurred during update: ", e)

            # Create a new instance of SmsSender for each instance
            sms_sender = SmsSender()

            if sms_dialers:
                try:
                    sms_sender.send_sms(sms_dialers[0])
                    print("sms_dialers[0] : ", sms_dialers[0])
                except Exception as e:
                    print("An error occurred during send_sms: ", e)

            for sms_dialer in sms_dialers[1:]:
                print("sms_dialer : ", sms_dialer)
                if sms_sender.shared_state['stop_thread']:
                    print("Thread stopped")
                    sms_dialer.sent_status = 0
                    sms_dialer.save()
                else:
                    try:
                        threading.Thread(target=sms_sender.send_sms, args=(sms_dialer,)).start()
                        time.sleep(1)
                    except Exception as e:
                        print("An error occurred during threading: ", e)