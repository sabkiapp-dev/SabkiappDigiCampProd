import requests
import pickle
from src.utils import read_api_credentials
import os
from django.conf import settings



class VirtualStorage:
    def fetch_data(self):
        try:
            with open('virtual_ram_data.pkl', 'rb') as file:
                if file.tell() == os.fstat(file.fileno()).st_size:  # Check if file is empty
                    raise FileNotFoundError  # Raise to fetch from API
                cached_data = pickle.load(file)
                if not cached_data:
                    raise FileNotFoundError  # Raise to fetch from API
                # print("virtual found in pickle")
                # print("virtual data : ", cached_data)
        except FileNotFoundError:
            # print("cached_data pickle not found or empty, fetching from API")
            cached_data = []
            # print("###Fetching from API")
            api_credentials = read_api_credentials()

            # print("api_credentials : ", api_credentials)
            api_url = f"{settings.BASE_URL}/sim_information"  # Use BASE_URL from settings
            # print("api_url : ", api_url)
            params = {
                "host": api_credentials['host'],
                "system_password": api_credentials['system_password']
            }

            try:
                response = requests.get(api_url, params=params)

                if response.status_code == 200:
                    api_data = response.json()

                    # Save data to pickle file
                    with open('virtual_ram_data.pkl', 'wb') as file:
                        pickle.dump(api_data, file)
                    cached_data = api_data
                else:
                    print(f"Failed to fetch data from the API. Status code: {response.status_code}")
                    return "Error"

            except requests.RequestException as e:
                print(f"Error occurred: {e}")
                

        return cached_data

    def get_field_by_sim_imsi(self, sim_imsi, field):
        cached_data = self.fetch_data()

        for item in cached_data:
            if item.get('sim_imsi') == sim_imsi:
                return item.get(field)

        print(f"No data found for sim_imsi: {sim_imsi} or field: {field}")
        return None

    def update_field_by_sim_imsi(self, sim_imsi, field, value):
        cached_data = self.fetch_data()
        sim_imsi_found = False  # Flag to track if sim_imsi is found

        for item in cached_data:
            if item.get('sim_imsi') == sim_imsi:
                item[field] = value
                sim_imsi_found = True  # Set flag as sim_imsi is found

                # Update data in the pickle file
                with open('virtual_ram_data.pkl', 'wb') as file:
                    pickle.dump(cached_data, file)
                return True
        
        # If sim_imsi is not found, insert it with the field and value
        if not sim_imsi_found:
            new_entry = {'sim_imsi': sim_imsi, field: value}
            cached_data.append(new_entry)

            # Update data in the pickle file
            with open('virtual_ram_data.pkl', 'wb') as file:
                pickle.dump(cached_data, file)
            return True

        print(f"No data found for sim_imsi: {sim_imsi}")
        return False
