# VoiceAPI - TODO / Task List

## DONE: External Contact Add API

**Status:** ✅ IMPLEMENTED
**Date Completed:** 2026-03-24

### Files Created/Modified:
- ✅ `api/views/contact_registration.py` - NEW (contains `add_contact` function)
- ✅ `api/urls.py` - MODIFIED (added `add_contact` route)

### Configuration Required:
Edit `API_KEY_TO_CAMPAIGN` in `contact_registration.py` on VPS:
```python
API_KEY_TO_CAMPAIGN = {
    "user1_api_key_abc123": {"user_id": 1001, "campaign_id": 1000000100},
    "user2_api_key_xyz789": {"user_id": 1002, "campaign_id": 1000000101},
}
```

### API Endpoint:
```
POST /api/add_contact/
```

---

## Timing Bypasses - Re-enable Time Restrictions

**Priority: High**
**Date Added: 2026-03-24**

The following timing checks were disabled for testing and need to be re-enabled before production:

---

### Task 1: Re-enable Time Check in `call_status.py`
**File:** `voiceapi/api/views/call_status.py` (line ~433)
**Status:** Uncommitted change (already re-enabled, just needs push)

**Change:** Re-enable dialer time restriction (10pm - 7am blocked)
```python
# Should be active:
if get_mytime().hour < 7 or get_mytime().hour > 22:
    if get_mytime().hour == 5 and get_mytime().minute == 30:
        Thread(target=reboot_active_host).start()
    return JsonResponse({'status': "message", 'message': 'Dialer is not allowed to run between 10pm and 7am'}, status=400)
```

---

### Task 2: Re-enable Time/Date Check in `phone_dialer.py` (PhoneDialer query)
**File:** `voiceapi/src/phone_dialer.py` (line ~188)
**Status:** Committed, needs re-enabling

**Bypassed Lines:**
```python
# NOTE: Timing check BYPASSED - uncomment below to re-enable
# Q(campaign__start_time__lte=my_time, campaign__end_time__gte=my_time) &
# Q(campaign__start_date__lte=my_time.date(), campaign__end_date__gte=my_time.date()) &
```

**Action:** Uncomment these lines to re-enable start/end time and date validation.

---

### Task 3: Re-enable Time/Date Check in `phone_dialer.py` (get_all_active_hosts)
**File:** `voiceapi/src/phone_dialer.py` (line ~410)
**Status:** Committed, needs re-enabling
**Note:** Bypassed on 2026-03-21

**Bypassed Lines:**
```python
# NOTE: Timing check BYPASSED for testing - campaigns will run at any time
# Commented out by user request on 2026-03-21
active_campaigns = Campaign.objects.filter(
    status=1,
    # start_time__lte=my_time,
    # end_time__gte=my_time,
    # start_date__lte=my_time.date(),
    # end_date__gte=my_time.date()
)
```

**Action:** Uncomment these lines to re-enable start/end time and date validation for active campaigns.

---

## Notes

- Tasks #2 and #3 are both in the same file (`phone_dialer.py`) but handle different functions:
  - Task #2: Filters which PhoneDialer records to process
  - Task #3: Filters which campaigns are considered "active"
- The `.pyc` (compiled Python) and `.pkl` (pickle) files are runtime cache and can be ignored in git
