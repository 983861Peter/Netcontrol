#!/usr/bin/env python3
"""
Test script to verify client assignment functionality
"""
import requests
import json
import time

API_BASE = "http://127.0.0.1:8080"

def test_client_assignment():
    print("Testing client assignment functionality...")

    # First, create a test client
    client_data = {
        "name": "Test Client",
        "location": "Test Location",
        "contact_info": "test@example.com"
    }

    try:
        response = requests.post(f"{API_BASE}/clients", json=client_data)
        if response.status_code == 201:
            client = response.json()
            client_id = client["id"]
            print(f"✓ Created test client: {client['name']} (ID: {client_id})")
        else:
            print(f"✗ Failed to create client: {response.status_code} - {response.text}")
            return
    except Exception as e:
        print(f"✗ Error creating client: {e}")
        return

    # Create a test device
    device_data = {
        "device_id": "test-device-001",
        "mac_address": "AA:BB:CC:DD:EE:01",
        "model": "Test Router",
        "status": "offline"
    }

    try:
        response = requests.post(f"{API_BASE}/devices", json=device_data)
        if response.status_code == 201:
            device = response.json()
            device_id = device["device"]["device_id"]
            print(f"✓ Created test device: {device_id}")
        else:
            print(f"✗ Failed to create device: {response.status_code} - {response.text}")
            return
    except Exception as e:
        print(f"✗ Error creating device: {e}")
        return

    # Test attaching device to client
    try:
        response = requests.post(f"{API_BASE}/devices/{device_id}/attach-client?client_id={client_id}")
        if response.status_code == 200:
            print(f"✓ Successfully attached device {device_id} to client {client_id}")
        else:
            print(f"✗ Failed to attach device: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"✗ Error attaching device: {e}")

    # Verify device details show client
    try:
        response = requests.get(f"{API_BASE}/devices/{device_id}")
        if response.status_code == 200:
            device_details = response.json()
            if device_details.get("client"):
                client_info = device_details["client"]
                print(f"✓ Device details show client: {client_info['name']} ({client_info['location']})")
            else:
                print("✗ Device details do not show client assignment")
        else:
            print(f"✗ Failed to get device details: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"✗ Error getting device details: {e}")

    # Test detaching device from client
    try:
        response = requests.post(f"{API_BASE}/devices/{device_id}/detach-client")
        if response.status_code == 200:
            print(f"✓ Successfully detached device {device_id} from client")
        else:
            print(f"✗ Failed to detach device: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"✗ Error detaching device: {e}")

    # Verify device is detached
    try:
        response = requests.get(f"{API_BASE}/devices/{device_id}")
        if response.status_code == 200:
            device_details = response.json()
            if not device_details.get("client"):
                print("✓ Device is properly detached from client")
            else:
                print("✗ Device still shows client assignment after detach")
        else:
            print(f"✗ Failed to get device details after detach: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"✗ Error getting device details after detach: {e}")

    print("\nTest completed!")

if __name__ == "__main__":
    test_client_assignment()
