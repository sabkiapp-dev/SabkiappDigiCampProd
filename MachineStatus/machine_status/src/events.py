import socket
from enum import Enum
from datetime import datetime
#from handler.database_handler import DatabaseHandler
import copy
# import requests

# Asterisk AMI credentials
AMI_HOST = '192.168.1.32'
AMI_PORT = 5038
AMI_USER = 'asterisk'
AMI_PASS = 'asterisk'

#db: DatabaseHandler


class CallStatus(Enum):
    queued = 1
    dialed = 2
    answered = 3
    completed = 4
    rejected = 5
    congestion = 6


class ActiveCallModel():
    unique_id: str
    mobile_number: str
    call_status: CallStatus = CallStatus.queued

    def __init__(self, unique_id: str = None, mobile_number: str = None):
        self.unique_id = unique_id
        self.mobile_number = mobile_number

    def __str__(self) -> str:
        return f"A(unique_id: {self.unique_id}, mobile_number: {self.mobile_number}, call_status: {self.call_status})"

    def __eq__(self, __value: object) -> bool:
        if isinstance(__value, ActiveCallModel):
            return self.unique_id == __value.unique_id and self.mobile_number == __value.mobile_number and self.call_status == __value.call_status
        return False


active_calls: list[ActiveCallModel] = []


def float_parse(a: str) -> float:
    if a is None:
        return None

    try:
        return float(a)
    except ValueError as error:
        print(error)
        return None

# Function to handle AMI events


def handle_ami_event(event: str):
    global active_calls

    active_calls_copy = copy.deepcopy(active_calls)

    # Convert the Event string into dictionary
    event_data = dict(item.split(': ', 1)
                      for item in event.splitlines() if ': ' in item)

    # Get the event unique id and event
    event_unique_id = float_parse(event_data.get('DestUniqueid'))
    event = event_data.get('Event')

    if event_unique_id is None:
        event_unique_id = float_parse(event_data.get('Uniqueid'))
    if event_unique_id is None:
        event_unique_id = float_parse(event_data.get('Linkedid'))
    if event_unique_id is None:
        event_unique_id = float_parse(event_data.get('DestLinkedid'))
    print("event unique id : ",event_unique_id)
    # If dial begins add the one active call as queued
    if event == 'DialBegin':
        print(event_data)
        exist = len(
            [item for item in active_calls if item.unique_id == event_unique_id]) >= 1
        if not exist:
            active_calls.append(ActiveCallModel(
                unique_id=event_unique_id,
                mobile_number=event_data.get('DialString').split('/')[1],
            ))

    # If received Event is RTPCSent which means call has been initiated
    if event == 'RTCPSent':
        print(event_data)
        calls = [item for item in active_calls if item.unique_id ==
                 event_unique_id]

        if len(calls) >= 1 and calls[0].call_status == CallStatus.queued:
            calls[0].call_status = CallStatus.dialed

    # If received Event is Newstate which means call has been picked up
    if event == 'Newstate':
        print(event_data)
        calls = [item for item in active_calls if item.unique_id ==
                 event_unique_id]

        if len(calls) == 1 and (calls[0].call_status == CallStatus.dialed or calls[0].call_status == CallStatus.queued):
            calls[0].call_status = CallStatus.answered

    # If received Event is DialEnd which means call is in congestion
    if event == 'DialEnd':
        print(event_data)
        calls = [item for item in active_calls if item.unique_id ==
                 event_unique_id]

        if len(calls) == 1 and calls[0].call_status == CallStatus.queued:
            calls[0].call_status = CallStatus.congestion

    # If received Event is DeviceStateChange which means call is either completed or rejected
    # If call has picked then `completed` otherwise `rejected`
    if event == 'DeviceStateChange' or event == 'Hangup':
        print(event_data)
        calls = [item for item in active_calls if item.unique_id ==
                 event_unique_id]

        if len(calls) >= 1:
            if calls[0].call_status == CallStatus.answered:
                calls[0].call_status = CallStatus.completed
            elif calls[0].call_status == CallStatus.dialed:
                calls[0].call_status = CallStatus.rejected

            # If the call is completed or rejected then send a call from congestion and remove that from list

            # if calls[0].call_status == CallStatus.completed or calls[0].call_status == CallStatus.rejected:
            #     congestion_calls = [
            #         item for item in active_calls if item.call_status == CallStatus.congestion]
            #     if len(congestion_calls) > 0:
            #         url = f"http://192.168.1.11:8000/call?mobile_number={congestion_calls[0].mobile_number}"
            #         active_calls.remove(congestion_calls[0])
            #         requests.get(url)

    queued = [item for item in active_calls if item.call_status ==
              CallStatus.queued]
    dialed = [item for item in active_calls if item.call_status ==
              CallStatus.dialed]
    answered = [item for item in active_calls if item.call_status ==
                CallStatus.answered]
    completed = [
        item for item in active_calls if item.call_status == CallStatus.completed]
    rejected = [item for item in active_calls if item.call_status ==
                CallStatus.rejected]
    congestion = [
        item for item in active_calls if item.call_status == CallStatus.congestion]

    if active_calls_copy != active_calls:
        print("Change encountered")
    print(
        f"Current time ({event} - {event_unique_id}) {datetime.now()}")

    for item in active_calls:
        print(item)

    print(f"Queued calls - {len(queued)}")
    print(f"Dialed calls - {len(dialed)}")
    print(f"Answered calls - {len(answered)}")
    print(f"Completed calls - {len(completed)}")
    print(f"Rejected calls - {len(rejected)}")
    print(f"Congestion calls - {len(congestion)}", end="\n\n")


# Function to connect and listen for AMI events


def listen_for_ami_events():
    #global db
    #db = DatabaseHandler()
    try:
        # Connect to Asterisk AMI
        ami_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        ami_socket.connect((AMI_HOST, AMI_PORT))

        # Log in to AMI
        login_data = f"Action: Login\r\nUsername: {AMI_USER}\r\nSecret: {AMI_PASS}\r\n\r\n"
        ami_socket.sendall(login_data.encode())

        # Listen for events
        while True:
            ami_data = ami_socket.recv(4096).decode()
            if 'Event: ' in ami_data:
                handle_ami_event(ami_data)

    except socket.error as err:
        print(f"Socket Error: {err}")

    finally:
        # Log off from AMI when the script exits
        logoff_data = "Action: Logoff\r\n\r\n"
        ami_socket.sendall(logoff_data.encode())
        ami_socket.close()


# Call the function to listen for AMI events
# listen_for_ami_events()

if __name__ == "__main__":
    listen_for_ami_events()
