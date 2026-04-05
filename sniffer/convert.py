import sys
import os
import argparse
import asyncio
import pyshark

# Add third-party directories to sys.path
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(base_dir, 'third-party', 'insta360'))
sys.path.append(os.path.join(base_dir, 'third-party', 'insta360-lib-one-proto'))

from tools.packet_analyzer import (
    PhoneCommandPacket, 
    ReceivedPacket, 
    KeepAlivePacket, 
    SyncPacket, 
    PACKET_ID_MAP
)
import logging

# Suppress noisy parsing warnings from the packet analyzer module
logging.getLogger("packet_analizer").setLevel(logging.ERROR)


def decode_payload(payload_bytes, is_phone_to_camera):
    """
    Decodes one or more protocol frames from the given payload bytes.
    """
    while len(payload_bytes) >= 7:
        try:
            # First 4 bytes are length (little-endian)
            packet_len = int.from_bytes(payload_bytes[:4], 'little')
            if packet_len > len(payload_bytes):
                # Incomplete frame, wait for more data (though pyshark usually gives full segments)
                break
            if packet_len == 0:
                print('Empty frame')
                break

            frame_bytes = payload_bytes[:packet_len]
            payload_bytes = payload_bytes[packet_len:]

            if len(frame_bytes) < 7:
                continue

            msg_type_bytes = frame_bytes[4:7]
            packet_type = PACKET_ID_MAP.get(msg_type_bytes, "UNKNOWN")

            if packet_type == "KEEP_ALIVE":
                continue

            print(f"Hex Payload: {frame_bytes.hex()}")

            packet = None
            if packet_type == "SYNC":
                packet = SyncPacket(frame_bytes)
            else:
                if is_phone_to_camera:
                    packet = PhoneCommandPacket(frame_bytes)
                else:
                    packet = ReceivedPacket(frame_bytes)

            if packet:
                print(packet.pformat())
            else:
                print("Unable to determine packet type.")

            print("-" * 60)

        except Exception as e:
            print(f"Failed to decode frame: {e}")
            break


def extract_communication(pcap_file, pov, protocol='ble'):
    print(f"Extracting {protocol.upper()} data from: {pcap_file} (POV: {pov})\n")
    print("-" * 60)

    if protocol == 'ble':
        # btatt ensures we only process GATT Writes, Responses, and Notifications
        display_filter = 'btatt'
    else:
        # TCP port 6666 is used for camera communication
        display_filter = 'tcp.port == 6666'

    cap = pyshark.FileCapture(pcap_file, display_filter=display_filter)

    for pkt in cap:
        try:
            payload_bytes = None
            is_phone_to_camera = False

            if protocol == 'ble':
                # In Android BTSnoop (HCI H4), direction 0x00 is Host->Controller
                # Direction 0x01 is Controller->Host
                direction_hex = pkt.hci_h4.direction
                dir_int = int(direction_hex, 16)

                if pov == 'client':
                    is_phone_to_camera = (dir_int == 0)
                else: # pov == 'server'
                    is_phone_to_camera = (dir_int == 1)

                if hasattr(pkt.btatt, 'value'):
                    hex_data = pkt.btatt.value.replace(':', '')
                    payload_bytes = bytes.fromhex(hex_data)
            else:
                # TCP direction logic
                if not hasattr(pkt.tcp, 'payload'):
                    continue

                # Port 6666 is the camera's control port
                # Packets TO port 6666 are Phone -> Camera
                # Packets FROM port 6666 are Camera -> Phone
                dst_port = int(pkt.tcp.dstport)
                is_phone_to_camera = (dst_port == 6666)

                hex_data = pkt.tcp.payload.replace(':', '')
                payload_bytes = bytes.fromhex(hex_data)

            if payload_bytes:
                direction = "SEND" if is_phone_to_camera else "RECV"
                # Note: For TCP, we just print the direction once per TCP segment,
                # even if it contains multiple protocol frames.
                print(f"Direction: {direction:<5} | Segment Length: {len(payload_bytes)}")
                decode_payload(payload_bytes, is_phone_to_camera)

        except AttributeError:
            pass
        except Exception as e:
            # print(f"Error processing packet: {e}")
            pass

    cap.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Insta360 PCAP Packet Extractor and Decoder")
    parser.add_argument("pcap_file", nargs='?', default="btsnoop_hci.log", help="Path to pcap file")
    parser.add_argument("--pov", choices=["client", "server"], default="client", help="Point of view of the capture (client or server)")
    parser.add_argument("--protocol", choices=["ble", "tcp"], default="ble", help="Protocol to extract (ble or tcp)")

    args = parser.parse_args()

    # Auto-detect protocol based on file extension if possible, or just use the arg
    protocol = args.protocol
    if args.pcap_file.endswith('.pcapng') and protocol == 'ble' and not any(arg == '--protocol' for arg in sys.argv):
        # Heuristic: pcapng often contains Ethernet/TCP in this project context
        # But we'll respect the default or explicit arg.
        pass

    extract_communication(args.pcap_file, args.pov, protocol)
