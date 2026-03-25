import pickle

def display_pickle_data(file):
    filename = file
    print("pickle for file : ", file)
    try:
        with open(filename, 'rb') as file:
            data = pickle.load(file)
            print("Data in ",file)
            print(data)
    except FileNotFoundError:
        print(f"File '{filename}' not found.")

if __name__ == "__main__":
    # display_pickle_data('machine_status/ussd_cache.pkl')
    display_pickle_data('machine_status/virtual_ram_data.pkl')
