#!/usr/bin/env python3
"""
DigiCampServer Campaign Admin Utility

Usage:
    python campaign_admin.py <command> [options]

Commands:
    login <mobile> <password>          - Login as user and get JWT token
    list-users                        - List all users
    list-campaigns <user_id>         - List campaigns for a user
    create-campaign <user_id> <name> - Create a new campaign for user
    set-api-key <api_key> <user_id> <campaign_id> [description] - Set API key mapping
    list-api-keys                     - List all API key mappings
    delete-api-key <api_key>          - Delete an API key mapping
    help                              - Show this help message

Examples:
    # Login as user
    python campaign_admin.py login 9876543210 mypassword

    # List all users
    python campaign_admin.py list-users

    # List campaigns for user
    python campaign_admin.py list-campaigns 1

    # Create a campaign
    python campaign_admin.py create-campaign 1 "My Test Campaign"

    # Set API key mapping
    python campaign_admin.py set-api-key my_app_key_123 1 1000000001 "Test app"

    # List API key mappings
    python campaign_admin.py list-api-keys

    # Delete API key mapping
    python campaign_admin.py delete-api-key my_app_key_123
"""

import sys
import os
import django
import requests
import json
import getpass
from pathlib import Path

# Setup Django
BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'digicamp_server.settings')
django.setup()

from api.models.users import Users
from api.models.campaign import Campaign
from api.models.api_key_mapping import ApiKeyMapping
from django.db.models import Q

# Server URL - change this to your server
SERVER_URL = "http://127.0.0.1:8000"


def print_error(msg):
    print(f"ERROR: {msg}", file=sys.stderr)


def print_success(msg):
    print(f"SUCCESS: {msg}")


def print_info(msg):
    print(f"INFO: {msg}")


def login(mobile, password):
    """Login as user and return user info."""
    try:
        user = Users.objects.get(mobile=mobile)
    except Users.DoesNotExist:
        print_error(f"User with mobile {mobile} not found")
        return None

    # Simple password check (actual implementation may use different auth)
    # Assuming password is stored as plain text or hashed
    if hasattr(user, 'password') and user.password == password:
        print_success(f"Logged in as user ID: {user.id}, Mobile: {user.mobile}")
        return user
    else:
        # Try checking password differently
        from django.contrib.auth.hashers import check_password
        try:
            if check_password(password, user.password):
                print_success(f"Logged in as user ID: {user.id}, Mobile: {user.mobile}")
                return user
        except:
            pass

        print_error("Invalid password")
        return None


def list_users():
    """List all users."""
    users = Users.objects.all().order_by('-id')[:50]  # Limit to 50
    if not users:
        print_info("No users found")
        return

    print(f"\n{'ID':<10} {'Mobile':<15} {'Name':<30} {'Status':<10} {'Created At':<20}")
    print("-" * 85)
    for u in users:
        name = (u.name or "")[:28]
        created = str(u.created_at)[:19] if hasattr(u, 'created_at') and u.created_at else "N/A"
        status = "Active" if (hasattr(u, 'status') and u.status == 1) else "Inactive"
        print(f"{u.id:<10} {u.mobile:<15} {name:<30} {status:<10} {created:<20}")


def list_campaigns(user_id):
    """List campaigns for a user."""
    try:
        user = Users.objects.get(id=user_id)
    except Users.DoesNotExist:
        print_error(f"User ID {user_id} not found")
        return

    campaigns = Campaign.objects.filter(user=user).order_by('-id')
    if not campaigns:
        print_info(f"No campaigns found for user {user_id}")
        return

    print(f"\nCampaigns for User {user_id} ({user.mobile}):")
    print(f"{'ID':<15} {'Name':<30} {'Status':<10} {'Priority':<10} {'Created At':<20}")
    print("-" * 85)
    for c in campaigns:
        name = (c.name or "")[:28]
        status_map = {0: "Inactive", 1: "Active", 2: "Paused", 3: "Completed"}
        status = status_map.get(c.status, str(c.status))
        priority = c.campaign_priority if hasattr(c, 'campaign_priority') else "N/A"
        created = str(c.created_at)[:19] if hasattr(c, 'created_at') and c.created_at else "N/A"
        print(f"{c.id:<15} {name:<30} {status:<10} {priority:<10} {created:<20}")


