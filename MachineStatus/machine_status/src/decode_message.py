import re
from datetime import datetime


def extract_validity_and_phone_vodafone(message):
    # Define the pattern for extracting validity and phone
    validity_pattern = r'Vldty\s*:\s*(\d{2})-(\d{2})-(\d{4})'  # Pattern for validity date
    phone_pattern = r'MSISDN:\s*([\d]+)'  # Pattern for phone number

    # Search for the patterns in the message (case-insensitive)
    validity_match = re.search(validity_pattern, message, re.IGNORECASE)
    phone_match = re.search(phone_pattern, message)

    validity = None
    phone = None

    # Extract validity date
    if validity_match:
        day, month, year = validity_match.groups()
        validity = f"{year}-{month}-{day}"

    # Extract phone number
    if phone_match:
        phone = phone_match.group(1)

    print(f"validity: {validity}, checking phone: {phone}, message: {message}")

    return validity, phone


def extract_phone_airtel(message):
    # Use regex to find the mobile number (last 10 digits)
    match = re.search(r'(\d{10})(?!\d)', message)
    
    if match:
        # Extract and return the last 10 digits as the mobile number
        return match.group(1)[-10:]
    else:
        return None  # Return None if no mobile number is found
    


def extract_validity_airtel(message):
    # Use regex to find the validity date pattern
    pattern = r'Validity: (\d{1,2}\s\w+\s\d{4})'
    match = re.search(pattern, message)
    
    if match:
        validity_str = match.group(1)
        # Convert the validity date string to datetime object
        validity_date = datetime.strptime(validity_str, '%d %b %Y')
        # Format the datetime object to 'YYYY-MM-DD'
        return validity_date.strftime('%Y-%m-%d')
    else:
        return None  # Return None if no validity date is found