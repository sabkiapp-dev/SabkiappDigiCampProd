
from django.urls import path
from .views.authentication import signup, signin, reset_password, change_password, generate_api_key, get_api_key
from .views.hello import hello_world
from .views.campaign import campaign_detail, add_campaign, campaigns, update_campaign, update_campaign_audio, update_campaign_status, add_contacts_to_campaign, add_to_phone_dialer, update_active_campaign_host
from .views.campaign import (
    campaign_summary_report,
    campaign_detail_report,
    delete_campaign_contact,
    download_campaign_report,
    verify_add_to_phone_dialer,
)
from .views.sms import send_sms
from .views.audios import add_audio, voices, update_voice, update_audio_status
from .views.dial_plan import add_dial_plan, update_dial_plan, dial_plan
from .views.contacts import add_contacts, get_contacts, get_unique_categories, delete_contacts, category_contacts_delete, count_category_contacts, upload_contacts
from .views.users import get_referred_users, change_user_status, change_host, get_user_token
from .views.voice import get_pronunciation
from .views.user_hosts import user_host, get_hosts_by_user, change_host_status, edit_host, get_host_password, active_hosts_status
from .views.machine_status import get_all_machine_status
from .views.sms_template import add_sms_template, get_sms_template, update_sms_template_status, update_sms_template_name
from .views.sim_information import SimInformationView               
from django.conf import settings
from django.conf.urls.static import static
from .views.call_status import send_call_status, trigger_dialer
from .views.sms_campaign import add_sms_campaign, get_sms_campaigns, update_sms_campaign_status, edit_sms_campaign, add_contacts_to_sms_campaign, sms_campaign_report, delete_sms_campaign_contact
from .views.api_docs import get_api_docs
from .views.misscall_management import add_misscall_operator, update_misscall_operator_status, get_misscall_operators, edit_misscall_operator
from .views.misscall_management import view_misscalls, download_misscalls_report, update_past_misscalls
from .views.check_sample_call import check_sample_call
from .views.test_blocked_sim import test_blocked_sim
from .views.sync_code import sync_code
from .views.general import homepage
from .views.debug_push_status import test_push_call_status
from .views.voice_tts import generate_verification_clip
from .views.campaign import cancel_ref_no
from .views.contact_registration import add_contact, create_api_key, list_api_keys, delete_api_key

urlpatterns = [
    path('', homepage, name='homepage'),
    path('register', signup, name='signup'),
    path('sign_in', signin, name='signin'),
    path('reset_password', reset_password, name='reset_password'),
    path('change_password', change_password, name='change_password'),
    path('campaign_detail/<int:campaign_id>', campaign_detail, name='campaign_detail'),
    path('add_campaign', add_campaign, name='add_campaign'),
    path('campaigns', campaigns, name='campaigns'),
    path('update_campaign', update_campaign, name='update_campaign'),
    path('add_audio', add_audio, name='add_audio'),
    path('voices', voices, name='voices'),
    path('update_voice', update_voice, name='update_voice'),
    path('add_dial_plan', add_dial_plan, name='add_dial_plan'),
    path('dial_plan/<int:campaign_id>', dial_plan, name='dial_plan'),
    path('update_dial_plan', update_dial_plan, name='update_dial_plan'),
    path('contacts', get_contacts, name='get_contacts'),
    path('add_contacts', add_contacts, name='add_contacts'),
    path('delete_contacts', delete_contacts, name='delete_contacts'),
    path('get_unique_categories', get_unique_categories, name='get_unique_categories'),
    path('get_referred_users', get_referred_users, name ='get_referred_users'),
    path('change_user_status', change_user_status, name = 'change_user_status'),
    path('get_pronunciation', get_pronunciation, name='get_pronunciation'),
    path('change_host', change_host, name='change_host'),
    path('category_contacts_delete', category_contacts_delete, name='category_contacts_delete'),
    path('count_category_contacts', count_category_contacts, name='count_category_contacts'),
    path('sim_information', SimInformationView.as_view(), name='sim_information'),
    path('user_host', user_host, name='user_host'),
    path('get_hosts/<int:user_id>', get_hosts_by_user, name='get_hosts_by_user'),
    path('change_host_status', change_host_status, name='change_host_status'),
    path('edit_host/<int:host_id>', edit_host, name='edit_host'),
    path('get_all_machine_status', get_all_machine_status, name='get_all_machine_status'),
    path('get_user_token/<int:user_id>', get_user_token, name='get_user_token'),
    path('send_sms', send_sms, name='send_sms'),
    path('add_sms_template', add_sms_template, name='add_sms_template'),
    path('get_sms_template', get_sms_template, name='get_sms_template'),
    path('update_audio_status', update_audio_status, name='update_audio_status'),
    path('update_sms_template_status', update_sms_template_status, name='update_sms_template_status'),
    path('update_campaign_audio', update_campaign_audio, name='update_campaign_audio'),
    path('send_call_status', send_call_status, name='send_call_status'),
    path('update_campaign_status', update_campaign_status, name='update_campaign_status'),
    path('add_sms_campaign', add_sms_campaign, name='add_sms_campaign'),
    path('edit_sms_campaign', edit_sms_campaign, name='edit_sms_campaign'),
    path('get_sms_campaigns', get_sms_campaigns, name='get_sms_campaigns'),
    path('add_contacts_to_campaign', add_contacts_to_campaign, name='add_contacts_to_campaign'),
    path('update_sms_campaign_status', update_sms_campaign_status, name='update_sms_campaign_status'),
    path('generate_api_key', generate_api_key, name='generate_api_key'),
    path('get_api_key', get_api_key, name='get_api_key'),
    path('update_sms_template_name', update_sms_template_name, name='update_sms_template_name'),
    path('add_to_phone_dialer', add_to_phone_dialer, name='add_to_phone_dialer'),
    path('get_api_docs', get_api_docs, name='get_api_docs'),
    path('update_active_campaign_host', update_active_campaign_host, name='update_active_campaign_host'),
    path('campaign_summary_report', campaign_summary_report, name='campaign_summary_report'),
    path('campaign_detail_report', campaign_detail_report, name='campaign_detail_report'),
    path('download_campaign_report', download_campaign_report, name='download_campaign_report'),
    path('verify_add_to_phone_dialer', verify_add_to_phone_dialer, name='verify_add_to_phone_dialer'),
    path('delete_campaign_contact', delete_campaign_contact, name='delete_campaign_contact'),
    path('trigger_dialer', trigger_dialer, name='trigger_dialer'),
    path('add_misscall_operator', add_misscall_operator, name='add_misscall_operator'),
    path('update_misscall_operator_status', update_misscall_operator_status, name='update_misscall_operator_status'),
    path('get_misscall_operators', get_misscall_operators, name='get_misscall_operators'),
    path('edit_misscall_operator', edit_misscall_operator, name='edit_misscall_operator'),
    path('add_contacts_to_sms_campaign', add_contacts_to_sms_campaign, name='add_contacts_to_sms_campaign'),
    path('sms_campaign_report', sms_campaign_report, name='sms_campaign_report'),
    path('delete_sms_campaign_contact', delete_sms_campaign_contact, name='delete_sms_campaign_contact'),
    path('view_misscalls', view_misscalls, name='view_misscalls'),
    path('check_sample_call', check_sample_call, name='check_sample_call'),
    path('get_host_password', get_host_password, name='get_host_password'),
    path('download_misscalls_report', download_misscalls_report, name='download_misscalls_report'),
    path('active_hosts_status', active_hosts_status, name='active_hosts_status'),
    path('upload_contacts', upload_contacts, name='upload_contacts'),
    path('test_blocked_sim', test_blocked_sim, name='test_blocked_sim'),
    path('sync_code', sync_code, name='sync_code'),
    path('update_past_misscalls', update_past_misscalls, name='update_past_misscalls'),
    

    path("cancel_ref_no", cancel_ref_no, name="cancel_ref_no"),

    # Debug endpoint for testing call status pushes
    path('debug/push_call_status', test_push_call_status, name='debug_push_call_status'),

    path('generate_verification_clip', generate_verification_clip, name='generate_verification_clip'),

    # External Contact Add API
    path('add_contact', add_contact, name='add_contact'),

    # API Key Management (JWT Auth required)
    path('api_key/create', create_api_key, name='create_api_key'),
    path('api_key/list', list_api_keys, name='list_api_keys'),
    path('api_key/delete', delete_api_key, name='delete_api_key'),

]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)