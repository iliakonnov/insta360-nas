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


def extract_ble_communication(pcap_file, pov):
    print(f"Extracting BLE data from: {pcap_file} (POV: {pov})\n")
    print("-" * 60)

    # display_filter='btatt' ensures we only process GATT Writes, Responses, and Notifications
    # This filters out the noisy background BLE advertising and empty ACL packets.
    cap = pyshark.FileCapture(pcap_file, display_filter='btatt')

    for pkt in cap:
        try:
            # In Android BTSnoop (HCI H4), direction 0x00 is Host->Controller
            # Direction 0x01 is Controller->Host
            direction_hex = pkt.hci_h4.direction
            dir_int = int(direction_hex, 16)
            
            if pov == 'client':
                is_phone_to_camera = (dir_int == 0)
            else: # pov == 'server'
                is_phone_to_camera = (dir_int == 1)

            direction = "SEND" if is_phone_to_camera else "RECV"

            # Check if the packet has a GATT value payload
            if hasattr(pkt.btatt, 'value'):
                # Wireshark normally formats the value as '1a:00:00:00...', so we remove the colons
                hex_data = pkt.btatt.value.replace(':', '')
                payload_bytes = bytes.fromhex(hex_data)

                print(f"Direction: {direction:<5} | Hex Payload: {hex_data}")
                
                try:
                    packet = None
                    if len(payload_bytes) >= 7:
                        msg_type_bytes = payload_bytes[4:7]
                        packet_type = PACKET_ID_MAP.get(msg_type_bytes, "UNKNOWN")
                        
                        if packet_type == "KEEP_ALIVE":
                            continue
                            packet = KeepAlivePacket(payload_bytes)
                        elif packet_type == "SYNC":
                            packet = SyncPacket(payload_bytes)
                        else:
                            if is_phone_to_camera:
                                packet = PhoneCommandPacket(payload_bytes)
                            else:
                                packet = ReceivedPacket(payload_bytes)
                    
                    if packet:
                        print(packet.pformat())
                    else:
                        print("Unable to determine packet type or payload too short.")
                except Exception as e:
                    print(f"Failed to decode packet: {e}")
                    
                print("-" * 60)

        except AttributeError:
            # Skip any packets that might be malformed or missing the expected layers
            pass
        except Exception:
            pass

    cap.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BLE PCAP Packet Extractor and Decoder")
    parser.add_argument("pcap_file", nargs='?', default="btsnoop_hci.log", help="Path to pcap file")
    parser.add_argument("--pov", choices=["client", "server"], default="client", help="Point of view of the capture (client or server)")
    
    args = parser.parse_args()
    
    extract_ble_communication(args.pcap_file, args.pov)