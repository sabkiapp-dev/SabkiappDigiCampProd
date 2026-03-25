from django.http import JsonResponse
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import IsAuthenticated
from ..models.sms_template import SmsTemplate
from django.db import IntegrityError
from django.http import JsonResponse
from django.db.models import Q
from django.core.paginator import Paginator
from ..utils import auth_wrapper 
from rest_framework import status
from rest_framework.response import Response
from rest_framework.exceptions import NotFound
@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def add_sms_template(request):
    template_name = request.data.get('template_name')
    template = request.data.get('template')

    if not template_name or not template:
        return JsonResponse({'message': 'Both template_name and template are required.'}, status=400)

    try:
        SmsTemplate.objects.create(user=request.user, template_name=template_name, template=template)
    except IntegrityError:
        return JsonResponse({'message': 'A template with this name already exists for this user.'}, status=400)

    return JsonResponse({'message': 'Template added successfully.'})




@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])

def get_sms_template(request):
    search_query = request.GET.get('search', '')
    order = request.GET.get('order', 'id desc')
    page_number = request.GET.get('page', 1)
    page_size = request.GET.get('page_size', 25)
    status = request.GET.get('status', None)

    templates = SmsTemplate.objects.filter(user=request.user)

    if search_query:
        templates = templates.filter(
            Q(template_name__icontains=search_query) | Q(template__icontains=search_query)
        )

    if status == '1':
        templates = templates.filter(status=1)

    # Split the order parameter into field and direction
    field, direction = order.split()

    # If direction is 'desc', prepend the field name with '-'
    if direction.lower() == 'desc':
        field = '-' + field

    templates = templates.order_by(field)

    paginator = Paginator(templates, page_size)  
    page = paginator.get_page(page_number)
    templates_list = list(page.object_list.values('id', 'template_name', 'template', 'status'))

    return JsonResponse({
        'current_page': page.number,
        'total_pages': paginator.num_pages,
        'templates': templates_list
    })



@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def update_sms_template_status(request):
    # extract user_id from token
    user_id = auth_wrapper(request)
    if not user_id:
        return Response({"message": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)
    # Extract the template_id and new_status from the request data
    template_id = request.data.get('template_id')
    new_status = request.data.get('status')

    # Check if the template_id and new_status are provided
    if template_id is None or new_status is None:
        return Response({"message": "Template ID and status are required."}, status=status.HTTP_400_BAD_REQUEST)
    
    # Retrieve the template with the given template_id for the user
    try:
        template = SmsTemplate.objects.get(id=template_id, user_id=user_id)
    except SmsTemplate.DoesNotExist:
        return Response({"message": "SMS Template not found."}, status=status.HTTP_404_NOT_FOUND)
    
    # Update the template's status
    template.status = new_status
    template.save(update_fields=['status'])

    # Return success response
    return Response({"message": "SMS Template status updated successfully."}, status=status.HTTP_200_OK)


@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def update_sms_template_name(request):
    # Get the user from the bearer token
    user = request.user

    # Get the new name and template id from the request data
    new_name = request.data.get('name')
    template_id = request.data.get('id')

    if not new_name:
        return Response({'message': 'New name is required.'}, status=400)

    if not template_id:
        return Response({'message': 'Template id is required.'}, status=400)

    # Check if a template with the new name already exists for the user
    if SmsTemplate.objects.filter(template_name=new_name, user=user).exists():
        return Response({'message': 'A template with this name already exists.'}, status=400)

    # Get the template to update
    try:
        template = SmsTemplate.objects.get(id=template_id, user=user)
    except SmsTemplate.DoesNotExist:
        raise NotFound('SMS template not found for this user.')

    # Update the template name
    template.template_name = new_name
    template.save()

    # Return a success response
    return Response({'message': 'Template name updated successfully.'})