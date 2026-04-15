from datetime import datetime
from rest_framework import serializers
from .models.campaign import Campaign
from .models.voices import Voices
from .models.dial_plan import DialPlan
from .models.contacts import Contacts
from .models.sim_information import SimInformation
from .models.users import Users
from .models.phone_dialer import PhoneDialer
from .models.sms_dialer import SmsDialer
from .models.call_dtmf_status import CallDtmfStatus
from .models.error_verify_phone_dialer import ErrorVerifyPhoneDialer
from .models.sms_campaign import SmsCampaign
from .models import PhoneDialer, SmsDialer
from .models import CallDtmfStatus
from .models import Misscalls
import imageio_ffmpeg as ffmpeg
from pydub import AudioSegment
import tempfile
import os
from src.voice_uploader import upload_file
from django.core.exceptions import ObjectDoesNotExist
import shutil
import sys
from .models.user_hosts import UserHosts
from .models.sms_template import SmsTemplate
from .models.call_status       import CallStatus
# # grab the ffmpeg executable that imageio-ffmpeg downloaded
ffmpeg_path = ffmpeg.get_ffmpeg_exe()
# tell pydub to use it for both conversion and probing
AudioSegment.converter = ffmpeg_path
AudioSegment.ffprobe   = ffmpeg_path


class CampaignStatusSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    status = serializers.IntegerField()







class VoicesSerializer(serializers.ModelSerializer):
    file = serializers.FileField(write_only=True)
    voice_name = serializers.CharField()
    voice_desc = serializers.CharField(required=False, allow_blank=True)


    class Meta:
        model = Voices
        fields = ['id', 'user', 'voice_name', 'voice_desc', 'file', 'path', 'modified_at', 'created_at']
        extra_kwargs = {
            'modified_at': {'read_only': True},
            'created_at': {'read_only': True},
            'path': {'read_only': True},
        }
    def validate_voice_name(self, value):
        if len(value) > 255:
            raise serializers.ValidationError("Name greater than 255 characters limit")
        return value

    

    def create(self, validated_data):
        # Handle file upload
        file_obj = validated_data.pop('file')
        user = validated_data.get('user')
        print("here 1")
        # Create the Voices object without the file path
        voice = Voices.objects.create(**validated_data)

        try:
            # Create a new directory in the current working directory
            new_dir_path = os.path.join(os.getcwd(), 'temp_audio_files')
            os.makedirs(new_dir_path, exist_ok=True)
            print("here 2")
            # Save file to disk temporarily to ensure format can be inferred
            temp_file = tempfile.NamedTemporaryFile(dir=new_dir_path, delete=False)
            temp_file.write(file_obj.read())
            temp_file.close()
            print("here 3")
            # Convert audio to .wav format
            audio = AudioSegment.from_file(temp_file.name)
            wav_file_name = f"{voice.id}.wav"  # Use the voice id as the file name
            wav_file_path = os.path.join(new_dir_path, wav_file_name)  # Create path for new .wav file
            audio.export(wav_file_path, format="wav")
            print("Uploading file...")
            # Upload the .wav file to DigitalOcean
            file_url = upload_file(wav_file_path, user.id, 'Audios', None)
            # Update the voice object with the file path
            voice.path = file_url
            voice.save()
            print("here 4")
            # Delete the directory
            shutil.rmtree(new_dir_path)
            print("here 5")
            return voice
        except Exception as e:
            # If any error occurs, delete the voice object and raise the exception
            voice.delete()
            raise serializers.ValidationError("An error occurred while saving the voice: " + str(e))

class UpdateVoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Voices
        fields = ['id', 'user', 'voice_name', 'voice_desc', 'path', 'modified_at', 'created_at']
        extra_kwargs = {
            'modified_at': {'read_only': True},
            'created_at': {'read_only': True},
            'path': {'read_only': True},
        }


class DialPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = DialPlan
        fields = '__all__'
        # depth = 1  # This will include related objects in the serialized output



class DialPlanUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = DialPlan
        fields = '__all__'
        extra_kwargs = {
            'id': {'read_only': True},
            'campaign_id': {'read_only': True},
            'extention_id': {'read_only': True}
        }




class ContactsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contacts
        fields = '__all__'

    def validate(self, data):
        # Nothing as of now
        return data

    def create(self, validated_data):
        # print("validated_data : ", validated_data)
        contacts = super().create(validated_data)
        return contacts
    



class SimInformationSerializer(serializers.ModelSerializer):
    system_password = serializers.CharField(write_only=True)
    sms_balance = serializers.IntegerField(required=False, allow_null=True)
    last_validity_check = serializers.DateTimeField(required=False)  
    
    class Meta:
        model = SimInformation
        fields = ['host', 'sim_imsi', 'phone_no', 'sms_backup_date', 'sms_balance', 'validity', 'system_password', 'last_validity_check']




class UserHostsSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserHosts
        fields = "__all__"



class UserSerializer(serializers.ModelSerializer):
    # hosts = UserHostsSerializer(many=True, read_only=True)


    class Meta:
        model = Users
        fields = ['id', 'name', 'mobile_number', 'status', 'hosts', 'created_at']



class UserSerializer(serializers.ModelSerializer):
    hosts = serializers.SerializerMethodField()

    class Meta:
        model = Users
        fields = ['id', 'name', 'mobile_number', 'status', 'hosts', 'created_at']

    def get_hosts(self, user):
        # Get the list of hosts for the specified user
        user_hosts = UserHosts.objects.filter(user_id=user.id, status=1)

        # Serialize the list of hosts
        serializer = UserHostsSerializer(user_hosts, many=True)

        return serializer.data


class SmsTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SmsTemplate
        fields = '__all__'


class VoiceField(serializers.IntegerField):
    def to_representation(self, value):
        # Make sure value is a Voices object, not an integer
        if isinstance(value, int):
            value = Voices.objects.get(id=value)
        return VoicesSerializer(value).data

    def to_internal_value(self, data):
        return data
    
class TemplateField(serializers.IntegerField):
    def to_representation(self, value):
        # Make sure value is a Voices object, not an integer
        if isinstance(value, int):
            value = SmsTemplate.objects.get(id=value)
            print("*********************************************")
            print(value)
        return SmsTemplateSerializer(value).data

    def to_internal_value(self, data):
        return data


class DialPlanSerializer(serializers.ModelSerializer):
    main_voice_id = VoiceField(required=False, allow_null=True)
    option_voice_id = VoiceField(required=False, allow_null=True)
    template_id = TemplateField(required=False, allow_null=True)
    continue_to = serializers.IntegerField(required=False, allow_null=True)

    class Meta:
        model = DialPlan
        fields = '__all__'

class CampaignSerializer(serializers.ModelSerializer):
    wrong_key_voice = VoicesSerializer(read_only=True)
    no_key_voice = VoicesSerializer(read_only=True)

    class Meta:
        model = Campaign
        fields = '__all__'
    
    def to_internal_value(self, data):
        # Map language names to their codes
        language_name_to_code = {name: code for code, name in Campaign.LANGUAGES}

        # Convert language name to code
        if 'language' in data and data['language'] in language_name_to_code:
            data['language'] = language_name_to_code[data['language']]

        return super().to_internal_value(data)

    def to_representation(self, instance):
        rep = super().to_representation(instance)

        # Replace empty language with None
        if rep.get('language', '') == '':
            rep['language'] = None
        else:
            # Convert language code to name
            language_code_to_name = {code: name for code, name in Campaign.LANGUAGES}
            if rep['language'] in language_code_to_name:
                rep['language'] = language_code_to_name[rep['language']]

        return rep

class CallStatusSerializer(serializers.ModelSerializer):
    host_name = serializers.SerializerMethodField()

    class Meta:
        model = CallStatus
        fields = '__all__'

    def get_host_name(self, obj):
        try:
            return UserHosts.objects.get(id=obj.host.id).host
        except ObjectDoesNotExist:
            return None




class SmsCampaignSerializer(serializers.ModelSerializer):
    template = SmsTemplateSerializer()

    class Meta:
        model = SmsCampaign
        exclude = ('user',)

        
class CallDtmfStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = CallDtmfStatus
        fields = '__all__'



class PhoneDialerSerializer(serializers.ModelSerializer):
    class Meta:
        model = PhoneDialer
        fields = '__all__'

class ApiPhoneDialerSerializer(serializers.ModelSerializer):
    """
    Used by verify_add_to_phone_dialer to ingest and validate
    ref_no, channel_name, surveyor_name, language, etc.
    """
    class Meta:
        model = PhoneDialer
        fields = '__all__'
        # these are auto-set on save
        read_only_fields = ('created_at', 'updated_at')
        extra_kwargs = {
            # we’ll populate these in the view
            'user':     {'required': False},
            'campaign': {'required': False},
        }


    
class SmsDialerSerializer(serializers.ModelSerializer):
    class Meta:
        model = SmsDialer
        fields = '__all__'



class MisscallsSerializer(serializers.ModelSerializer):
    operator = serializers.CharField(source='misscall_management.operator')

    class Meta:
        model = Misscalls
        fields = ['phone_number', 'datetime', 'campaign', 'operator']


class ErrorVerifyPhoneDialerSerializer(serializers.ModelSerializer):
    """
    Tracks any non-200 pushes to staging.sabkiapp.com/push_call_status
    """
    class Meta:
        model = ErrorVerifyPhoneDialer
        fields = '__all__'