from datetime import datetime, timedelta, timezone
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.exceptions import ValidationError
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import IsAuthenticated
from ..models.contacts import Contacts
from ..models import MisscallManagement
from ..models import Campaign
import secrets
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework import status
from ..models import Misscalls
from ..serializers import MisscallsSerializer, CampaignSerializer
from rest_framework.pagination import PageNumberPagination
from django.core.paginator import Paginator, EmptyPage
from django.http import Http404
from django.shortcuts import get_object_or_404
from src.sabkiapp_server import store_misscall_on_sabkiapp

@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def add_misscall_operator(request):
    # Get the user_id from the request object and verify that the user exists
    user_id = request.user.id
    if user_id is None:
        return JsonResponse({'message': 'User not found'}, status=400)
    # Take campaign_associated from the request data and verify that it exists and is associated with the user
    campaign_associated = request.data.get('campaign_associated')
    if campaign_associated is not None:
        # Verify that the campaign is associated with the user
        user_campaign = Campaign.objects.filter(user_id=user_id, id=campaign_associated)
        if not user_campaign.exists():
            return JsonResponse({'message': 'Campaign not associated with user'}, status=400)
    # If operator is None or empty, return an error
    operator = request.data.get('operator')
    if operator is None or operator == '':
        return JsonResponse({'message': 'Operator is required'}, status=400)
    # If operator length not 11, and all should be digits, return an error
    if len(operator) < 10 or len(operator) > 11 or not operator.isdigit():
        return JsonResponse({'message': 'Invalid operator'}, status=400)

    # For operator found in the request data, then update else create

    try:
        if MisscallManagement.objects.filter(user_id=user_id, operator=operator).exists():
            return JsonResponse({'message': f'This Operator {operator} already exist'}, status=400)

        # Get the Campaign instance with the given ID
        campaign_associated_id = request.data.get('campaign_associated')
        if campaign_associated_id is not None:
            try:
                campaign_associated = Campaign.objects.get(id=campaign_associated_id)
            except Campaign.DoesNotExist:
                return JsonResponse({'message': 'Campaign not found'}, status=400)
        else:
            campaign_associated = None

        management_id = secrets.token_hex(5)  # Generate a 10 characters long alphanumeric string
        # Keep generating a new management_id until we get a unique one
        while MisscallManagement.objects.filter(management_id=management_id).exists():
            management_id = secrets.token_hex(5)
        MisscallManagement.objects.create(
            user_id=user_id,
            operator=operator,
            description=request.data.get('description'),
            associated_number=request.data.get('associated_number'),
            campaign_associated=campaign_associated,
            management_id=management_id
        )
        return JsonResponse({'message': 'Created successfully'}, status=201)
    except (KeyError, TypeError, ValueError) as e:
        return JsonResponse({"message": 'Bad Request '+str(e)}, status=400)
    except ValidationError as e:
        return JsonResponse({"message": str(e)}, status=400)

@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def update_misscall_operator_status(request):
    # Get the user_id from the request object and verify that the user exists
    user_id = request.user.id
    if user_id is None:
        return JsonResponse({'message': 'User not found'}, status=400)
    # Take id and status from the request data and verify that they exist
    id = request.data.get('id')
    status = request.data.get('status')
    if id is None or status is None:
        return JsonResponse({'message': 'Invalid payload'}, status=400)

    # Verify that the MisscallManagement object exists and is associated with the user
    try:
        misscall_management = MisscallManagement.objects.get(id=id, user_id=user_id)
    except MisscallManagement.DoesNotExist:
        return JsonResponse({'message': 'MisscallManagement object not found or not associated with user'}, status=404)

    # Update the status
    misscall_management.status = status
    misscall_management.save()

    return JsonResponse({'message': 'Updated successfully'}, status=200)

@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def get_misscall_operators(request):
    # Get the user_id from the request object
    user_id = request.user.id

    # Fetch all MisscallManagement objects associated with the user
    misscall_managements = MisscallManagement.objects.filter(user_id=user_id)

    

    # Convert the QuerySet to a list of dictionaries
    data = []
    for misscall_management in misscall_managements:
        try:
            if misscall_management.campaign_associated is not None:
                campaign_associated = get_object_or_404(Campaign, id=misscall_management.campaign_associated.id)
                campaign_serializer = CampaignSerializer(campaign_associated)
                campaign_data = campaign_serializer.data
            else:
                campaign_data = None
        except Http404:
            campaign_data = None
        misscall_data = {
            'id': misscall_management.id,  
            'description': misscall_management.description,
            'operator': misscall_management.operator,
            'associated_number': misscall_management.associated_number,
            'user_id': misscall_management.user_id,
            'campaign_associated': campaign_data,  # Use the serialized data or None
            'status': misscall_management.status,
            'management_id': misscall_management.management_id
        }
        data.append(misscall_data)

    # Return the data as JSON
    return JsonResponse(data, safe=False)


@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def edit_misscall_operator(request):
    # Get the operator from the request data
    operator = request.data.get('operator')

    # Check if operator is provided
    if not operator:
        return JsonResponse({"message": 'Operator is required'}, status=400)

    # Get the user_id from the request object
    user_id = request.user.id

    # Fetch the MisscallManagement object associated with the operator and user
    try:
        misscall_management = MisscallManagement.objects.get(operator=operator, user_id=user_id)
    except MisscallManagement.DoesNotExist:
        return JsonResponse({"message": 'No MisscallManagement found for this operator and user'}, status=404)

    # Get the new associated_number from the request data
    associated_number = request.data.get('associated_number')

    # Check if associated_number is provided and valid
    if associated_number:
        if len(associated_number) != 10 or int(associated_number[0]) < 5:
            return JsonResponse({'message': 'Associated number must be a valid number'}, status=400)
        misscall_management.associated_number = associated_number

    # Update the other fields
    misscall_management.description = request.data.get('description', misscall_management.description)
# Get the Campaign instance with the given ID
    campaign_associated_id = request.data.get('campaign_associated')
    if campaign_associated_id is not None:
        try:
            campaign_associated = Campaign.objects.get(id=campaign_associated_id)
        except Campaign.DoesNotExist:
            return JsonResponse({'message': 'Campaign not found'}, status=400)
        misscall_management.campaign_associated = campaign_associated

    misscall_management.status = request.data.get('status', misscall_management.status)

    # Save the changes
    misscall_management.save()

    return JsonResponse({'message': 'Updated successfully'}, status=200)



class CustomPageNumberPagination(PageNumberPagination):
    def get_paginated_response(self, data):
        return Response({
            'count': self.page.paginator.count,
            'results': data
        })


def get_misscalls_list(user, operator=None, sort='id desc', page_size=25, page_no=1, complete_data=False):
    if operator:
        misscalls = Misscalls.objects.filter(misscall_management__operator=operator, misscall_management__user=user)
    else:
        misscalls = Misscalls.objects.filter(misscall_management__user=user)

    if not complete_data:
        # Split the sort parameter into field and direction
        field, direction = sort.split()

        # Check if field is a valid field in the Misscalls model
        if field not in [f.name for f in Misscalls._meta.get_fields()]:
            raise ValueError(f"Invalid sort field: {field}")

        # If direction is 'desc', prepend the field name with '-'
        if direction.lower() == 'desc':
            field = '-' + field

        misscalls = misscalls.order_by(field)

    if complete_data:
        serializer = MisscallsSerializer(misscalls, many=True)
        misscalls_list = serializer.data

        # Add a serial number to each item
        for i, item in enumerate(misscalls_list, start=1):
            item['serialnumber'] = i

        return misscalls_list, None, None

    paginator = Paginator(misscalls, page_size)  # Use Django's built-in Paginator

    try:
        page = paginator.page(page_no)
    except EmptyPage:
        # If the page is out of range, return an empty list
        misscalls_list = []
    else:
        serializer = MisscallsSerializer(page.object_list, many=True)
        misscalls_list = serializer.data

        # Add a serial number to each item
        for i, item in enumerate(misscalls_list, start=(page.number-1)*paginator.per_page+1):
            item['serialnumber'] = i

    return misscalls_list, page.number if misscalls_list else None, paginator.num_pages
