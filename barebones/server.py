import socket
import threading
import selectors
import urllib.parse
from .router import Request, Response, Router
from .middleware import MiddlewareChain
from .websocket import calculate_accept_key, WebSocketConnection

class ConnectionState:
    def __init__(self, sock):
        self.sock = sock
        self.read_buffer = bytearray()
        self.write_buffer = bytearray()
        self.request = None
        self.request_body_acc = bytearray()
        self.response = None
        self.response_generator = None

class BareBones:
    def __init__(self, secret_key="barebones_secret"):
        self.router = Router()
        self.ws_router = Router()
        self.middleware = MiddlewareChain()
        self.secret_key = secret_key
        self.concurrency_mode = "threaded"
        self.running = False
        self.server_sock = None
        self._mode_changed = False
        self.selector = None

        # Register default body parser and session middlewares
        from .middleware import json_parser_middleware, form_parser_middleware, gzip_middleware
        from .sessions import session_middleware
        self.middleware.add(json_parser_middleware)
        self.middleware.add(form_parser_middleware)
        self.middleware.add(session_middleware(secret_key))
        self.middleware.add(gzip_middleware)

    def get(self, path):
        def decorator(handler):
            self.router.add_route("GET", path, handler)
            return handler
        return decorator

    def post(self, path):
        def decorator(handler):
            self.router.add_route("POST", path, handler)
            return handler
        return decorator

    def put(self, path):
        def decorator(handler):
            self.router.add_route("PUT", path, handler)
            return handler
        return decorator

    def delete(self, path):
        def decorator(handler):
            self.router.add_route("DELETE", path, handler)
            return handler
        return decorator

    def websocket(self, path):
        def decorator(handler):
            self.ws_router.add_route("GET", path, handler)
            return handler
        return decorator

    def run(self, host="127.0.0.1", port=8080, mode="threaded"):
        self.concurrency_mode = mode
        self.running = True
        
        while self.running:
            self._mode_changed = False
            self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                self.server_sock.bind((host, port))
                self.server_sock.listen(128)
                print(f"[*] BareBones running at http://{host}:{port}/ in {self.concurrency_mode.upper()} mode")
            except Exception as e:
                print(f"[!] Bind failed on {host}:{port}: {e}")
                break

            if self.concurrency_mode == "threaded":
                self._run_threaded()
            else:
                self._run_eventloop()

            if not self._mode_changed:
                break

    def toggle_mode(self, new_mode):
        if new_mode in ["threaded", "eventloop"] and new_mode != self.concurrency_mode:
            print(f"[*] Switching concurrency mode to {new_mode.upper()}...")
            self.concurrency_mode = new_mode
            self._mode_changed = True
            if self.server_sock:
                try:
                    self.server_sock.close()
                except Exception:
                    pass
            if self.selector:
                try:
                    self.selector.close()
                except Exception:
                    pass

    def _run_threaded(self):
        self.server_sock.settimeout(0.1)
        while self.running and not self._mode_changed:
            try:
                client_sock, addr = self.server_sock.accept()
            except socket.timeout:
                continue
            except Exception:
                break

            t = threading.Thread(target=handle_client_sync, args=(client_sock, self), daemon=True)
            t.start()

    def _run_eventloop(self):
        self.selector = selectors.DefaultSelector()
        self.server_sock.setblocking(False)
        self.selector.register(self.server_sock, selectors.EVENT_READ, data="accept")

        while self.running and not self._mode_changed:
            try:
                events = self.selector.select(timeout=1.0)
            except Exception:
                break

            for key, mask in events:
                if key.data == "accept":
                    try:
                        client_sock, addr = self.server_sock.accept()
                        client_sock.setblocking(False)
                        state = ConnectionState(client_sock)
                        self.selector.register(client_sock, selectors.EVENT_READ, data=state)
                    except Exception:
                        pass
                else:
                    state = key.data
                    if mask & selectors.EVENT_READ:
                        self.process_read(state)
                    if mask & selectors.EVENT_WRITE:
                        self.process_write(state)

        # Close all selector registrations
        try:
            self.selector.close()
        except Exception:
            pass

    def close_connection(self, state):
        try:
            self.selector.unregister(state.sock)
        except Exception:
            pass
        try:
            state.sock.close()
        except Exception:
            pass

    def process_read(self, state):
        try:
            chunk = state.sock.recv(4096)
        except (BlockingIOError, InterruptedError):
            return
        except Exception:
            self.close_connection(state)
            return

        if not chunk:
            self.close_connection(state)
            return

        if not state.request:
            state.read_buffer.extend(chunk)
            if b"\r\n\r\n" in state.read_buffer:
                parts = state.read_buffer.split(b"\r\n\r\n", 1)
                header_bytes = parts[0]
                body_bytes = parts[1]
                
                req = parse_request_headers(header_bytes, state.sock)
                if not req:
                    self.close_connection(state)
                    return
                state.request = req
                state.request_body_acc.extend(body_bytes)
        else:
            state.request_body_acc.extend(chunk)

        if state.request:
            content_length = int(state.request.headers.get("content-length", 0))
            if len(state.request_body_acc) >= content_length:
                state.request.body = bytes(state.request_body_acc[:content_length])
                parse_request_cookies_and_body(state.request)

                # Check WS upgrade
                if state.request.headers.get("upgrade", "").lower() == "websocket" and self.ws_router:
                    ws_handler, ws_path_params = self.ws_router.match(state.request.method, state.request.path)
                    if ws_handler:
                        try:
                            self.selector.unregister(state.sock)
                        except Exception:
                            pass
                        state.sock.setblocking(True)
                        handle_ws_upgrade(state.sock, state.request, ws_handler, ws_path_params)
                        return

                handler, path_params = self.router.match(state.request.method, state.request.path)
                if not handler:
                    resp = Response(b"Not Found", status=404)
                else:
                    state.request.path_params = path_params
                    final_handler = lambda r: handler(r, **r.path_params)
                    resp = self.middleware.execute(state.request, final_handler)

                if getattr(resp, "hijacked", False):
                    try:
                        self.selector.unregister(state.sock)
                    except Exception:
                        pass
                    return

                state.response = resp
                status_text = Response.STATUS_MAP.get(resp.status, "Unknown")
                res_lines = [f"HTTP/1.1 {resp.status} {status_text}"]
                if "content-length" not in resp.headers and not resp.file_path:
                    resp.set_header("Content-Length", str(len(resp.body)))
                for k, v in resp.headers.items():
                    res_lines.append(f"{k.title()}: {v}")
                for cookie in resp.cookies_to_set:
                    res_lines.append(f"Set-Cookie: {cookie}")
                res_lines.append("")
                res_lines.append("")

                state.write_buffer.extend("\r\n".join(res_lines).encode('utf-8'))
                state.response_generator = resp.get_body_chunks()
                self.selector.modify(state.sock, selectors.EVENT_WRITE, data=state)

    def process_write(self, state):
        if not state.write_buffer:
            if state.response_generator:
                try:
                    chunk = next(state.response_generator)
                    state.write_buffer.extend(chunk)
                except StopIteration:
                    self.close_connection(state)
                    return
                except Exception:
                    self.close_connection(state)
                    return
            else:
                self.close_connection(state)
                return

        try:
            sent = state.sock.send(state.write_buffer)
            state.write_buffer = state.write_buffer[sent:]
        except (BlockingIOError, InterruptedError):
            pass
        except Exception:
            self.close_connection(state)

