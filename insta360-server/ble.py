import asyncio
import logging
from bless import (
    BlessServer,
    BlessGATTCharacteristic,
    GATTCharacteristicProperties,
    GATTAttributePermissions
)

logging.basicConfig(level=logging.DEBUG)

# 1. Corrected Device Name
DEVICE_NAME = "X5 1RM6G"

SERVICE_UUID = "0000be80-0000-1000-8000-00805f9b34fb"
CHAR_BE81 = "0000be81-0000-1000-8000-00805f9b34fb"  # Write (From iPad)
CHAR_BE82 = "0000be82-0000-1000-8000-00805f9b34fb"  # Notify (To iPad)
CHAR_BE83 = "0000be83-0000-1000-8000-00805f9b34fb"  # Read


async def main():
    loop = asyncio.get_running_loop()
    server = BlessServer(name=DEVICE_NAME)

    # ---------------------------------------------------------
    # The Read & Write Callbacks (Attached to the SERVER)
    # ---------------------------------------------------------
    def on_read(characteristic: BlessGATTCharacteristic, **kwargs) -> bytearray:
        # bless requires a read callback to be defined, even if we just echo the value
        return characteristic.value

    def on_write(characteristic: BlessGATTCharacteristic, value: bytearray, **kwargs):
        # Update the local characteristic state
        characteristic.value = value

        # bless normalizes UUIDs to lowercase internally
        if str(characteristic.uuid).lower() == CHAR_BE81.lower():
            hex_val = value.hex()
            print(f"\n[RECEIVED WRITE ON BE81] -> {hex_val}")

            if hex_val.startswith("1a00000004000008000201"):
                print("[MATCH] Handshake Request. Preparing response...")
                asyncio.run_coroutine_threadsafe(
                    send_handshake_responses(server),
                    loop
                )

    # Assign the callbacks to the server itself
    server.read_request_func = on_read
    server.write_request_func = on_write

    # ---------------------------------------------------------
    # The Notification Sequence (Sent out via BE82)
    # ---------------------------------------------------------
    async def send_handshake_responses(server_instance):
        await asyncio.sleep(0.1)  # Brief pause

        print("[SENDING] Fast ACK Notification on BE82...")
        ack_payload = bytes.fromhex("10000000040000172002ff8a43f40000")
        server_instance.get_characteristic(CHAR_BE82).value = ack_payload
        server_instance.update_value(SERVICE_UUID, CHAR_BE82)

        await asyncio.sleep(0.1)

        print("[SENDING] WiFi Properties Notification on BE82...")
        # Your modified WiFi payload goes here
        response_payload = bytes.fromhex(
            "92000000040000c800020100008000000830080f08240825080b"
            "12765a060800102620007a0e494148454132353031524d364759"
            "a202240a0d58352031524d3647592e4f53431208383834515335"
            "56481895012000280130014000aa02260a025255122024282c30"
            "95999da1a500000000"
        )
        server_instance.get_characteristic(CHAR_BE82).value = response_payload
        server_instance.update_value(SERVICE_UUID, CHAR_BE82)

    # ---------------------------------------------------------
    # Build the GATT Database (Matching the real camera)
    # ---------------------------------------------------------
    print("Building GATT database...")
    await server.add_new_service(SERVICE_UUID)

    # Add BE81 (Read / Write)
    await server.add_new_characteristic(
        SERVICE_UUID, CHAR_BE81,
        (GATTCharacteristicProperties.read | GATTCharacteristicProperties.write),
        None,
        (GATTAttributePermissions.readable | GATTAttributePermissions.writeable)
    )

    # Add BE82 (Notify)
    await server.add_new_characteristic(
        SERVICE_UUID, CHAR_BE82,
        GATTCharacteristicProperties.notify,
        None,
        GATTAttributePermissions.readable
    )

    # Add BE83 (Read)
    await server.add_new_characteristic(
        SERVICE_UUID, CHAR_BE83,
        GATTCharacteristicProperties.read,
        None,
        GATTAttributePermissions.readable
    )

    print(f"\nStarting BLE server. Advertising as: '{DEVICE_NAME}'")
    await server.start()
    print("Waiting for iPad... (Press Ctrl+C to quit)")

    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        await server.stop()


if __name__ == "__main__":
    asyncio.run(main())