@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def view_misscalls(request):
    operator = request.data.get('operator', None)
    sort = request.data.get('sort', 'id desc')
    page_size = request.data.get('page_size', 25)
    page_no = request.data.get('page_no', 1)

    user = request.user

    try:
        misscalls_list, current_page, total_pages = get_misscalls_list(user, operator, sort, page_size, page_no)
    except ValueError as e:
        return Response({"message": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    return Response({
        'current_page': current_page,
        'total_pages': total_pages,
        'data': misscalls_list,
        'message': "Misscalls Retrieved Successfully" if misscalls_list else "Data not found"
    }, status=status.HTTP_200_OK)


from django.http import FileResponse
import csv
import os
import pandas as pd
from django.http import FileResponse

def generate_misscalls_csv_report(user_id, data):
    # Check if data is empty
    if not data:
        return Response({"message": "No data to generate CSV"}, status=status.HTTP_200_OK)

    # Define the headers for the CSV file
    headers = ['serialnumber'] + list(data[0].keys())

    # Open the CSV file in write mode
    with open(f'misscalls_report_{user_id}.csv', 'w', newline='') as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=headers)

        # Write the headers to the CSV file
        writer.writeheader()

        # Write the data to the CSV file
        for row in data:
            writer.writerow(row)

    # Open the CSV file in binary mode and return it as a FileResponse
    csv_file = open(f'misscalls_report_{user_id}.csv', 'rb')
    response = FileResponse(csv_file, as_attachment=True, filename=f'misscalls_report_{user_id}.csv')
    return response


def generate_misscalls_excel_response(user_id, data):
    # Generate the CSV report
    csv_response = generate_misscalls_csv_report(user_id, data)

    # Read the CSV file into a pandas DataFrame
    df = pd.read_csv(f'misscalls_report_{user_id}.csv')

    # Write the DataFrame to an Excel file
    df.to_excel(f'misscalls_report_{user_id}.xlsx', index=False)

    # Open the Excel file in binary mode and return it as a response
    excel_file = open(f'misscalls_report_{user_id}.xlsx', 'rb')
    response = FileResponse(excel_file, as_attachment=True, filename=f'misscalls_report_{user_id}.xlsx')
    return response

@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def download_misscalls_report(request):
    user = request.user
    operator = request.GET.get('operator', None)
    report_type = request.GET.get('type')

    try:
        misscalls_list, _, _ = get_misscalls_list(user, operator, None, None, None, True)
    except ValueError as e:
        return Response({"message": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    # delete all the .xlsx and .csv files from the directory starting with misscalls_report_
    files = [f for f in os.listdir('.') if os.path.isfile(f) and f.startswith('misscalls_report_')]
    for file in files:
        os.remove(file)
    

    if report_type == 'excel':
        return generate_misscalls_excel_response(user.id, misscalls_list)
    elif report_type == 'csv':
        return generate_misscalls_csv_report(user.id, misscalls_list)
    
    return Response({"message": "Invalid report type"}, status=status.HTTP_400_BAD_REQUEST)



from django.db.models.functions import TruncDate
def update_past_misscall_to_misscalls(phone_number, date_time, misscall_management_id):    
    # Convert the date_time string to a datetime object
    try:
        date_time = datetime.strptime(date_time, "%Y-%m-%d %H:%M:%S.%f")
    except ValueError:
        date_time = datetime.strptime(date_time, "%Y-%m-%d %H:%M:%S")
    # Extract the date from date_time
    date = date_time.date()


    # Check if the Misscalls object already exists
    if Misscalls.objects.annotate(date=TruncDate('datetime')).filter(phone_number=phone_number, date=date).exists():
        return False

    # Create a new Misscalls object
    Misscalls.objects.create(
        phone_number=phone_number,
        datetime=date_time,
        misscall_management_id=misscall_management_id
    )

    return True
            

def update_past_misscalls_to_contacts(user_id, phone_number, operator, date_time):
    # Convert the date_time string to a datetime object
    try:
        date_time = datetime.strptime(date_time, "%Y-%m-%d %H:%M:%S.%f")
    except ValueError:
        date_time = datetime.strptime(date_time, "%Y-%m-%d %H:%M:%S")
    # Extract the date from date_time
    date = date_time.date()

    # Check if the Contacts object already exists
    if Contacts.objects.filter(phone_number=phone_number, user_id=user_id).exists():
        return False

    # Create a new Contacts object
    Contacts.objects.create(
        phone_number=phone_number,
        user_id=user_id,
        category_1="misscall",
        category_2=operator,
        category_3=str(date),
        name="",
        status=1
    )

    return True


def update_misscall_management(user, operator, date):
 

    # Find the entry with the given user, operator, and status=1
    entry = MisscallManagement.objects.filter(user=user, operator=operator, status=1).first()

    if entry is not None:
        # Update the update_date field
        entry.update_date = date
        entry.save()

    return entry

def add_0_padding(operator):
    # If operator is 10 digits and first digit is no 0, add 0 at the beginning
    if len(operator) == 10 and operator[0] != '0':
        operator = '0' + operator
    return operator

@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def update_past_misscalls(request):
    # Get the user_id from the request object
    user_id = request.user.id

    # Get the file from the form data
    file = request.FILES.get('misscalls_file')

    if not file:
        return Response({"message": "No file was uploaded"}, status=status.HTTP_400_BAD_REQUEST)
    
    # Check if the file is a CSV or Excel file
    if not (file.name.endswith('.csv') or file.name.endswith('.xlsx')):
        return Response({"message": "Invalid file format. Please upload a CSV or Excel file"}, status=status.HTTP_400_BAD_REQUEST)
    

    # Read the file into a pandas DataFrame
    if file.name.endswith('.csv'):
        df = pd.read_csv(file)
    elif file.name.endswith('.xlsx'):
        df = pd.read_excel(file)

    # Rename the columns if they exist
    df.rename(columns={
        'NumberId': 'operator',
        'CallerNumber': 'phone_number',
        'CallDateTime': 'date_time'
    }, inplace=True)

    if 'operator' in df.columns:
        df['operator'] = df['operator'].astype(str)

    
    
    # get only first 100 rows
    df = df.head(100)

    latest_date = '2022-02-17 11:34:14'
    latest_operator = '0'
    for index, row in df.iterrows():
        print("index : ", index+1)
        
        # Get the operator and associated_number from the row
        operator = row.get('operator')
        phone_number = row.get('phone_number')
        date_time = row.get('date_time')
        phone_number = str(phone_number)
        operator = str(operator)



        # Convert the date_time string to a datetime object
        if isinstance(date_time, str):
            try:
                # Convert the date_time string to a datetime object
                date_time_obj = datetime.strptime(date_time, "%d-%m-%Y %H:%M:%S")
                # Convert the datetime object back to a string in the desired format
                date_time = date_time_obj.strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                print("Invalid date_time format")


        # Validate if date_time is in the correct format
        try:
            pd.to_datetime(date_time)
        except ValueError:
            print("Invalid date_time format")
            continue

        # compare the date_time with the latest_date, if it is newer than the latest_date, update the latest_date and latest_operator
        if date_time > latest_date:
            latest_date = date_time
            latest_operator = operator

        
        operator = add_0_padding(operator)

        

        # Validate if operator is in the correct format, is 11 digits long and starts with 0 and all are digits
        if len(operator) != 11 or not operator.isdigit() or operator[0] != '0':
            print("Invalid operator format ", operator, len(operator), operator.isdigit(), operator[0] != "0")
            continue  


        # Validate if phone_number is in the correct format, starts with greater than 5 and is 10 digits long
            
        try:
            misscall_management = MisscallManagement.objects.get(operator=operator, user_id=user_id, status=1)
            misscall_management_id = misscall_management.id
            management_id = misscall_management.management_id

        except MisscallManagement.DoesNotExist:
            management_id = 0
            misscall_management_id = 0
        
                                                            
        response_sabkiapp_server = store_misscall_on_sabkiapp(phone_number, management_id, operator, user_id, True, date_time)


        if len(phone_number) != 10 or int(phone_number[0]) < 5:
            print("Invalid phone number format")
            continue
        
        response_misscalls = update_past_misscall_to_misscalls(phone_number, date_time, misscall_management_id)
        response_contacts = update_past_misscalls_to_contacts(user_id, phone_number, operator, date_time)
                

    latest_operator = add_0_padding(latest_operator)
    print("latest_date : ", latest_date)

    print("latest_operator : ", latest_operator)
    print("user_id : ", user_id)
    # get only date from the latest_date
    latest_date = latest_date.split(' ')[0]
    # make the latest data one day before
    latest_date = datetime.strptime(latest_date, "%Y-%m-%d") - timedelta(days=1)
    latest_date = latest_date.strftime("%Y-%m-%d")
    response = update_misscall_management(user_id, latest_operator, latest_date)
    return Response({"message": "Misscalls updated successfully"}, status=status.HTTP_200_OK)