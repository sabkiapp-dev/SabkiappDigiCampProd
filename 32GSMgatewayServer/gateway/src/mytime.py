from datetime import datetime, timedelta

def get_mytime():
    # Get the current UTC time
    utc_now = datetime.utcnow()
    
    # Add an offset of UTC + 5.30 (5 hours and 30 minutes)
    mytime = utc_now + timedelta(hours=5, minutes=30)

    return mytime


def get_mytime_strftime():
    # Get current UTC time
    current_time = datetime.utcnow() + timedelta(hours=5, minutes=30)
    return current_time.strftime('%Y-%m-%d %H:%M:%S')
