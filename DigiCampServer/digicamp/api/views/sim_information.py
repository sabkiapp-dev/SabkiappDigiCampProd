from django.db.utils import IntegrityError
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from ..models import Users, SimInformation, UserHosts
from ..serializers import SimInformationSerializer
from rest_framework.permissions import AllowAny
from django.utils import timezone
from src.mytime import get_mytime

class SimInformationView(APIView):
    permission_classes = [AllowAny]
    


    def post(self, request, format=None):
        serializer = SimInformationSerializer(data=request.data)
        if serializer.is_valid():
            system_password = serializer.validated_data.pop('system_password')
            host = serializer.validated_data.get('host')
            print("hello "+host)
            try:
                user_host = UserHosts.objects.filter(host=host, status=1).first()
                if user_host is None:
                    return Response({"message": 'Host not available'}, status=status.HTTP_404_NOT_FOUND)
                # Print all data from the UserHosts object for debugging
                if user_host.system_password != system_password:
                    return Response({"message": 'Wrong password'}, status=status.HTTP_400_BAD_REQUEST)
            except UserHosts.DoesNotExist:
                return Response({"message": 'Host not available'}, status=status.HTTP_404_NOT_FOUND)

            # Extract sim_imsi and prepare defaults for update_or_create
            sim_imsi = serializer.validated_data.pop('sim_imsi', None)
            update_fields = {key: value for key, value in serializer.validated_data.items() if value is not None}

            # Check if the phone_no and sms_backup_date are provided in the request
            if 'phone_no' in serializer.validated_data and not serializer.validated_data['phone_no']:
                update_fields.pop('phone_no', None)

            if 'sms_backup_date' in serializer.validated_data and not serializer.validated_data['sms_backup_date']:
                update_fields.pop('sms_backup_date', None)

            # Update sms_backup_date if sms_balance is in the request
            if 'sms_balance' in serializer.validated_data:
                update_fields['sms_backup_date'] = get_mytime().date()

            sim_info, created = SimInformation.objects.update_or_create(
                host=host, 
                sim_imsi=sim_imsi,
                defaults=update_fields
            )

            # Serialize the updated or created object
            sim_info_serializer = SimInformationSerializer(sim_info)

            status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
            return Response(sim_info_serializer.data, status=status_code)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request, format=None):
        print("request", request)
        print("request.query_params", request.query_params)
        host = request.query_params.get('host')
        print("host", host)
        system_password = request.query_params.get('system_password')

        if not host or not system_password:
            return Response({"message": 'Host and system_password are required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user_host = UserHosts.objects.filter(host=host, status=1).first()
            if user_host is None:
                return Response({"message": 'Host not available'}, status=status.HTTP_404_NOT_FOUND)
        except UserHosts.DoesNotExist:
            return Response({"message": 'Host not available'}, status=status.HTTP_404_NOT_FOUND)
        print("user_host", user_host)
        if user_host.system_password == system_password:
            sim_informations = SimInformation.objects.filter(host=host)
            serializer = SimInformationSerializer(sim_informations, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        else:
            return Response({"message": 'Wrong password'}, status=status.HTTP_400_BAD_REQUEST)