#!/bin/bash
#
# dtmf.sh — sends call/SMS events to the VoiceAPI server.
#
# Changes in iter05:
#   • All curl calls now use --fail --max-time so failures return non-zero.
#   • HTTP response body is captured and written to dtmf.log (if log enabled).
#   • Unused `send_sms` path simplified.
#   • Timestamps on every log entry.
#

# ── Config ──────────────────────────────────────────────────────────────────
SETTINGS_FILE="/home/pi/Documents/MachineStatus/machine_status/machine_status/settings.py"
LOG_FILE="/home/pi/Documents/MachineStatus/dtmf.log"
LOG_ENABLED=1          # Set to 0 to disable file logging

# ── Config reader ───────────────────────────────────────────────────────────
BASE_URL=$(grep -oP 'BASE_URL\s*=\s*["\x27](.*?)["\x27]' "$SETTINGS_FILE" | awk -F= '{print $2}' | tr -d "\" '")
SYSTEM_PASSWORD=$(grep -oP "'SYSTEM_PASSWORD'\s*:\s*['\"](.*?)['\"]" "$SETTINGS_FILE" | awk -F: '{print $2}' | tr -d "' '")
HOST=$(grep -oP "'HOST'\s*:\s*['\"](.*?)['\"]" "$SETTINGS_FILE" | awk -F: '{print $2}' | tr -d "' '")
MACHINE_URL=$(grep -oP 'MACHINE_URL\s*=\s*["\x27](.*?)["\x27]' "$SETTINGS_FILE" | awk -F= '{print $2}' | tr -d "\" '")

if [[ -z "$HOST" || -z "$SYSTEM_PASSWORD" || -z "$BASE_URL" || -z "$MACHINE_URL" ]]; then
    echo "[$(date '+%Y-%m-%dT%H:%M:%S')] ERROR: missing config from settings.py" >&2
    exit 1
fi

# ── Logging helper ──────────────────────────────────────────────────────────
log() {
    local msg="[$(date '+%Y-%m-%dT%H:%M:%S')] $*"
    echo "$msg"
    if [[ "$LOG_ENABLED" == "1" ]]; then
        echo "$msg" >> "$LOG_FILE"
    fi
}

# ── Helpers ─────────────────────────────────────────────────────────────────

get_sim_imsi() {
    local port="$1"
    local response
    response=$(curl -s --max-time 5 "http://localhost:9000/gsm-info" 2>/dev/null)
    if [[ -z "$response" ]]; then
        echo ""
        return
    fi
    echo "$response" | jq -r --arg port "$port" '.[$port][] | select(.port == ($port | tonumber)) | .sim_imsi // empty' 2>/dev/null
}

get_mytime() {
    local utc_now
    local utc_epoch
    utc_now=$(date -u +"%Y-%m-%d %H:%M:%S")
    utc_epoch=$(date -ud "$utc_now" +"%s")
    echo $((utc_epoch + 19800))   # UTC+5:30
}

# ── HTTP sender (sets RESPONSE and HTTP_CODE globals) ───────────────────────
do_post() {
    local url="$1"
    local data="$2"

    local raw_resp
    raw_resp=$(curl -s --fail --max-time 10 \
        --header 'Content-Type: application/json' \
        --data "$data" \
        "$url" 2>&1)
    RESPONSE="$raw_resp"
    HTTP_CODE=$?
}

# ── Parse arguments ──────────────────────────────────────────────────────────
event=$1
phone_number=$2
phone_number="${phone_number//[^0-9]/}"   # strip non-digits
port=$3
port=$((port - 1000))
user_id=$4
campaign=$5
field6=$6    # extension (dtmf) or template_id (sms)
field7=$7

# Add a separator line at the start of every event trace
log "====================================================================="
log "dtmf.sh invoked: event=$event phone=$phone_number port=$port campaign=$campaign"

# ── Pre-fetch IMSI (only needed for not_answered / completed) ─────────────────
sim_imsi=""
if [[ "$event" == "completed" || "$event" == "not_answered" ]]; then
    sim_imsi=$(get_sim_imsi "$port")
    log "sim_imsi for port $port: ${sim_imsi:-none}"
fi

# ── Set field7 to IST epoch (for start_dialing / not_answered) ──────────────
if [[ "$event" == "start_dialing" || "$event" == "not_answered" ]]; then
    field7=$(get_mytime)
    
    # Because get_mytime adds 19800 seconds (IST offset) to UTC, 
    # we treat the epoch as UTC to get an accurate human-readable IST string.
    hr_time=$(date -ud "@$field7" +"%Y-%m-%d %H:%M:%S")
    log "Timestamp sent: $field7 (Human readable: $hr_time IST)"
fi

# ── send_sms path ────────────────────────────────────────────────────────────
if [[ "$event" == "send_sms" ]]; then
    url="$BASE_URL/send_sms"
    data=$(cat <<EOF
{
    "user_id": "$user_id",
    "host": "$HOST",
    "system_password": "$SYSTEM_PASSWORD",
    "template_id": "$field6",
    "phone_number": "$phone_number"
}
EOF
)
    log "send_sms request data: $data"
    do_post "$url" "$data"
    if [[ $HTTP_CODE -eq 0 ]]; then
        log "send_sms -> 200 | $RESPONSE"
    else
        log "send_sms -> FAIL (curl exit $HTTP_CODE) | $RESPONSE"
    fi
    exit 0
fi

# ── Call-status events: start_dialing / not_answered / answered / dtmf / completed
if [[ "$event" == @(start_dialing|not_answered|answered|dtmf|completed) ]]; then
    # Refresh IMSI in case it changed
    sim_imsi=$(get_sim_imsi "$port")

    url="$BASE_URL/send_call_status"
    data=$(cat <<EOF
{
    "phone": "$phone_number",
    "campaign": "$campaign",
    "port": "$port",
    "host": "$HOST",
    "event": "$event",
    "extension": "$field6",
    "dtmf_response": "$field7",
    "system_password": "$SYSTEM_PASSWORD",
    "sim_imsi": "${sim_imsi}",
    "AMI": "Not AMI"
}
EOF
)
    log "call_status request data: $data"
    do_post "$url" "$data"
    if [[ $HTTP_CODE -eq 0 ]]; then
        log "POST $event -> 200 | $RESPONSE"
    else
        log "POST $event -> FAIL (curl exit $HTTP_CODE) | phone=$phone_number campaign=$campaign port=$port sim_imsi=${sim_imsi} | $RESPONSE"
    fi
    exit 0
fi

log "Unknown event: $event"
exit 1