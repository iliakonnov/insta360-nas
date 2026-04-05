import argparse
import asyncio
import os
import struct
import logging
from aiohttp import web

from bless import (
    BlessServer,
    BlessGATTCharacteristic,
    GATTCharacteristicProperties,
    GATTAttributePermissions
)

# BLE Constants
SERVICE_UUID = "0000be80-0000-1000-8000-00805f9b34fb"
CHAR_BE81 = "0000be81-0000-1000-8000-00805f9b34fb"  # Write (From iPad)
CHAR_BE82 = "0000be82-0000-1000-8000-00805f9b34fb"  # Notify (To iPad)
CHAR_BE83 = "0000be83-0000-1000-8000-00805f9b34fb"  # Read
DEVICE_NAME = "X5 1RM6GY"

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('insta360-server')

from lib_one_proto import (
    get_options_pb2,
    set_options_pb2,
    get_file_list_pb2,
    set_photography_options_pb2,
    get_photography_options_pb2,
    start_capture_pb2,
    stop_capture_pb2,
    take_picture_pb2,
    start_live_stream_pb2,
    stop_live_stream_pb2,
    get_current_capture_status_pb2,
    check_authorization_pb2,
    wifi_mode_pb2,
)

PKT_SYNC = b"\x06\x00\x00syNceNdinS"
PKT_KEEPALIVE = b"\x05\x00\x00"

# Phone commands from insta360/rtmp/rtmp.py
PHONE_COMMAND_START_LIVE_STREAM = 1
PHONE_COMMAND_STOP_LIVE_STREAM = 2
PHONE_COMMAND_TAKE_PICTURE = 3
PHONE_COMMAND_START_CAPTURE = 4
PHONE_COMMAND_STOP_CAPTURE = 5
PHONE_COMMAND_SET_OPTIONS = 7
PHONE_COMMAND_GET_OPTIONS = 8
PHONE_COMMAND_SET_PHOTOGRAPHY_OPTIONS = 9
PHONE_COMMAND_GET_PHOTOGRAPHY_OPTIONS = 10
PHONE_COMMAND_GET_FILE_LIST = 13
PHONE_COMMAND_GET_CURRENT_CAPTURE_STATUS = 15
PHONE_COMMAND_CHECK_AUTHORIZATION = 39
PHONE_COMMAND_RESET_WIFI = 125
PHONE_COMMAND_PREPARE_GET_FILE_SYNC_PACKAGE = 151

@web.middleware
async def logging_middleware(request, handler):
    logger.info(f"HTTP Request: {request.method} {request.path} from {request.remote}")
    try:
        response = await handler(request)
        logger.info(f"HTTP Response: {response.status} for {request.method} {request.path}")
        return response
    except web.HTTPException as e:
        logger.warning(f"HTTP Exception: {e.status} for {request.method} {request.path}")
        raise
    except Exception as e:
        logger.error(f"HTTP Error handling {request.method} {request.path}: {e}")
        raise

# Response codes
RESPONSE_CODE_OK = 200

# Classes dictionary
pb_resp_classes = {
    PHONE_COMMAND_GET_OPTIONS: get_options_pb2.GetOptionsResp,
    PHONE_COMMAND_SET_OPTIONS: set_options_pb2.SetOptionsResp,
    PHONE_COMMAND_GET_FILE_LIST: get_file_list_pb2.GetFileListResp,
    PHONE_COMMAND_SET_PHOTOGRAPHY_OPTIONS: set_photography_options_pb2.SetPhotographyOptionsResp,
    PHONE_COMMAND_GET_PHOTOGRAPHY_OPTIONS: get_photography_options_pb2.GetPhotographyOptionsResp,
    PHONE_COMMAND_START_CAPTURE: start_capture_pb2.StartCaptureResp,
    PHONE_COMMAND_STOP_CAPTURE: stop_capture_pb2.StopCaptureResp,
    PHONE_COMMAND_TAKE_PICTURE: take_picture_pb2.TakePictureResponse,
    PHONE_COMMAND_START_LIVE_STREAM: start_live_stream_pb2.StartLiveStreamResp,
    PHONE_COMMAND_STOP_LIVE_STREAM: stop_live_stream_pb2.StopLiveStreamResp,
    PHONE_COMMAND_GET_CURRENT_CAPTURE_STATUS: get_current_capture_status_pb2.GetCurrentCaptureStatusResp,
    PHONE_COMMAND_CHECK_AUTHORIZATION: check_authorization_pb2.CheckAuthorizationResp,
}

