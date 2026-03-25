import os
import sys
import django

# Add the project directory to the Python path
sys.path.append('/Pythonic/projects/VoiceAPI/voiceapi')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'voiceapi.voiceapi.settings')
django.setup()
from api.models import PhoneDialer


def get_active_calls_count():
    # Get the count of active calls
    active_calls_count = PhoneDialer.objects.filter(sent_status__in=[1, 3]).count()
    return active_calls_count

if __name__ == '__main__':
    print(get_active_calls_count())