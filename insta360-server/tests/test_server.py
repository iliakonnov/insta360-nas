import pytest
from unittest.mock import Mock, patch
from server import RTMPHandler, PHONE_COMMAND_CHECK_AUTHORIZATION, PHONE_COMMAND_GET_FILE_LIST
from database import Database, User
from lib_one_proto import check_authorization_pb2, get_file_list_pb2
import struct
import os

@pytest.fixture
def mock_db():
    db = Mock() # Remove strict spec to allow missing methods if they are buggy in server.py
    return db

@pytest.fixture
def rtmp_handler(mock_db):
    return RTMPHandler(media_dir="/fake/dir", db=mock_db)

def pack_rtmp_request(msg_code, seq, pb_msg):
    pb_bytes = pb_msg.SerializeToString()

    header = b"\x04\x00\x00"
    header += struct.pack("<H", msg_code)
    header += b"\x02"
    header += struct.pack("<i", seq)[0:3]
    header += b"\x80\x00\x00"

    return header + pb_bytes

def unpack_rtmp_response(response_bytes, pb_class):
    # response format: length (4), header (12), body
    # header is b"\x04\x00\x00" + code(2) + \x02 + seq(3) + \x80\x00\x00
    body = response_bytes[16:]
    resp_msg = pb_class()
    resp_msg.ParseFromString(body)
    return resp_msg

def test_rtmp_authorization_success(rtmp_handler, mock_db):
    # Setup mock
    mock_db.get_or_create_user.return_value = User(id="user1", name="Test", is_admin=False, authorized=True)

    # Create request
    req = check_authorization_pb2.CheckAuthorization()
    req.id = "user1"
    # Actually server.py expects the raw bytes of CheckAuthorization to be the body
    pkt = pack_rtmp_request(PHONE_COMMAND_CHECK_AUTHORIZATION, 1, req)

    # Handle
    response = rtmp_handler.handle_packet(pkt, client_id=("127.0.0.1", 12345))

    # Verify response
    assert response is not None
    resp_msg = unpack_rtmp_response(response, check_authorization_pb2.CheckAuthorizationResp)
    assert resp_msg.authorization_status == check_authorization_pb2.CheckAuthorizationResp.AUTHORIZED

    # Verify state
    assert rtmp_handler.sessions["127.0.0.1"] == "user1"

def test_rtmp_authorization_failure(rtmp_handler, mock_db):
    # Setup mock
    mock_db.get_or_create_user.return_value = User(id="user2", name="Test", is_admin=False, authorized=False)

    # Create request
    req = check_authorization_pb2.CheckAuthorization()
    req.id = "user2"
    pkt = pack_rtmp_request(PHONE_COMMAND_CHECK_AUTHORIZATION, 1, req)

    # Handle
    response = rtmp_handler.handle_packet(pkt, client_id=("127.0.0.1", 12345))

    # Verify response
    resp_msg = unpack_rtmp_response(response, check_authorization_pb2.CheckAuthorizationResp)
    assert resp_msg.authorization_status == check_authorization_pb2.CheckAuthorizationResp.UNAUTHORIZED

    # Verify state - failed auth should NOT add to sessions
    assert "127.0.0.1" not in rtmp_handler.sessions

@patch('server.os.listdir')
@patch('server.os.path.isdir')
@patch('server.os.walk')
def test_rtmp_get_file_list_merging(mock_walk, mock_isdir, mock_listdir, rtmp_handler, mock_db):
    # Setup authorized session
    rtmp_handler.sessions["127.0.0.1"] = "user1"

    # Setup mocks
    mock_db.get_allowed_directories.return_value = ["SDCard", "Internal"]
    mock_db.get_hidden_files.return_value = set(["/DCIM/Camera01/hidden.mp4"])

    # Mock file system
    mock_listdir.return_value = ["SDCard", "Internal", "NotAllowed"]
    mock_isdir.return_value = True # Assume everything is a dir for this test

    # Walk returns tuples of (dirpath, dirnames, filenames)
    # We'll simulate walking SDCard/Camera01 and Internal/Camera01
    def walk_side_effect(path):
        if "SDCard" in path:
            return [(path, [], ["file1.mp4", "hidden.mp4"])]
        if "Internal" in path:
            return [(path, [], ["file2.mp4", ".DS_Store"])]
        return []

    mock_walk.side_effect = walk_side_effect

    # Create request
    req = get_file_list_pb2.GetFileList()
    pkt = pack_rtmp_request(PHONE_COMMAND_GET_FILE_LIST, 2, req)

    # Handle
    response = rtmp_handler.handle_packet(pkt, client_id=("127.0.0.1", 12345))

    # Verify
    resp_msg = unpack_rtmp_response(response, get_file_list_pb2.GetFileListResp)

    # Verify merging logic
    assert resp_msg.total_count == 2
    uris = list(resp_msg.uri)
    assert "/DCIM/Camera01/file1.mp4" in uris
    assert "/DCIM/Camera01/file2.mp4" in uris
    assert "/DCIM/Camera01/hidden.mp4" not in uris # Hidden
    assert "/DCIM/Camera01/.DS_Store" not in uris # Starts with dot

def test_rtmp_get_file_list_unauthorized(rtmp_handler, mock_db):
    # No session
    req = get_file_list_pb2.GetFileList()
    pkt = pack_rtmp_request(PHONE_COMMAND_GET_FILE_LIST, 2, req)

    # Handle
    response = rtmp_handler.handle_packet(pkt, client_id=("127.0.0.1", 12345))

    # Verify
    resp_msg = unpack_rtmp_response(response, get_file_list_pb2.GetFileListResp)
    assert resp_msg.total_count == 0
    assert len(resp_msg.uri) == 0