class BLEHandler:
    def __init__(self, rtmp_handler):
        self.rtmp_handler = rtmp_handler
        self.server = None
        self.heartbeat_task = None
        self.ready_ack = bytes.fromhex("10000000040000172002ff8a43f40000")
        self.heartbeat_payload = bytes.fromhex("07000000050000")

    async def _heartbeat_loop(self):
        """Sends the periodic heartbeat and initial ready signal."""
        # Initial Ready Signal
        await asyncio.sleep(1.0)
        await self.notify(self.ready_ack, "Ready Signal")
        
        while True:
            try:
                await self.notify(self.heartbeat_payload, "Heartbeat")
            except Exception as e:
                logger.debug(f"[BLE] Heartbeat send failed: {e}")
            await asyncio.sleep(1.0)

    async def notify(self, data, label="Data"):
        if self.server:
            if label != "Heartbeat":
                logger.info(f"[BLE] Sending {label} via notification: {data.hex()}")
            self.server.get_characteristic(CHAR_BE82).value = data
            self.server.update_value(SERVICE_UUID, CHAR_BE82)

    async def start(self):
        self.server = BlessServer(name=DEVICE_NAME)
        self.server.read_request_func = self.on_read
        self.server.write_request_func = self.on_write

        logger.info("Building GATT database for BLE...")
        await self.server.add_new_service(SERVICE_UUID)

        # Add BE81 (Read / Write)
        await self.server.add_new_characteristic(
            SERVICE_UUID, CHAR_BE81,
            (GATTCharacteristicProperties.read | GATTCharacteristicProperties.write),
            None,
            (GATTAttributePermissions.readable | GATTAttributePermissions.writeable)
        )

        # Add BE82 (Notify + Read)
        await self.server.add_new_characteristic(
            SERVICE_UUID, CHAR_BE82,
            (GATTCharacteristicProperties.notify | GATTCharacteristicProperties.read),
            bytearray(self.heartbeat_payload),
            GATTAttributePermissions.readable
        )

        # Add BE83 (Read)
        await self.server.add_new_characteristic(
            SERVICE_UUID, CHAR_BE83,
            GATTCharacteristicProperties.read,
            None,
            GATTAttributePermissions.readable
        )

        await self.server.start()
        logger.info(f"BLE server started. Advertising as: '{DEVICE_NAME}'")
        
        # Start heartbeat loop
        self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def stop(self):
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
        if self.server:
            await self.server.stop()
            logger.info("BLE server stopped")

    def on_read(self, characteristic: BlessGATTCharacteristic, **kwargs) -> bytearray:
        logger.info(f"[BLE] Read request on {characteristic.uuid}")
        return characteristic.value

    def on_write(self, characteristic: BlessGATTCharacteristic, value: bytearray, **kwargs):
        logger.info(f"[BLE] Write request on {characteristic.uuid}: {value.hex()}")
        characteristic.value = value
        if str(characteristic.uuid).lower() == CHAR_BE81.lower():
            if len(value) < 4:
                return
            
            # 1. Send ACK first (matching real camera behavior)
            loop = asyncio.get_running_loop()
            asyncio.run_coroutine_threadsafe(self.notify(self.ready_ack, "ACK"), loop)

            # 2. Process and send actual response
            pkt_data = value[4:]
            response = self.rtmp_handler.handle_packet(pkt_data)
            if response:
                # Small delay to ensure ACK is processed first by the app
                async def send_with_delay():
                    await asyncio.sleep(0.05)
                    await self.notify(response, "Response")
                asyncio.run_coroutine_threadsafe(send_with_delay(), loop)

