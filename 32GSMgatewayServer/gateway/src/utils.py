from django.conf import settings



# Function to read API credentials from Django settings
def read_api_credentials():
    return {
        'system_password': settings.API_CREDENTIALS['SYSTEM_PASSWORD'],
        'host': settings.API_CREDENTIALS['HOST'],
    }