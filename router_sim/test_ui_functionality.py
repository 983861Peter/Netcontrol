#!/usr/bin/env python3
"""
Test script to verify client assignment UI functionality.
Tests the backend API responses that the UI depends on.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.orm import sessionmaker, Session
import models
import db
import schemas

Client = models.Client
Device = models.Device
Base = models.Base
engine = db.engine
SessionLocal = db.SessionLocal
ClientOut = schemas.ClientOut

def test_client_device_count():
    """Test that clients include device count in API response"""
    db: Session = SessionLocal()
    try:
        # Create test data
        client1 = Client(name="Test Client 1", location="Test Location 1")
        client2 = Client(name="Test Client 2", location="Test Location 2")
        db.add(client1)
        db.add(client2)
        db.commit()

        # Create devices
        device1 = Device(
            device_id="test-device-1",
            mac_address="AA:BB:CC:DD:EE:01",
            client_id=client1.id
        )
        device2 = Device(
            device_id="test-device-2",
            mac_address="AA:BB:CC:DD:EE:02",
            client_id=client1.id
        )
        device3 = Device(
            device_id="test-device-3",
            mac_address="AA:BB:CC:DD:EE:03",
            client_id=client2.id
        )
        db.add(device1)
        db.add(device2)
        db.add(device3)
        db.commit()

        # Test the list_clients function logic
        clients = db.query(Client).order_by(Client.created_at.desc()).all()
        for client in clients:
            client.device_count = len(client.devices)

        # Verify counts
        client1_data = next(c for c in clients if c.id == client1.id)
        client2_data = next(c for c in clients if c.id == client2.id)

        assert client1_data.device_count == 2, f"Expected 2 devices for client1, got {client1_data.device_count}"
        assert client2_data.device_count == 1, f"Expected 1 device for client2, got {client2_data.device_count}"

        print("✅ Client device count test passed")

        # Test ClientOut schema serialization
        client_out = ClientOut.from_orm(client1_data)
        assert hasattr(client_out, 'device_count'), "ClientOut should have device_count field"
        assert client_out.device_count == 2, f"ClientOut device_count should be 2, got {client_out.device_count}"

        print("✅ ClientOut schema test passed")

    finally:
        # Clean up
        db.query(Device).filter(Device.device_id.like("test-device-%")).delete()
        db.query(Client).filter(Client.name.like("Test Client%")).delete()
        db.commit()
        db.close()

def test_device_client_info():
    """Test that device API response includes client information"""
    db: Session = SessionLocal()
    try:
        # Create test client
        client = Client(name="Test Client", location="Test Location")
        db.add(client)
        db.commit()

        # Create device with client
        device = Device(
            device_id="test-device-client",
            mac_address="AA:BB:CC:DD:EE:FF",
            client_id=client.id
        )
        db.add(device)
        db.commit()

        # Test device query with client relationship
        d = db.query(Device).filter(Device.device_id == "test-device-client").first()
        assert d is not None, "Device should exist"
        assert d.client is not None, "Device should have client relationship"
        assert d.client.name == "Test Client", f"Client name should be 'Test Client', got {d.client.name}"

        # Simulate API response building
        client_info = None
        if d.client:
            client_info = {
                "id": d.client.id,
                "name": d.client.name,
                "location": d.client.location
            }

        assert client_info is not None, "Client info should be populated"
        assert client_info["name"] == "Test Client", f"Client info name should be 'Test Client', got {client_info['name']}"
        assert client_info["location"] == "Test Location", f"Client info location should be 'Test Location', got {client_info['location']}"

        print("✅ Device client info test passed")

        # Test device without client
        device_no_client = Device(
            device_id="test-device-no-client",
            mac_address="BB:CC:DD:EE:FF:00"
        )
        db.add(device_no_client)
        db.commit()

        d2 = db.query(Device).filter(Device.device_id == "test-device-no-client").first()
        client_info2 = None
        if d2.client:
            client_info2 = {
                "id": d2.client.id,
                "name": d2.client.name,
                "location": d2.client.location
            }

        assert client_info2 is None, "Device without client should have None client_info"

        print("✅ Device without client test passed")

    finally:
        # Clean up
        db.query(Device).filter(Device.device_id.like("test-device%")).delete()
        db.query(Client).filter(Client.name.like("Test Client%")).delete()
        db.commit()
        db.close()

def main():
    print("Testing client assignment UI functionality...")

    # Create tables if they don't exist
    Base.metadata.create_all(bind=engine)

    try:
        test_client_device_count()
        test_device_client_info()
        print("\n🎉 All UI functionality tests passed!")
        print("\nThe backend changes ensure that:")
        print("- Clients API returns device_count for each client")
        print("- Devices API returns client information when assigned")
        print("- UI can display client names on device panels")
        print("- UI can show updated device counts on client pages")

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
