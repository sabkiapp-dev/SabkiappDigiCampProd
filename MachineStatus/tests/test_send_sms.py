#!/usr/bin/env python3
import requests
import argparse

MACHINE_URL = "http://192.168.8.50"  # Replace with your machine URL
SMS_API_URL = f"{MACHINE_URL}:80/sendsms"

def send_test_sms(phone_number, message, port):
    """Send a test SMS using the SMS API."""
    params = {
        'username': 'smsuser',
        'password': 'smspwd',
        'phonenumber': phone_number,
        'message': message,
        'port': port,
    }

    try:
        # Create a prepared request to see the final URL
        prepared_request = requests.Request('GET', SMS_API_URL, params=params).prepare()
        print(f"\nFinal SMS API URL: {prepared_request.url}")

        # Make the actual request
        print(f"\nSending SMS to {phone_number} via port {port}...")
        response = requests.get(SMS_API_URL, params=params)
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        
        return response.status_code == 200
    except Exception as e:
        print(f"Error sending SMS: {str(e)}")
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Test SMS sending API')
    # parser.add_argument('phone', help='Phone number to send SMS to')
    # parser.add_argument('message', help='Message content')
    # parser.add_argument('port', type=int, help='Port number to use')
    
    
    # args = parser.parse_args()
    
    success = send_test_sms("9934445076", "Test SMS", 1)
    print(f"\nSMS sending {'successful' if success else 'failed'}")