def parse_request_headers(header_bytes, sock):
    try:
        header_lines = header_bytes.decode('utf-8', errors='ignore').split('\r\n')
        if not header_lines or not header_lines[0]:
            return None
        req_line = header_lines[0].split(' ')
        if len(req_line) < 2:
            return None
        method, full_path = req_line[0], req_line[1]

        path = full_path
        query = {}
        if '?' in full_path:
            path, query_str = full_path.split('?', 1)
            for pair in query_str.split('&'):
                if '=' in pair:
                    k, v = pair.split('=', 1)
                    query[urllib.parse.unquote(k)] = urllib.parse.unquote(v)
                elif pair:
                    query[urllib.parse.unquote(pair)] = ""

        headers = {}
        for line in header_lines[1:]:
            if not line:
                continue
            if ':' in line:
                k, v = line.split(':', 1)
                headers[k.strip().lower()] = v.strip()

        return Request(method, path, headers, query, b"", {}, sock)
    except Exception:
        return None

def parse_request_cookies_and_body(req):
    cookie_hdr = req.headers.get("cookie", "")
    cookies = {}
    if cookie_hdr:
        for item in cookie_hdr.split(';'):
            if '=' in item:
                k, v = item.split('=', 1)
                cookies[k.strip()] = v.strip()
    req.cookies = cookies

