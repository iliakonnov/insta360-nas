import pyshark
import sys


def extract_ble_communication(pcap_file):
    print(f"Extracting BLE data from: {pcap_file}\n")
    print(f"{'DIR':<5} | {'HEX PAYLOAD'}")
    print("-" * 60)

    # display_filter='btatt' ensures we only process GATT Writes, Responses, and Notifications
    # This filters out the noisy background BLE advertising and empty ACL packets.
    cap = pyshark.FileCapture(pcap_file, display_filter='btatt')

    for pkt in cap:
        try:
            # In Android BTSnoop (HCI H4), direction 0x00 is Host->Controller (Phone sending to Camera)
            # Direction 0x01 is Controller->Host (Phone receiving from Camera)
            direction_hex = pkt.hci_h4.direction
            direction = "SEND" if int(direction_hex, 16) == 0 else "RECV"

            # Check if the packet has a GATT value payload
            if hasattr(pkt.btatt, 'value'):
                # Wireshark normally formats the value as '1a:00:00:00...', so we remove the colons
                hex_data = pkt.btatt.value.replace(':', '')

                print(f"{direction:<5} | {hex_data}")

        except AttributeError as e:
            print(e)
            # Skip any packets that might be malformed or missing the expected layers
            continue

    cap.close()


if __name__ == "__main__":
    # You can pass the file name as a command line argument, or hardcode it here
    if len(sys.argv) > 1:
        log_file = sys.argv[1]
    else:
        log_file = "btsnoop_hci.log"  # Replace with your actual file name

    extract_ble_communication(log_file)