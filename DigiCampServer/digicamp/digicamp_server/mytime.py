
from datetime import timedelta, datetime

def get_mytime():
        # Get the current UTC time
        utc_now = datetime.utcnow()

        # Add an offset of UTC + 5.30 (5 hours and 30 minutes)
        mytime = utc_now + timedelta(hours=5, minutes=30)
        # print("mytime : ", mytime)

        return mytime