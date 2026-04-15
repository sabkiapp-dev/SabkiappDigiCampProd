import threading
import time
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import IsAuthenticated
from ..models.users import Users
from ..models.contacts import Contacts, phone_number_validator
from ..models.campaign import Campaign
from ..serializers import ContactsSerializer
from ..utils import auth_wrapper
from django.db import transaction
from django.db.models import Count
from rest_framework.pagination import PageNumberPagination
from django.db.models import Q
from django.http import JsonResponse
from django.core.exceptions import ValidationError
from src.sabkiapp_server import get_name

class CustomPagination(PageNumberPagination):
    def paginate_queryset(self, queryset, request, view=None):
        self.page_size = request.query_params.get('page_size', self.page_size)
        return super().paginate_queryset(queryset, request, view)

    def get_paginated_response(self, data):
        return Response({
            'links': {
                'next': self.get_next_link(),
                'previous': self.get_previous_link()
            },
            'count': self.page.paginator.count,
            'results': data
        })
@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def get_contacts(request):
    user_id = auth_wrapper(request)
    if not user_id:
        return Response({"message": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)

    
    name_phone_input_query = request.data.get('query', '')
    category_1 = request.data.get('category_1', [])
    category_2 = request.data.get('category_2', [])
    category_3 = request.data.get('category_3', [])
    category_4 = request.data.get('category_4', [])
    category_5 = request.data.get('category_5', [])

    category_1_keywords = [keyword.strip() for keyword in category_1]
    category_2_keywords = [keyword.strip() for keyword in category_2]
    category_3_keywords = [keyword.strip() for keyword in category_3]
    category_4_keywords = [keyword.strip() for keyword in category_4]
    category_5_keywords = [keyword.strip() for keyword in category_5]


    name_phone_query = Q(Q(name__istartswith=name_phone_input_query) | Q(phone_number__istartswith=name_phone_input_query))
 


    category_1_query = Q()
    for category_string in category_1_keywords:
        category_1_query |= Q(category_1__exact=category_string)    


    category_2_query = Q()
    for category_string in category_2_keywords:
        category_2_query |= Q(category_2__exact=category_string)
    

    category_3_query = Q()
    for category_string in category_3_keywords:
        category_3_query |= Q(category_3__exact=category_string)

    category_4_query = Q()
    for category_string in category_4_keywords:
        category_4_query |= Q(category_4__exact=category_string)

    category_5_query = Q()
    for category_string in category_5_keywords:
        category_5_query |= Q(category_5__exact=category_string)

    
    category_final_query = Q()
    if(category_1):
        category_final_query&=category_1_query
    if(category_2):
        category_final_query&=category_2_query
    if(category_3):
        category_final_query&=category_3_query
    if(category_4):
        category_final_query&=category_4_query
    if(category_5):
        category_final_query&=category_5_query
    

    final_query = Q(name_phone_query & category_final_query)
   
    contacts = Contacts.objects.filter(user_id=user_id, status=1).order_by('-id').filter(final_query)
    # contacts = Contacts.objects.filter(user_id=user_id, status=1)
    # Set up pagination with a fixed page size

    page_number = request.data.get('page', 1)

    # Create a mutable copy of the request's query parameters
    query_params = request.GET.copy()

    # Set the page number in the query parameters
    query_params['page'] = page_number

    # Replace the request's query parameters with the modified copy
    request.GET = query_params

    paginator = CustomPagination()
    result_page = paginator.paginate_queryset(contacts, request)
    paginator.request = request

    serializer = ContactsSerializer(result_page, many=True)
    return paginator.get_paginated_response(serializer.data)



@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def add_contacts(request):
    user_id = auth_wrapper(request)
    
    if not user_id:
        return Response({"message": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)

    contacts_data = request.data

    # Remove duplicates from contacts_data
    seen_phone_numbers = set()
    contacts_data = [x for x in contacts_data if not (x['phone_number'] in seen_phone_numbers or seen_phone_numbers.add(x['phone_number']))]
    # print("contacts_data : ", contacts_data)
    new_contacts_data = list()
    updated_contacts_data = list()
    existing_phone_numbers = list()
    invalid_phone_numbers = list()
    get_name_phone_numbers = set()


    for contact_data in contacts_data:
        phone_number = contact_data.get('phone_number')
        contact_data['name'] = contact_data.get('name', "")
        contact_data['phone_number'] = phone_number
        contact_data['category_1'] = contact_data.get('category_1', "Others")
        contact_data['category_2'] = contact_data.get('category_2', "Others")
        contact_data['category_3'] = contact_data.get('category_3', "Others")
        contact_data['category_4'] = contact_data.get('category_4', "Others")
        contact_data['category_5'] = contact_data.get('category_5', "Others")

        # Chech if contact data's all category is no empty or null. if so make them others
        if contact_data['name'] is None:
            contact_data['name'] = ""
        if not contact_data['category_1']:
            contact_data['category_1'] = "Others"
        if not contact_data['category_2']:
            contact_data['category_2'] = "Others"
        if not contact_data['category_3']:
            contact_data['category_3'] = "Others"
        if not contact_data['category_4']:
            contact_data['category_4'] = "Others"
        if not contact_data['category_5']:
            contact_data['category_5'] = "Others"


        # Adding invalid phone numbers to invalid phone_number list
        if phone_number:
            # Validate phone number
            # print("phCatone_number : ", phone_number)
            # print("user_id : ", user_id)
            try:
                phone_number_validator(phone_number)
            except ValidationError:
                invalid_phone_numbers.append(phone_number)
                continue

            
            existing_contact = Contacts.objects.filter(user_id=user_id).filter(phone_number=phone_number).first()

            if existing_contact:
                # If status 0, delete the contact and add it to new_contacts_data
                if existing_contact.status == 0:
                    existing_contact.delete()
                    contact_data['user_id'] = user_id
                    new_contacts_data.append(contact_data)
                    continue
                
                
                if existing_contact.status == 1:
                    
                    # If name is emtpy or null, get from get_name method
                    if not contact_data['name']:
                        # Add in a get_names list
                        
                        get_name_phone_numbers.add(phone_number)



                    # If the name has changed, set pronunciation_status to 0, 
                    if((contact_data['name'] != existing_contact.name and contact_data['name'] != "" ) or contact_data['category_1'] != existing_contact.category_1 or contact_data['category_2'] != existing_contact.category_2 or contact_data['category_3'] != existing_contact.category_3 or contact_data['category_4'] != existing_contact.category_4 or contact_data['category_5'] != existing_contact.category_5):
    
                        existing_contact.name = contact_data['name']
                        existing_contact.category_1 = contact_data['category_1']
                        existing_contact.category_2 = contact_data['category_2']
                        existing_contact.category_3 = contact_data['category_3']
                        existing_contact.category_4 = contact_data['category_4']
                        existing_contact.category_5 = contact_data['category_5']
                        existing_contact.save()

                        # Put the new contact data into the updated contact data
                        updated_contacts_data.append(ContactsSerializer(existing_contact).data)
                        
                        continue    
                    else:
                        # If no change in the contact data, add the phone number to existing_phone_numbers
                        # print("existing_contact : ", existing_contact)
                        existing_phone_numbers.append(phone_number)
                        continue        
            else:
                # If contact does not exist in the database, add it to new_contacts_data
                contact_data['user_id'] = user_id
                # print("new contact_data1 : ", contact_data)
                if not contact_data.get('name'): 
                    get_name_phone_numbers.add(contact_data['phone_number'])
                new_contacts_data.append(contact_data)
                continue
        else:
            invalid_phone_numbers.append(phone_number)
            continue
    
    # Save the new contacts
    new_contacts_serializer = ContactsSerializer(data=new_contacts_data, many=True)
    if new_contacts_serializer.is_valid(raise_exception=True):
        new_contacts_serializer.save()
    

    names = get_name(user_id, list(get_name_phone_numbers))
    print("--names : ", names)
    # Update the names to contacts with user_id and phone_number if not empty
    for phone_number, name in names.items():
        if name:
            Contacts.objects.filter(user_id=user_id, phone_number=phone_number).update(name=name)

    response = Response({
        "message": f"Added data count: {len(new_contacts_data)}, Updated data count: {len(updated_contacts_data)}, Existing phone numbers count: {len(existing_phone_numbers)}, Invalid phone numbers count: {len(invalid_phone_numbers)}",
        "added_data": new_contacts_data,
        "updated_data": updated_contacts_data,
        "existing_phone_numbers": existing_phone_numbers,
        "invalid_phone_numbers": invalid_phone_numbers
    }, status=status.HTTP_201_CREATED)



    return response
from rest_framework.parsers import FileUploadParser
from django.core.files.storage import default_storage
import csv


def convert_csv_to_json(file):
    json_data = []
    reader = csv.DictReader(file)
    for row in reader:
        if 'phone_number' not in row or not row['phone_number']:
            continue
        json_row = {}
        for key, value in row.items():
            if key.lower() == 'sn':  # Ignore 'sn' column
                continue
            if value:
                json_row[key.lower()] = value
        for i in range(1, 6):  # For category_1 to category_5
            category_key = f'category_{i}'
            if category_key not in json_row or not json_row[category_key]:
                json_row[category_key] = "Others"
        json_data.append(json_row)
    return json_data

import concurrent.futures
import time

def process_contact(contact_data, user_id, new_contacts_data, get_name_phone_numbers, updated_contacts_data, existing_phone_numbers, invalid_phone_numbers):
    phone_number = contact_data.get('phone_number')
    contact_data['name'] = contact_data.get('name', "")
    contact_data['phone_number'] = phone_number
    contact_data['category_1'] = contact_data.get('category_1', "Others")
    contact_data['category_2'] = contact_data.get('category_2', "Others")
    contact_data['category_3'] = contact_data.get('category_3', "Others")
    contact_data['category_4'] = contact_data.get('category_4', "Others")
    contact_data['category_5'] = contact_data.get('category_5', "Others")

    # Check if contact data's all category is not empty or null. if so make them others
    if contact_data['name'] is None:
        contact_data['name'] = ""
    if not contact_data['category_1']:
        contact_data['category_1'] = "Others"
    if not contact_data['category_2']:
        contact_data['category_2'] = "Others"
    if not contact_data['category_3']:
        contact_data['category_3'] = "Others"
    if not contact_data['category_4']:
        contact_data['category_4'] = "Others"
    if not contact_data['category_5']:
        contact_data['category_5'] = "Others"

    # Adding invalid phone numbers to invalid phone_number list
    if phone_number:
        # Validate phone number
        try:
            phone_number_validator(phone_number)
        except ValidationError:
            invalid_phone_numbers.append(phone_number)
            return new_contacts_data, get_name_phone_numbers, updated_contacts_data, existing_phone_numbers, invalid_phone_numbers

        existing_contact = Contacts.objects.filter(user_id=user_id).filter(phone_number=phone_number).first()

        if existing_contact:
            # If status 0, delete the contact and add it to new_contacts_data
            if existing_contact.status == 0:
                existing_contact.delete()
                contact_data['user_id'] = user_id
                new_contacts_data.append(contact_data)
            elif existing_contact.status == 1:
                # If name is empty or null, get from get_name method
                if not contact_data['name']:
                    # Add in a get_names list
                    get_name_phone_numbers.add(phone_number)

                # If the name has changed, set pronunciation_status to 0, 
                if((contact_data['name'] != existing_contact.name and contact_data['name'] != "" ) or contact_data['category_1'] != existing_contact.category_1 or contact_data['category_2'] != existing_contact.category_2 or contact_data['category_3'] != existing_contact.category_3 or contact_data['category_4'] != existing_contact.category_4 or contact_data['category_5'] != existing_contact.category_5):
                    existing_contact.name = contact_data['name']
                    existing_contact.category_1 = contact_data['category_1']
                    existing_contact.category_2 = contact_data['category_2']
                    existing_contact.category_3 = contact_data['category_3']
                    existing_contact.category_4 = contact_data['category_4']
                    existing_contact.category_5 = contact_data['category_5']
                    existing_contact.save()

                    # Put the new contact data into the updated contact data
                    updated_contacts_data.append(ContactsSerializer(existing_contact).data)
                else:
                    # If no change in the contact data, add the phone number to existing_phone_numbers
                    existing_phone_numbers.append(phone_number)
        else:
            # If contact does not exist in the database, add it to new_contacts_data
            contact_data['user_id'] = user_id
            if not contact_data.get('name'): 
                get_name_phone_numbers.add(contact_data['phone_number'])
            new_contacts_data.append(contact_data)
    else:
        invalid_phone_numbers.append(phone_number)

    return new_contacts_data, get_name_phone_numbers, updated_contacts_data, existing_phone_numbers, invalid_phone_numbers

from django.db import IntegrityError, transaction, connection
import concurrent.futures


@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def upload_contacts(request):
    user_id = auth_wrapper(request)
    
    if not user_id:
        return Response({"message": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)


    file_obj = request.data['file']
    file_name = default_storage.save('tmp/' + file_obj.name, file_obj)
    file = default_storage.open(file_name, 'r')

    # Convert the CSV file to JSON
    contacts_data = convert_csv_to_json(file)

    # Remove duplicates from contacts_data
    seen_phone_numbers = set()
    contacts_data = [x for x in contacts_data if not (x['phone_number'] in seen_phone_numbers or seen_phone_numbers.add(x['phone_number']))]
    print("total contacts_data : ", len(contacts_data))
    # time.sleep(20)
    

    contacts_processed = 0
    start_time = time.time()
    new_contacts_data = []
    get_name_phone_numbers = set()
    updated_contacts_data = []
    existing_phone_numbers = []
    invalid_phone_numbers = []
    contacts_data = contacts_data[:200]

    # Use a ThreadPoolExecutor to process the contacts in parallel
    with concurrent.futures.ThreadPoolExecutor() as executor:
        results = executor.map(process_contact, contacts_data, [user_id]*len(contacts_data), [new_contacts_data]*len(contacts_data), [get_name_phone_numbers]*len(contacts_data), [updated_contacts_data]*len(contacts_data), [existing_phone_numbers]*len(contacts_data), [invalid_phone_numbers]*len(contacts_data))

    # Update new_contacts_data, get_name_phone_numbers, updated_contacts_data, existing_phone_numbers, invalid_phone_numbers with the results from the threads
    for result in results:
        new_contacts_data, get_name_phone_numbers, updated_contacts_data, existing_phone_numbers, invalid_phone_numbers = result
        contacts_processed += 1
        elapsed_time = time.time() - start_time
        if elapsed_time >= 60:  # 60 seconds = 1 minute
            print(f"Processed {contacts_processed} contacts in the last minute.")
            start_time = time.time()
            contacts_processed = 0

    
    def save_contact(contact_data):
        # Close old database connections to prevent usage of stale connections
        # connection.close()
        try:
            with transaction.atomic():
                contact = Contacts.objects.create(**contact_data)
                print(f"Saved contact: {contact_data}")
        except IntegrityError:
            print(f"IntegrityError occurred while saving contact: {contact_data}")

    # Assuming new_contacts_data is defined here
    print("total new_contacts_data : ", len(new_contacts_data))

    # Save the new contacts
    with concurrent.futures.ThreadPoolExecutor() as executor:
        executor.map(save_contact, new_contacts_data)

    def update_names(user_id, get_name_phone_numbers):
        names = get_name(user_id, list(get_name_phone_numbers))
        print("--names : ", names)
        # Update the names to contacts with user_id and phone_number if not empty
        for phone_number, name in names.items():
            if name:
                Contacts.objects.filter(user_id=user_id, phone_number=phone_number).update(name=name)

    # Start a new thread that will run the update_names function
    update_thread = threading.Thread(target=update_names, args=(user_id, get_name_phone_numbers))
    update_thread.start()

    response = Response({
        "message": f"Added data count: {len(new_contacts_data)}, Updated data count: {len(updated_contacts_data)}, Existing phone numbers count: {len(existing_phone_numbers)}, Invalid phone numbers count: {len(invalid_phone_numbers)}",
        "added_data": new_contacts_data,
        "updated_data": updated_contacts_data,
        "existing_phone_numbers": existing_phone_numbers,
        "invalid_phone_numbers": invalid_phone_numbers
    }, status=status.HTTP_201_CREATED)

    # Delete the temporary file
    default_storage.delete(file_name)

    return response

@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def get_unique_categories(request):
    user_id = auth_wrapper(request)
    if not user_id:
        return Response({"message": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)
    
    

    # Get the category keywords from request.data
    category_1 = request.data.get('category_1', [])
    category_2 = request.data.get('category_2', [])
    category_3 = request.data.get('category_3', [])
    category_4 = request.data.get('category_4', [])
    category_5 = request.data.get('category_5', [])

    # Prepare category queries
    category_1_query = Q(category_1__in=category_1) if category_1 else Q()
    category_2_query = Q(category_2__in=category_2) if category_2 else Q()
    category_3_query = Q(category_3__in=category_3) if category_3 else Q()
    category_4_query = Q(category_4__in=category_4) if category_4 else Q()
    category_5_query = Q(category_5__in=category_5) if category_5 else Q()

    # Combine category queries
    category_final_query = category_1_query & category_2_query & category_3_query & category_4_query & category_5_query


    # Filter contacts
    contacts = Contacts.objects.filter(user_id=user_id, status=1).filter(category_final_query)

    unique_category_1 = list(contacts.values_list('category_1', flat=True).distinct())
    unique_category_2 = list(contacts.values_list('category_2', flat=True).distinct())
    unique_category_3 = list(contacts.values_list('category_3', flat=True).distinct())
    unique_category_4 = list(contacts.values_list('category_4', flat=True).distinct())
    unique_category_5 = list(contacts.values_list('category_5', flat=True).distinct())

    unique_categories = {
        'category_1': unique_category_1,
        'category_2': unique_category_2,
        'category_3': unique_category_3,
        'category_4': unique_category_4,
        'category_5': unique_category_5
    }

    return JsonResponse(unique_categories)

@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def delete_contacts(request):
    user_id = auth_wrapper(request)
    if not user_id:
        return Response({"message": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)

    try:
        phone_numbers = request.data.get("phone_numbers")
        if not isinstance(phone_numbers, list):
            return Response({"message": "Invalid data format. 'phone_numbers' should be a list."}, status=status.HTTP_400_BAD_REQUEST)

        Contacts.objects.filter(user_id=user_id, phone_number__in=phone_numbers).update(status=0)

        return Response({"message": "Contacts deleted successfully."}, status=status.HTTP_200_OK)
    except Exception as e:
        # Handle unexpected errors
        return Response({"message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def category_contacts_delete(request):
    user_id = request.user.id
    categories = request.data

    print("Received request for user_id:", user_id)
    print("Categories received:", categories)

    # Initialize the base query with user_id
    base_query = Q(user_id=user_id)

    # Initialize an empty list to hold category queries
    category_queries = []

    # Build the category conditions
    for key, values in categories.items():
        # If values is a string, convert it to a list
        if isinstance(values, str):
            values = [values]

        if values:  # Check if the list is not empty
            # Create a Q object for each value and combine them using OR
            category_query = Q(**{key: values[0]})
            for val in values[1:]:
                category_query |= Q(**{key: val})
            # Add this category query to the list
            category_queries.append(category_query)

    # Combine all category queries using AND
    for q in category_queries:
        base_query &= q

    print("Final query:", base_query)

    # Count contacts before update where status=1
    count_before = Contacts.objects.filter(base_query, status=1).count()
    print(f"Contacts count before update: {count_before}")

    # Update the contacts where status=1
    updated_count = Contacts.objects.filter(base_query, status=1).update(status=0)

    print(f"Deleted {updated_count} contacts")

    return Response({"message": f"Contacts deleted successfully. Deleted {updated_count} contacts."}, status=200)




@api_view(['POST'])
@permission_classes([IsAuthenticated])
def count_category_contacts(request):
    user_id = request.user.id
    categories = request.data

    print("Received count request for user_id:", user_id)
    print("Categories received for counting:", categories)

    # Initialize the base query with user_id
    base_query = Q(user_id=user_id)

    # Build the category conditions
    for key, values in categories.items():
        if values:  # Check if the list is not empty
            category_query = Q(**{key: values[0]})
            for val in values[1:]:
                category_query |= Q(**{key: val})
            base_query &= category_query

    print("Final query for counting:", base_query)

    # Count contacts
    contacts_count = Contacts.objects.filter(base_query).count()
    print(f"Contacts count based on query: {contacts_count}")

    return Response({"message": "Contacts count retrieved successfully.", "count": contacts_count}, status=200)
