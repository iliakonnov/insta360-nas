    async def handle_admin(request):
        ip = request.remote
        user_id = rtmp_handler.sessions.get(ip)
        if not user_id:
            raise web.HTTPForbidden(text="Not authorized or no active session.")

        user = db.get_user_by_id(user_id)
        if not user or not user['is_admin']:
            raise web.HTTPForbidden(text="Admin access required.")

        if request.method == 'POST':
            data = await request.post()
            action = data.get('action')
            if action == 'toggle_access':
                target_user_id = data.get('user_id')
                directory = data.get('directory')
                access_granted = data.get('access_granted') == 'on'

                if target_user_id and directory:
                    db.set_directory_access(target_user_id, directory, access_granted)
            elif action == 'toggle_authorize':
                target_user_id = data.get('user_id')
                authorized = data.get('authorized') == 'on'
                if target_user_id:
                    db.set_user_authorized(target_user_id, authorized)

            raise web.HTTPFound('/admin')

        all_users = db.get_all_users()
        all_top_levels = [d for d in os.listdir(args.dir) if os.path.isdir(os.path.join(args.dir, d))]

        html = f"<html><body><h1>Admin Panel</h1>"
        html += "<h2>Users</h2>"
        html += "<table border='1'><tr><th>ID</th><th>Name</th><th>Admin</th><th>Authorized</th><th>Directory Access</th></tr>"

        for u in all_users:
            html += f"<tr>"
            html += f"<td>{u['id']}</td>"
            html += f"<td>{u['name']}</td>"
            html += f"<td>{'Yes' if u['is_admin'] else 'No'}</td>"

            # Auth toggle
            html += f"<td>"
            html += f"<form style='display:inline;' method='POST'>"
            html += f"<input type='hidden' name='action' value='toggle_authorize'>"
            html += f"<input type='hidden' name='user_id' value='{u['id']}'>"
            html += f"<input type='hidden' name='authorized' value='{'' if u['authorized'] else 'on'}'>"
            html += f"<button type='submit'>{'Revoke Auth' if u['authorized'] else 'Grant Auth'}</button>"
            html += f"</form>"
            html += f"</td>"

            # Directory toggles
            user_dirs = db.get_user_directories(u['id'])
            access_map = {d['directory']: d['access_granted'] for d in user_dirs}

            html += "<td>"
            for d in all_top_levels:
                has_access = access_map.get(d, False)
                html += f"<form style='display:inline; margin-right: 10px;' method='POST'>"
                html += f"<input type='hidden' name='action' value='toggle_access'>"
                html += f"<input type='hidden' name='user_id' value='{u['id']}'>"
                html += f"<input type='hidden' name='directory' value='{d}'>"
                html += f"<input type='hidden' name='access_granted' value='{'' if has_access else 'on'}'>"
                html += f"<button type='submit'>{'Revoke ' + d if has_access else 'Grant ' + d}</button>"
                html += f"</form>"
            html += "</td>"

            html += "</tr>"

        html += "</table></body></html>"
        return web.Response(text=html, content_type='text/html')

    async def handle_dashboard(request):
        ip = request.remote
        user_id = rtmp_handler.sessions.get(ip)
        if not user_id:
            raise web.HTTPForbidden(text="Not authorized or no active session.")

        user = db.get_user_by_id(user_id)

        if request.method == 'POST':
            data = await request.post()
            action = data.get('action')
            if action == 'undelete':
                uri = data.get('uri')
                if uri:
                    db.unhide_file(user_id, uri)
            elif action == 'toggle_export':
                directory = data.get('directory')
                is_exported = data.get('is_exported') == 'on'
                if directory:
                    db.set_directory_export(user_id, directory, is_exported)

            raise web.HTTPFound('/dashboard')

        hidden_files = db.get_hidden_files(user_id)
        directories = db.get_user_directories(user_id)

        html = f"<html><body><h1>Dashboard - {user['name']}</h1>"

        html += "<h2>Exported Directories</h2>"
        html += "<form method='POST'>"
        html += "<table><tr><th>Directory</th><th>Exported</th><th>Action</th></tr>"
        for d in directories:
            if not d['access_granted']:
                continue
            checked = "checked" if d['is_exported'] else ""
            html += f"<tr>"
            html += f"<td>{d['directory']}</td>"
            html += f"<td><input type='checkbox' name='is_exported' {'checked'} disabled> {d['is_exported']}</td>"
            html += f"<td>"
            html += f"<form style='display:inline;' method='POST'>"
            html += f"<input type='hidden' name='action' value='toggle_export'>"
            html += f"<input type='hidden' name='directory' value='{d['directory']}'>"
            html += f"<input type='hidden' name='is_exported' value='{'' if d['is_exported'] else 'on'}'>"
            html += f"<button type='submit'>Toggle</button>"
            html += f"</form>"
            html += f"</td></tr>"
        html += "</table>"

        html += "<h2>Hidden Files</h2>"
        html += "<ul>"
        for uri in sorted(hidden_files):
            html += f"<li>{uri} "
            html += f"<form style='display:inline;' method='POST'>"
            html += f"<input type='hidden' name='action' value='undelete'>"
            html += f"<input type='hidden' name='uri' value='{uri}'>"
            html += f"<button type='submit'>Undelete</button>"
            html += f"</form></li>"
        if not hidden_files:
            html += "<li>No hidden files.</li>"
        html += "</ul>"
        html += "</body></html>"

        return web.Response(text=html, content_type='text/html')

    async def handle_http_request(request):
        ip = request.remote
        user_id = rtmp_handler.sessions.get(ip)

        # Skip IP check only for dashboard and admin? No, we need user context for both dashboard and general endpoints
        if not user_id:
            logger.warning(f"Unauthorized HTTP request to {request.path} from IP: {ip}")
            raise web.HTTPForbidden()

        allowed_dirs = db.get_allowed_directories(user_id)
        hidden_files = db.get_hidden_files(user_id)

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
                    if top_level not in allowed_dirs:
                        continue
                    top_level_path = os.path.join(args.dir, top_level)
                    if os.path.isdir(top_level_path):
                        camera01_path = os.path.join(top_level_path, "Camera01")
                        if os.path.isdir(camera01_path):
                            for item in os.listdir(camera01_path):
                                if item.startswith('.'):
                                    continue
                                uri = f"/DCIM/Camera01/{item}"
                                if not os.path.isdir(os.path.join(camera01_path, item)) and uri in hidden_files:
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
                        for top_level in allowed_dirs:
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
                for top_level in allowed_dirs:
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

                                    # Form relative URI from Camera01
                                    rel_uri_path = os.path.relpath(os.path.join(candidate, item), os.path.join(top_level_path, "Camera01"))
                                    uri = f"/DCIM/Camera01/{rel_uri_path}"
                                    if uri in hidden_files:
                                        continue

                                    item_path = os.path.join(candidate, item)
                                    is_dir = os.path.isdir(item_path)
                                    size_str = "directory" if is_dir else str(os.path.getsize(item_path))
                                    link_path = f"{item}/" if is_dir else item
                                    html += f'<tr><td><a href="{link_path}">{item}</a></td><td></td><td>{size_str}</td></tr>'
                                html += "</tbody></table></body></html>"
                                return web.Response(text=html, content_type='text/html')
                            else:
                                # We check if the exact file being requested is hidden
                                rel_uri_path = os.path.relpath(candidate, os.path.join(top_level_path, "Camera01"))
                                uri = f"/DCIM/Camera01/{rel_uri_path}"
                                if uri in hidden_files:
                                    continue
                                return web.FileResponse(candidate)

        raise web.HTTPNotFound()

    runner = None
    if args.http:
        # Start HTTP server
        app = web.Application(middlewares=[logging_middleware])
        app.router.add_route('GET', '/dashboard', handle_dashboard)
        app.router.add_route('POST', '/dashboard', handle_dashboard)
        app.router.add_route('GET', '/admin', handle_admin)
        app.router.add_route('POST', '/admin', handle_admin)
        app.router.add_route('GET', '/{tail:.*}', handle_http_request)
        runner = web.AppRunner(app)
        await runner.setup()
        http_port = 8080 if args.bind == "127.0.0.1" else 80
        http_site = web.TCPSite(runner, args.bind, http_port)

        try:
            await http_site.start()
            logger.info(f"HTTP Server started on {args.bind}:{http_port}")
        except Exception as e:
