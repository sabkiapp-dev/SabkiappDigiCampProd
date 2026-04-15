from enum import Enum

class FinalStatus(Enum):
    NO_SIM = "No SIM"
    NO_SIGNAL = "No Signal"
    RECHARGELESS = "Rechargeless"
    READY = "Ready"
    BUSY = "Busy"
    NEW_SIM = "New SIM"