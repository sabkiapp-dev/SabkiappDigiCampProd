import psutil

def convert_bytes(size_in_bytes):
    # Define the size units and their corresponding labels
    size_units = ['B', 'KB', 'MB', 'GB']

    # Initialize variables
    size = size_in_bytes
    unit_index = 0

    # Convert bytes to larger units until the size is less than 1024
    while size >= 1024 and unit_index < len(size_units) - 1:
        size /= 1024.0
        unit_index += 1

    # Format the result with two decimal places
    result = "{:.2f} {}".format(size, size_units[unit_index])

    return result

def get_disk_space_info():
    # Get information about all mounted disks with "ext4" filesystem type
    ext4_disks_info = {}

    for partition in psutil.disk_partitions():
        if partition.fstype == "ext4":
            device_key = partition.device

            if device_key in ext4_disks_info:
                # Update existing entry with additional mount point
                ext4_disks_info[device_key]['mountpoints'].append(partition.mountpoint)
            else:
                # Create a new entry for the device
                disk_info = psutil.disk_usage(partition.mountpoint)
                total = convert_bytes(disk_info.total)
                used = convert_bytes(disk_info.used)
                free = convert_bytes(disk_info.free)

                device_data = {
                    'device': device_key,
                    'fstype': partition.fstype,
                    'total': total,
                    'used': used,
                    'free': free,
                    'percent': disk_info.percent,
                    'mountpoints': [partition.mountpoint]
                }

                ext4_disks_info[device_key] = device_data

    return {'disks': list(ext4_disks_info.values())}
