from rest_framework import status
from api.models.sms_template import SmsTemplate
from api.models.contacts import Contacts
from src.sabkiapp_server import get_name
from django.core.exceptions import ObjectDoesNotExist
from rest_framework.response import Response


def get_sms_message(user_id, template_id, phone_number):
    # Check if template_id exists for the user
    try:
        template = SmsTemplate.objects.get(user_id=user_id, id=template_id).template
    except ObjectDoesNotExist:
        return Response({"message": "Invalid template_id"}, status=status.HTTP_400_BAD_REQUEST)
    
    
    # Check if template contains "{name}"
    if "{name}" in template:
        # Fetch the corresponding name from the Contacts table
        try:
            contact = Contacts.objects.get(user_id=user_id, phone_number=phone_number)
            name = contact.name
        except ObjectDoesNotExist:
            name = ""
        if not name:
           names = get_name(user_id, [phone_number])
           name = names.get(phone_number, "")

        # Replace "{name}" in the template with the fetched name
        message = template.replace("{name}", name)

    else:
        message = template

    return message