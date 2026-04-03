import argparse
import asyncio
import os
import struct
import logging
from aiohttp import web

logging.basicConfig(
    level=logging.INFO,
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
}

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
        if len(pkt_data) < 12:
            return None

        header = pkt_data[:12]
        body = pkt_data[12:]

        msg_code = struct.unpack("<H", pkt_data[3:5])[0]
        seq = struct.unpack("<I", pkt_data[6:9] + b"\x00")[0]

        logger.info(f"RTMP Request Received - msg_code: {msg_code}, seq: {seq}, payload_size: {len(body)}")

        if msg_code not in pb_resp_classes:
            logger.warning(f"RTMP Request Unknown message code: {msg_code}")
            return None

        RespClass = pb_resp_classes[msg_code]
        resp_msg = RespClass()

        if msg_code == PHONE_COMMAND_GET_OPTIONS:
            resp_msg.value.camera_type = "Insta360 X5"
            resp_msg.value.firmwareRevision = "v1.0.0"
            # Some fields like battery_status scale might not exist or may have different names
            # we will just skip them if they cause issues, or set standard values
            if hasattr(resp_msg.value, "battery_status"):
                if hasattr(resp_msg.value.battery_status, "level"):
                    resp_msg.value.battery_status.level = 80
        elif msg_code == PHONE_COMMAND_GET_FILE_LIST:
            # Need to populate from self.media_dir
            for root, dirs, files in os.walk(self.media_dir):
                for file in files:
                    # Ignore non-media for now?
                    if file.startswith('.'):
                        continue
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, self.media_dir)
                    # Convert to /DCIM/ format
                    uri = f"/DCIM/{rel_path}"
                    resp_msg.uri.append(uri)
            # Some pb versions use totalCount, others might use total_count or it might be missing
            if hasattr(resp_msg, "totalCount"):
                resp_msg.totalCount = len(resp_msg.uri)
            elif hasattr(resp_msg, "total_count"):
                resp_msg.total_count = len(resp_msg.uri)
        # All other commands just get an empty/default OK response which is fine.

        logger.info(f"RTMP Response Sent - msg_code: {msg_code}, seq: {seq}, response: {resp_msg}")
        return self._pack_response(msg_code, seq, resp_msg)

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
    parser = argparse.ArgumentParser(description="Insta360 RTMP/HTTP Server")
    parser.add_argument("--bind", default="0.0.0.0", help="IP address to bind to")
    parser.add_argument("--dir", required=True, help="Directory to serve files from")
    args = parser.parse_args()

    rtmp_handler = RTMPHandler(args.dir)

    # Start RTMP TCP server
    rtmp_server = await asyncio.start_server(
        lambda r, w: handle_client(r, w, rtmp_handler),
        args.bind, 6666
    )
    logger.info(f"RTMP Server started on {args.bind}:6666")

    async def handle_http_request(request):
        rel_path = request.path
        if rel_path.startswith('/DCIM/'):
            rel_path = rel_path[6:] # strip /DCIM/

        full_path = os.path.join(args.dir, rel_path)

        if os.path.isdir(full_path):
            # Ensure path ends with / for correct HTML relative linking
            if not request.path.endswith('/'):
                raise web.HTTPFound(request.path + '/')

            # Generate HTML listing
            html = "<html><body><table><tbody>"
            for item in sorted(os.listdir(full_path)):
                if item.startswith('.'):
                    continue
                item_path = os.path.join(full_path, item)
                is_dir = os.path.isdir(item_path)

                size_str = "directory" if is_dir else str(os.path.getsize(item_path))
                link_path = f"{item}/" if is_dir else item

                html += f'<tr><td><a href="{link_path}">{item}</a></td><td></td><td>{size_str}</td></tr>'
            html += "</tbody></table></body></html>"
            return web.Response(text=html, content_type='text/html')

        elif os.path.isfile(full_path):
            return web.FileResponse(full_path)

        else:
            raise web.HTTPNotFound()

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
        # Could fallback to another port if not running as root, but user requested 80.

    async with rtmp_server:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            pass
        finally:
            await runner.cleanup()

def main_entry():
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server stopped")

if __name__ == "__main__":
    main_entry()