def create_campaign(user_id, name, description="", language="en"):
    """Create a new campaign for user."""
    try:
        user = Users.objects.get(id=user_id)
    except Users.DoesNotExist:
        print_error(f"User ID {user_id} not found")
        return None

    # Get a default priority
    max_priority = Campaign.objects.filter(user=user).count() + 1

    campaign = Campaign.objects.create(
        user=user,
        name=name,
        description=description,
        language=language,
        campaign_priority=max_priority,
        status=1,  # Active
        start_date=None,
        end_date=None,
        start_time=None,
        end_time=None,
    )

    print_success(f"Created campaign ID: {campaign.id}, Name: {name}")
    return campaign


def set_api_key(api_key, user_id, campaign_id, description=""):
    """Set or update API key mapping."""
    # Validate user exists
    try:
        user = Users.objects.get(id=user_id)
    except Users.DoesNotExist:
        print_error(f"User ID {user_id} not found")
        return False

    # Validate campaign exists and belongs to user
    try:
        campaign = Campaign.objects.get(id=campaign_id, user_id=user_id)
    except Campaign.DoesNotExist:
        print_error(f"Campaign ID {campaign_id} not found for user {user_id}")
        return False

    # Create or update mapping
    mapping, created = ApiKeyMapping.objects.update_or_create(
        api_key=api_key,
        defaults={
            'user_id': user_id,
            'campaign_id': campaign_id,
            'description': description,
            'is_active': True
        }
    )

    if created:
        print_success(f"Created API key mapping: {api_key[:20]}... -> user:{user_id}, campaign:{campaign_id}")
    else:
        print_success(f"Updated API key mapping: {api_key[:20]}... -> user:{user_id}, campaign:{campaign_id}")

    return True


def list_api_keys():
    """List all API key mappings."""
    mappings = ApiKeyMapping.objects.all().order_by('-id')
    if not mappings:
        print_info("No API key mappings found")
        return

    print(f"\n{'API Key':<25} {'User ID':<10} {'Campaign ID':<15} {'Description':<30} {'Active':<10}")
    print("-" * 90)
    for m in mappings:
        desc = (m.description or "")[:28]
        active = "Yes" if m.is_active else "No"
        print(f"{m.api_key[:23]:<25} {m.user_id:<10} {m.campaign_id:<15} {desc:<30} {active:<10}")


def delete_api_key(api_key):
    """Delete an API key mapping."""
    try:
        mapping = ApiKeyMapping.objects.get(api_key=api_key)
        mapping.delete()
        print_success(f"Deleted API key mapping: {api_key}")
        return True
    except ApiKeyMapping.DoesNotExist:
        print_error(f"API key '{api_key}' not found")
        return False


def generate_random_api_key():
    """Generate a random API key."""
    import secrets
    return secrets.token_hex(24)


def help():
    print(__doc__)


def main():
    if len(sys.argv) < 2:
        help()
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == "help":
        help()

    elif command == "login":
        if len(sys.argv) < 4:
            print_error("Usage: login <mobile> <password>")
            sys.exit(1)
        login(sys.argv[2], sys.argv[3])

    elif command == "list-users":
        list_users()

    elif command == "list-campaigns":
        if len(sys.argv) < 3:
            print_error("Usage: list-campaigns <user_id>")
            sys.exit(1)
        list_campaigns(int(sys.argv[2]))

    elif command == "create-campaign":
        if len(sys.argv) < 4:
            print_error("Usage: create-campaign <user_id> <name> [description]")
            sys.exit(1)
        desc = sys.argv[4] if len(sys.argv) > 4 else ""
        create_campaign(int(sys.argv[2]), sys.argv[3], desc)

    elif command == "set-api-key":
        if len(sys.argv) < 5:
            print_error("Usage: set-api-key <api_key> <user_id> <campaign_id> [description]")
            sys.exit(1)
        desc = sys.argv[5] if len(sys.argv) > 5 else ""
        set_api_key(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), desc)

    elif command == "generate-api-key":
        key = generate_random_api_key()
        print_success(f"Generated API key: {key}")
        print_info(f"Use this key with: set-api-key {key} <user_id> <campaign_id> [description]")

    elif command == "list-api-keys":
        list_api_keys()

    elif command == "delete-api-key":
        if len(sys.argv) < 3:
            print_error("Usage: delete-api-key <api_key>")
            sys.exit(1)
        delete_api_key(sys.argv[2])

    else:
        print_error(f"Unknown command: {command}")
        help()
        sys.exit(1)


if __name__ == "__main__":
    main()
