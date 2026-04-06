def patch():
    with open("insta360-server/server.py") as f:
        content = f.read()

    old1 = '''    def _get_ip_from_client_id(self, client_id):
        ip = client_id
        if isinstance(client_id, str) and client_id.startswith("('"):
            try:
                import ast
                ip = ast.literal_eval(client_id)[0]
            except Exception:
                pass
        elif isinstance(client_id, tuple):
            ip = client_id[0]
        return ip

    def handle_packet(self, pkt_data, client_id=None):'''
    new1 = '''    def handle_packet(self, pkt_data, client_id=None):'''

    old2 = '''            elif msg_code == PHONE_COMMAND_GET_FILE_LIST:
                resp_msg = get_file_list_pb2.GetFileListResp()
                ip = self._get_ip_from_client_id(client_id)
                user_id = self.sessions.get(ip)'''
    new2 = '''            elif msg_code == PHONE_COMMAND_GET_FILE_LIST:
                resp_msg = get_file_list_pb2.GetFileListResp()
                ip = client_id[0] if isinstance(client_id, tuple) else client_id
                user_id = self.sessions.get(ip)'''

    old3 = '''            elif msg_code == PHONE_COMMAND_DELETE_FILES:
                req_msg = delete_files_pb2.DeleteFiles()
                req_msg.ParseFromString(body)
                logger.info(f"DeleteFiles request: {req_msg.uri}")

                resp_msg = delete_files_pb2.DeleteFilesResp()

                ip = self._get_ip_from_client_id(client_id)
                user_id = self.sessions.get(ip)'''
    new3 = '''            elif msg_code == PHONE_COMMAND_DELETE_FILES:
                req_msg = delete_files_pb2.DeleteFiles()
                req_msg.ParseFromString(body)
                logger.info(f"DeleteFiles request: {req_msg.uri}")

                resp_msg = delete_files_pb2.DeleteFilesResp()

                ip = client_id[0] if isinstance(client_id, tuple) else client_id
                user_id = self.sessions.get(ip)'''

    old4 = '''            elif msg_code == PHONE_COMMAND_CHECK_AUTHORIZATION:
                req_msg = check_authorization_pb2.CheckAuthorization()
                req_msg.ParseFromString(body)
                logger.info(f"CheckAuthorization request: {req_msg}")

                user = self.db.get_or_create_user(req_msg.id)
                resp_msg = check_authorization_pb2.CheckAuthorizationResp()

                if user["authorized"]:
                    logger.info(f"Authorization successful for ID: {req_msg.id}")
                    if client_id:
                        ip = self._get_ip_from_client_id(client_id)
                        self.sessions[ip] = req_msg.id
                        logger.info(f"Associated IP {ip} with User {req_msg.id}")
                    resp_msg.authorization_status = check_authorization_pb2.CheckAuthorizationResp.AUTHORIZED'''
    new4 = '''            elif msg_code == PHONE_COMMAND_CHECK_AUTHORIZATION:
                req_msg = check_authorization_pb2.CheckAuthorization()
                req_msg.ParseFromString(body)
                logger.info(f"CheckAuthorization request: {req_msg}")

                user = self.db.get_or_create_user(req_msg.id)
                resp_msg = check_authorization_pb2.CheckAuthorizationResp()

                if user.authorized:
                    logger.info(f"Authorization successful for ID: {req_msg.id}")
                    if client_id:
                        ip = client_id[0] if isinstance(client_id, tuple) else client_id
                        self.sessions[ip] = req_msg.id
                        logger.info(f"Associated IP {ip} with User {req_msg.id}")
                    resp_msg.authorization_status = check_authorization_pb2.CheckAuthorizationResp.AUTHORIZED'''

    old5 = '''            # 2. Process and send actual response
            pkt_data = value[4:]
            client_id = f"BLE-{kwargs.get('device', 'unknown')}"
            response = self.rtmp_handler.handle_packet(pkt_data, client_id=client_id)'''
    new5 = '''            # 2. Process and send actual response
            pkt_data = value[4:]
            client_id = (f"BLE-{kwargs.get('device', 'unknown')}", 0)
            response = self.rtmp_handler.handle_packet(pkt_data, client_id=client_id)'''

    old6 = '''            elif pkt_data[:3] == b'\\x04\\00\\00':
                response_pkt = rtmp_handler.handle_packet(pkt_data, client_id=str(peername))
                if response_pkt:'''
    new6 = '''            elif pkt_data[:3] == b'\\x04\\00\\00':
                response_pkt = rtmp_handler.handle_packet(pkt_data, client_id=peername)
                if response_pkt:'''

    content = content.replace(old1, new1)
    content = content.replace(old2, new2)
    content = content.replace(old3, new3)
    content = content.replace(old4, new4)
    content = content.replace(old5, new5)
    content = content.replace(old6, new6)

    with open("insta360-server/server.py", "w") as f:
        f.write(content)

if __name__ == "__main__":
    patch()