class RTMPHandler:
    def __init__(self, media_dir):
        self.media_dir = media_dir

    def _pack_response(self, code, seq, pb_msg):
        pb_bytes = pb_msg.SerializeToString()
        header = b"\x04\x00\x00"
        header += struct.pack("<H", RESPONSE_CODE_OK)
        header += b"\x02"
        header += struct.pack("<i", seq)[0:3]
        header += b"\x80\x00\x00"
        payload = header + pb_bytes

        # Add length prefix
        pkt_data = bytearray(struct.pack("<i", len(payload) + 4))
        pkt_data.extend(payload)
        return bytes(pkt_data)

    def handle_packet(self, pkt_data):
        try:
            if len(pkt_data) < 12:
                return None

            header = pkt_data[:12]
            body = pkt_data[12:]

            msg_code = struct.unpack("<H", pkt_data[3:5])[0]
            seq = struct.unpack("<I", pkt_data[6:9] + b"\x00")[0]

            logger.info(f"RTMP Request Received - msg_code: {msg_code}, seq: {seq}, payload_size: {len(body)}")

            if msg_code not in pb_resp_classes:
                logger.warning(f"RTMP Request Unknown message code: {msg_code}. Sending empty OK response.")
                header = b"\x04\x00\x00"
                header += struct.pack("<H", RESPONSE_CODE_OK)
                header += b"\x02"
                header += struct.pack("<i", seq)[0:3]
                header += b"\x80\x00\x00"
                pkt_data = bytearray(struct.pack("<i", len(header) + 4))
                pkt_data.extend(header)
                return bytes(pkt_data)

            if msg_code == PHONE_COMMAND_GET_OPTIONS:
                req_msg = get_options_pb2.GetOptions()
                req_msg.ParseFromString(body)
                logger.info(f"GetOptions request: {req_msg}")

                resp_msg = get_options_pb2.GetOptionsResp()
                
                # Copy requested options to response
                for opt in req_msg.option_types:
                    try:
                        resp_msg.option_types.append(opt)
                    except Exception:
                        # Skip if it's an unknown enum value that protobuf refuses to append
                        pass

                req_opts = set(req_msg.option_types)
                
                # Device Identification
                if get_options_pb2.CAMERA_TYPE in req_opts:
                    resp_msg.value.camera_type = "Insta360 X5"
                if get_options_pb2.FIRMWAREREVISION in req_opts:
                    resp_msg.value.firmwareRevision = "v1.13.3"
                if get_options_pb2.SERIAL_NUMBER in req_opts:
                    resp_msg.value.serial_number = "IAHEA2501RM6GY"
                if get_options_pb2.OTA_PKG_VERSION in req_opts:
                    resp_msg.value.ota_pkg_version = "v1.13.3"
                if get_options_pb2.ACTIVATE_TIME in req_opts:
                    resp_msg.value.activate_time = 1712234567 # Non-zero activation time
                
                # Network & Connectivity
                if get_options_pb2.WIFI_INFO in req_opts:
                    resp_msg.value.wifi_info.ssid = "X5 1RM6GY.OSC"
                    resp_msg.value.wifi_info.password = "884QS5VH"
                    resp_msg.value.wifi_info.channel = 6
                    resp_msg.value.wifi_info.mode = resp_msg.value.wifi_info.Mode.AP
                    resp_msg.value.wifi_info.wifi_state = resp_msg.value.wifi_info.WifiState.ON
                
                if get_options_pb2.WIFI_CHANNEL_LIST in req_opts:
                    resp_msg.value.wifi_channel_list.country_code = "RU"
                    # Example 5GHz + 2.4GHz channel list
                    resp_msg.value.wifi_channel_list.channel_list = bytes.fromhex("24282c3095999da1a50000000000000000000000000000000000000000000000")

                # Status
                if get_options_pb2.BATTERY_STATUS in req_opts:
                    resp_msg.value.battery_status.battery_level = 95
                    resp_msg.value.battery_status.battery_scale = 100
                    resp_msg.value.battery_status.power_type = resp_msg.value.battery_status.PowerType.BATTERY
                
                if get_options_pb2.MEDIA_OFFSET in req_opts:
                    # Real media offset from X5 trace
                    resp_msg.value.media_offset = "n2_2653.309_2703.750_2677.660_-0.428_0.477_90.071_2652.531_8100.790_2678.900_0.447_0.332_90.187_10752_5376_1137"

                if get_options_pb2.QUICK_READER_MOVING_FLAG in req_opts:
                    resp_msg.value.quick_reader_moving_flag = False

            elif msg_code == PHONE_COMMAND_GET_FILE_LIST:
                resp_msg = get_file_list_pb2.GetFileListResp()
                for top_level in os.listdir(self.media_dir):
                    top_level_path = os.path.join(self.media_dir, top_level)
                    if os.path.isdir(top_level_path):
                        camera01_path = os.path.join(top_level_path, "Camera01")
                        if os.path.isdir(camera01_path):
                            for root, dirs, files in os.walk(camera01_path):
                                for file in files:
                                    if file.startswith('.'):
                                        continue
                                    full_path = os.path.join(root, file)
                                    rel_path = os.path.relpath(full_path, camera01_path)
                                    uri = f"/DCIM/Camera01/{rel_path}"
                                    resp_msg.uri.append(uri)
                resp_msg.total_count = len(resp_msg.uri)
            elif msg_code == PHONE_COMMAND_CHECK_AUTHORIZATION:
                logger.info(f"RTMP Response Sent - msg_code: {msg_code}, seq: {seq}, response: manually packed 08 00")
                pb_bytes = b"\x08\x00"
                header = b"\x04\x00\x00"
                header += struct.pack("<H", RESPONSE_CODE_OK)
                header += b"\x02"
                header += struct.pack("<i", seq)[0:3]
                header += b"\x80\x00\x00"
                payload = header + pb_bytes
                pkt_data = bytearray(struct.pack("<i", len(payload) + 4))
                pkt_data.extend(payload)
                return bytes(pkt_data)
            else:
                RespClass = pb_resp_classes[msg_code]
                resp_msg = RespClass()

            logger.info(f"RTMP Response Sent - msg_code: {msg_code}, seq: {seq}, response: {resp_msg}")
            return self._pack_response(msg_code, seq, resp_msg)
        except Exception as e:
            logger.error(f"Fatal exception in handle_packet: {e}", exc_info=True)
            return None

