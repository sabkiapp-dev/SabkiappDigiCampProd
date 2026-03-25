from django.urls import path
from .views import (
    machine_status, receive_sms, send_sms, sms_response,
    start_ssh_tunnel, start_eroll_tunnels, get_disk_space_info_view,
    upload_audio, get_tunnel_status, make_call, change_host_password,
    save_dial_plan, reboot, update_code, zip_entire_code, download_zip,
    gsm_info_view,
)

urlpatterns = [
    path('machine_status', machine_status, name='machine_status'),
    path('receive_sms', receive_sms, name='receive_sms'),
    path('send_sms', send_sms, name="send_sms"),
    path('sms_response', sms_response, name="sms_response"),
    path('start_ssh_tunnel', start_ssh_tunnel, name='start_ssh_tunnel'),
    path('start_eroll_tunnels', start_eroll_tunnels, name='start_eroll_tunnels'),
    path('disk_space', get_disk_space_info_view, name='get_disk_space_info_view'),
    path('upload_audio', upload_audio, name= 'upload_audio'),
    path('tunnel_status', get_tunnel_status, name='get_tunnel_status'),
    path('make_call', make_call, name='make_call'),
    path('change_host_password', change_host_password, name='change_host_password'),
    path('save_dial_plan', save_dial_plan, name='save_dial_plan'),
    path('reboot', reboot, name='reboot'),
    path('update_code', update_code, name='update_code'),
    path('zip_entire_code', zip_entire_code, name='zip_entire_code'),
    path('Documents/MachineStatus.zip', download_zip, name='download_zip'),
    path('gsm-info', gsm_info_view, name='gsm_info'),
]
