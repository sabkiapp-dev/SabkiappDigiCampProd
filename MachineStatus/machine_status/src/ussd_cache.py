import pickle
from datetime import datetime

class UssdCache:
    def __init__(self, port_no):
        self.port_no = port_no
        self.load_data()

    def load_data(self):
        instance_data = self.load_from_file(self.port_no)
        if instance_data:
            for key, value in instance_data.items():
                setattr(self, key, value)

    @staticmethod
    def load_from_file(port_no):
        filename = 'ussd_cache.pkl'
        try:
            with open(filename, 'rb') as file:
                data = pickle.load(file)
            cache_key = f"ussd_request_{port_no}"
            if cache_key in data:
                return data[cache_key]
        except FileNotFoundError:
            # Handle the case where the file doesn't exist
            print(f"File '{filename}' not found.")
        except Exception as e:
            # Handle other exceptions
            print(f"An error occurred: {e}")
        return None

    def save(self):
        filename = 'ussd_cache.pkl'
        try:
            with open(filename, 'rb') as file:
                data = pickle.load(file)
        except FileNotFoundError:
            data = {}
        except Exception as e:
            # Handle other exceptions
            print(f"An error occurred: {e}")

        cache_key = f"ussd_request_{self.port_no}"
        current_date_time = self.get_current_date_time()
        data[cache_key] = {
            'port_no': self.port_no,
            'request_type': getattr(self, 'request_type', None),
            'status': getattr(self, 'status', None),
            'operator': getattr(self, 'operator', None),
            'trials': getattr(self, 'trials', None),
            'phone_no': getattr(self, 'phone_no', None),
            'date_time': current_date_time,  # Add current date time to data
            'sim_imsi':getattr(self, 'sim_imsi', None),
        }

        with open(filename, 'wb') as file:
            pickle.dump(data, file)

    @classmethod
    def fetch(cls, port_no):
        filename = 'ussd_cache.pkl'
        try:
            with open(filename, 'rb') as file:
                data = pickle.load(file)
            cache_key = f"ussd_request_{port_no}"
            if cache_key in data:
                instance = cls(port_no)
                for key, value in data[cache_key].items():
                    setattr(instance, key, value)
                return instance
        except FileNotFoundError:
            pass
        return None

    def clear(self):
        filename = 'ussd_cache.pkl'
        try:
            with open(filename, 'rb') as file:
                data = pickle.load(file)
                print("Clearing port no:", self.port_no)
                cache_key = f"ussd_request_{self.port_no}"
                if cache_key in data:
                    del data[cache_key]
            with open(filename, 'wb') as file:
                pickle.dump(data, file)
        except FileNotFoundError:
            # Handle the case where the file doesn't exist
            print(f"File '{filename}' not found.")
        except Exception as e:
            # Handle other exceptions
            print(f"An error occurred: {e}")

    def update_request_type(self, request_type):
        self.request_type = request_type
        self.save()

    def update_status(self, status):
        self.status = status
        self.save()

    def update_operator(self, operator):
        self.operator = operator
        self.save()

    def update_trials(self, trials):
        self.trials = trials
        self.save()

    def update_phone_no(self, phone_no):
        self.phone_no = phone_no
        self.save()

    def update_sim_imsi(self, sim_imsi):
        self.sim_imsi = sim_imsi
        self.save()

    def get_port_no(self):
        return self.port_no

    def get_request_type(self):
        return getattr(self, 'request_type', None)

    def get_status(self):
        return getattr(self, 'status', None)

    def get_operator(self):
        return getattr(self, 'operator', None)

    def get_trials(self):
        return getattr(self, 'trials', None)

    def get_phone_no(self):
        return getattr(self, 'phone_no', None)

    def get_sim_imsi(self):
        return getattr(self, 'sim_imsi', None)
    
    def get_date_time(self):
        filename = 'ussd_cache.pkl'
        try:
            with open(filename, 'rb') as file:
                data = pickle.load(file)
                cache_key = f"ussd_request_{self.port_no}"
                if cache_key in data and 'date_time' in data[cache_key]:
                    return data[cache_key]['date_time']
        except FileNotFoundError:
            pass
        except Exception as e:
            # Handle other exceptions
            print(f"An error occurred: {e}")
        return None

    def get_current_date_time(self):
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    def __str__(self):
        return f"UssdRequests: port_no={self.get_port_no()}, request_type={self.get_request_type()}, status={self.get_status()}, operator={self.get_operator()}, trials={self.get_trials()}, phone_no={self.get_phone_no()}, date_time={self.get_date_time()}"