async def handle_client(reader, writer, rtmp_handler):
    peername = writer.get_extra_info('peername')
    logger.info(f"Accepted connection from {peername}")

    # Send SYNC packet with length prefix
    sync_packet = bytearray(struct.pack("<i", len(PKT_SYNC) + 4))
    sync_packet.extend(PKT_SYNC)
    writer.write(sync_packet)
    await writer.drain()

    while True:
        try:
            len_bytes = await reader.readexactly(4)
            pkt_len = int.from_bytes(len_bytes, byteorder="little")

            # pkt_len includes the 4 bytes of length itself in the client logic
            payload_len = pkt_len - 4
            if payload_len <= 0:
                continue

            pkt_data = await reader.readexactly(payload_len)

            if pkt_data == PKT_SYNC:
                continue
            elif pkt_data == PKT_KEEPALIVE:
                # Echo keepalive? Wait, server doesn't have to echo keepalive, but can if needed.
                continue

            response_pkt = rtmp_handler.handle_packet(pkt_data)
            if response_pkt:
                writer.write(response_pkt)
                await writer.drain()

        except asyncio.IncompleteReadError:
            logger.info(f"Client {peername} disconnected.")
            break
        except Exception as e:
            logger.error(f"Error handling client {peername}: {e}")
            break

    writer.close()
    await writer.wait_closed()