def handle_client_sync(client_sock, app):
    client_sock.settimeout(10.0)
    upgraded = False
    try:
        req = parse_request_sync(client_sock)
        if not req:
            return

        # Check WS upgrade
        if req.headers.get("upgrade", "").lower() == "websocket" and app.ws_router:
            ws_handler, ws_path_params = app.ws_router.match(req.method, req.path)
            if ws_handler:
                upgraded = True
                handle_ws_upgrade(client_sock, req, ws_handler, ws_path_params)
                return

        handler, path_params = app.router.match(req.method, req.path)
        if not handler:
            resp = Response(b"Not Found", status=404)
        else:
            req.path_params = path_params
            final_handler = lambda r: handler(r, **r.path_params)
            resp = app.middleware.execute(req, final_handler)

        if getattr(resp, "hijacked", False):
            upgraded = True
            return

        send_response_sync(client_sock, resp)
    except Exception as e:
        print("[!] Thread error:", e)
        try:
            send_response_sync(client_sock, Response(b"Internal Server Error", status=500))
        except Exception:
            pass
    finally:
        if not upgraded:
            try:
                client_sock.close()
            except Exception:
                pass

def parse_request_sync(client_sock):
    buffer = bytearray()
    while b"\r\n\r\n" not in buffer:
        chunk = client_sock.recv(4096)
        if not chunk:
            break
        buffer.extend(chunk)
    if not buffer:
        return None

    parts = buffer.split(b"\r\n\r\n", 1)
    header_bytes = parts[0]
    body_buffer = bytearray(parts[1]) if len(parts) > 1 else bytearray()

    req = parse_request_headers(header_bytes, client_sock)
    if not req:
        return None

    content_length = int(req.headers.get("content-length", 0))
    while len(body_buffer) < content_length:
        chunk = client_sock.recv(4096)
        if not chunk:
            break
        body_buffer.extend(chunk)

    req.body = bytes(body_buffer[:content_length])
    parse_request_cookies_and_body(req)
    return req

def send_response_sync(client_sock, resp):
    status_text = Response.STATUS_MAP.get(resp.status, "Unknown")
    res_lines = [f"HTTP/1.1 {resp.status} {status_text}"]

    if "content-length" not in resp.headers and not resp.file_path:
        resp.set_header("Content-Length", str(len(resp.body)))

    for k, v in resp.headers.items():
        res_lines.append(f"{k.title()}: {v}")

    for cookie in resp.cookies_to_set:
        res_lines.append(f"Set-Cookie: {cookie}")

    res_lines.append("")
    res_lines.append("")

    header_bytes = "\r\n".join(res_lines).encode('utf-8')
    client_sock.sendall(header_bytes)

    for chunk in resp.get_body_chunks():
        client_sock.sendall(chunk)

def handle_ws_upgrade(client_sock, req, ws_handler, ws_path_params):
    sec_key = req.headers.get("sec-websocket-key", "")
    if not sec_key:
        try:
            send_response_sync(client_sock, Response(b"Missing Sec-WebSocket-Key", status=400))
        except Exception:
            pass
        return

    accept_key = calculate_accept_key(sec_key)
    res_lines = [
        "HTTP/1.1 101 Switching Protocols",
        "Upgrade: websocket",
        "Connection: Upgrade",
        f"Sec-WebSocket-Accept: {accept_key}",
        "",
        ""
    ]
    header_bytes = "\r\n".join(res_lines).encode('utf-8')
    client_sock.sendall(header_bytes)

    ws_conn = WebSocketConnection(client_sock)
    def run_ws():
        try:
            ws_handler(ws_conn, **ws_path_params)
        except Exception as e:
            print("[!] WebSocket handler error:", e)
        finally:
            ws_conn.close()

    t = threading.Thread(target=run_ws, daemon=True)
    t.start()
