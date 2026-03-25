#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys
from django.conf import settings
from django.core.management.commands.runserver import Command as runserver

class CustomRunserver(runserver):
    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument('--port', dest='port', type=int, default=getattr(settings, 'PORT', 8000))

def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'machine_status.settings')

    # Delete ussd_cache.pkl and virtual_ram_data.pkl files on server start
    delete_files(['ussd_cache.pkl', 'virtual_ram_data.pkl'])

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc

    # Override the runserver command to set the default port from settings.py
    runserver.default_port = getattr(settings, 'PORT', 8000)
    runserver.default_addr = '0.0.0.0'

    # Modify sys.argv to use the custom runserver command
    sys.argv[0] = 'manage.py'
    sys.argv[1:] = ["runserver"]

    execute_from_command_line(sys.argv)

def delete_files(files):
    """Delete specified files."""
    for file_name in files:
        if os.path.exists(file_name):
            os.remove(file_name)
            print(f"Deleted {file_name}")

if __name__ == '__main__':
    main()
