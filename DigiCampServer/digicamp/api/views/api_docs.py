from django.http import JsonResponse
from django.conf import settings
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import IsAuthenticated
import os
import json


@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def get_api_docs(request):
    if request.user.is_superuser:
        filename = 'api_docs_superuser.json'
    else:
        filename = 'api_docs.json'

    with open(os.path.join(settings.BASE_DIR, 'digicamp_server', filename)) as f:
        data = json.load(f)
    return JsonResponse(data, safe=False)