async def main():
    parser = argparse.ArgumentParser(description="Insta360 RTMP/HTTP/BLE Server")
    parser.add_argument("--bind", default="0.0.0.0", help="IP address to bind to")
    parser.add_argument("--dir", required=True, help="Directory to serve files from")
    parser.add_argument("--ble", action="store_true", default=True, help="Start BLE server")
    parser.add_argument("--no-ble", action="store_false", dest="ble")
    parser.add_argument("--http", action="store_true", default=True, help="Start HTTP server")
    parser.add_argument("--no-http", action="store_false", dest="http")
    parser.add_argument("--rtsp", action="store_true", default=True, help="Start RTSP server on port 6666")
    parser.add_argument("--no-rtsp", action="store_false", dest="rtsp")
    args = parser.parse_args()

    rtmp_handler = RTMPHandler(args.dir)
    tasks = []

    if args.ble:
        ble_handler = BLEHandler(rtmp_handler)
        await ble_handler.start()

    if args.rtsp:
        rtmp_server = await asyncio.start_server(
            lambda r, w: handle_client(r, w, rtmp_handler),
            args.bind, 6666
        )
        logger.info(f"RTSP Server started on {args.bind}:6666")
    else:
        rtmp_server = None

    async def handle_http_request(request):
        req_path = request.path
        rel_path = req_path.lstrip('/')
        if rel_path.startswith('DCIM/'):
            rel_path = rel_path[5:]
        else:
            raise web.HTTPBadRequest()

        # Handle requests to /DCIM or /DCIM/
        if rel_path == 'DCIM' or rel_path == '':
            if not req_path.endswith('/'):
                raise web.HTTPFound(req_path + '/')
            html = "<html><body><table><tbody>"
            html += '<tr><td><a href="Camera01/">Camera01</a></td><td></td><td>directory</td></tr>'
            html += "</tbody></table></body></html>"
            return web.Response(text=html, content_type='text/html')

        # Handle requests to /DCIM/Camera01...
        if rel_path == 'Camera01' or rel_path.startswith('Camera01/'):
            sub_path = rel_path[8:].lstrip('/')

            if not sub_path:
                # Root of Camera01 listing: merge all Camera01 contents
                if not req_path.endswith('/'):
                    raise web.HTTPFound(req_path + '/')

                merged_items = {}
                for top_level in os.listdir(args.dir):
                    top_level_path = os.path.join(args.dir, top_level)
                    if os.path.isdir(top_level_path):
                        camera01_path = os.path.join(top_level_path, "Camera01")
                        if os.path.isdir(camera01_path):
                            for item in os.listdir(camera01_path):
                                if item.startswith('.'):
                                    continue
                                item_path = os.path.join(camera01_path, item)
                                merged_items[item] = os.path.isdir(item_path)

                html = "<html><body><table><tbody>"
                for item in sorted(merged_items.keys()):
                    is_dir = merged_items[item]
                    size_str = "directory" if is_dir else ""
                    # Actually get file size if it's not a directory?
                    if not is_dir:
                        # Find the first one to get size
                        for top_level in os.listdir(args.dir):
                            cand = os.path.join(args.dir, top_level, "Camera01", item)
                            if os.path.isfile(cand):
                                size_str = str(os.path.getsize(cand))
                                break

                    link_path = f"{item}/" if is_dir else item
                    html += f'<tr><td><a href="{link_path}">{item}</a></td><td></td><td>{size_str}</td></tr>'
                html += "</tbody></table></body></html>"
                return web.Response(text=html, content_type='text/html')

            else:
                # Find the file or sub-directory in one of the top-level directories
                for top_level in os.listdir(args.dir):
                    top_level_path = os.path.join(args.dir, top_level)
                    if os.path.isdir(top_level_path):
                        candidate = os.path.join(top_level_path, "Camera01", sub_path)
                        if os.path.exists(candidate):
                            if os.path.isdir(candidate):
                                if not req_path.endswith('/'):
                                    raise web.HTTPFound(req_path + '/')
                                html = "<html><body><table><tbody>"
                                for item in sorted(os.listdir(candidate)):
                                    if item.startswith('.'):
                                        continue
                                    item_path = os.path.join(candidate, item)
                                    is_dir = os.path.isdir(item_path)
                                    size_str = "directory" if is_dir else str(os.path.getsize(item_path))
                                    link_path = f"{item}/" if is_dir else item
                                    html += f'<tr><td><a href="{link_path}">{item}</a></td><td></td><td>{size_str}</td></tr>'
                                html += "</tbody></table></body></html>"
                                return web.Response(text=html, content_type='text/html')
                            else:
                                return web.FileResponse(candidate)

        raise web.HTTPNotFound()

    runner = None
    if args.http:
        # Start HTTP server
        app = web.Application(middlewares=[logging_middleware])
        app.router.add_route('GET', '/{tail:.*}', handle_http_request)
        runner = web.AppRunner(app)
        await runner.setup()
        http_site = web.TCPSite(runner, args.bind, 80)

        try:
            await http_site.start()
            logger.info(f"HTTP Server started on {args.bind}:80")
        except Exception as e:
            logger.error(f"Failed to start HTTP server on port 80: {e}")

    try:
        # Keep the process alive
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        pass
    finally:
        if runner:
            await runner.cleanup()
        if args.ble:
            await ble_handler.stop()
        if rtmp_server:
            rtmp_server.close()
            await rtmp_server.wait_closed()

def main_entry():
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server stopped")

if __name__ == "__main__":
    main_entry()
