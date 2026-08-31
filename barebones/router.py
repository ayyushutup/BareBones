import json
import re
import urllib.parse

class Request:
    def __init__(self, method, path, headers, query, body, cookies, socket=None):
        self.method = method.upper()
        self.path = path
        self.headers = {k.lower(): v for k, v in headers.items()}
        self.query = query
        self.body = body
        self.cookies = cookies
        self.socket = socket
        self.session = {}  # Decrypted session dict
        self.json = None   # Parsed JSON dict
        self.form = None   # Parsed URL-encoded dict
        self.path_params = {}

class Response:
    STATUS_MAP = {
        101: "Switching Protocols",
        200: "OK",
        201: "Created",
        204: "No Content",
        206: "Partial Content",
        301: "Moved Permanently",
        302: "Found",
        400: "Bad Request",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Not Found",
        405: "Method Not Allowed",
        500: "Internal Server Error",
    }

    def __init__(self, body=b"", status=200, headers=None):
        self.status = status
        self.body = body if isinstance(body, bytes) else body.encode('utf-8')
        self.headers = {}
        if headers:
            for k, v in headers.items():
                self.headers[k.lower()] = str(v)
        self.cookies_to_set = []
        self.file_path = None
        self.file_offset = 0
        self.file_length = None

    def get_body_chunks(self, chunk_size=8192):
        if self.file_path:
            try:
                with open(self.file_path, "rb") as f:
                    if self.file_offset:
                        f.seek(self.file_offset)
                    remaining = self.file_length if self.file_length is not None else float('inf')
                    while remaining > 0:
                        to_read = min(chunk_size, remaining)
                        chunk = f.read(to_read)
                        if not chunk:
                            break
                        yield chunk
                        remaining -= len(chunk)
            except Exception:
                yield b""
        else:
            yield self.body

    def set_header(self, name, value):
        self.headers[name.lower()] = str(value)

    def set_cookie(self, name, value, max_age=None, expires=None, path="/", domain=None, secure=False, httponly=False, samesite="Lax"):
        cookie = f"{name}={value}"
        if max_age is not None:
            cookie += f"; Max-Age={max_age}"
        if expires is not None:
            cookie += f"; Expires={expires}"
        if path:
            cookie += f"; Path={path}"
        if domain:
            cookie += f"; Domain={domain}"
        if secure:
            cookie += "; Secure"
        if httponly:
            cookie += "; HttpOnly"
        if samesite:
            cookie += f"; SameSite={samesite}"
        self.cookies_to_set.append(cookie)

    def delete_cookie(self, name, path="/", domain=None):
        self.set_cookie(name, "", max_age=0, expires="Thu, 01 Jan 1970 00:00:00 GMT", path=path, domain=domain)

    @classmethod
    def json(cls, data, status=200, headers=None):
        body = json.dumps(data).encode('utf-8')
        resp = cls(body, status, headers)
        resp.set_header("Content-Type", "application/json")
        return resp

    @classmethod
    def html(cls, html_content, status=200, headers=None):
        body = html_content.encode('utf-8') if isinstance(html_content, str) else html_content
        resp = cls(body, status, headers)
        resp.set_header("Content-Type", "text/html; charset=utf-8")
        return resp

    @classmethod
    def text(cls, text_content, status=200, headers=None):
        body = text_content.encode('utf-8') if isinstance(text_content, str) else text_content
        resp = cls(body, status, headers)
        resp.set_header("Content-Type", "text/plain; charset=utf-8")
        return resp

class Router:
    def __init__(self):
        self.routes = []

    def add_route(self, method, path, handler):
        # Escape regex special characters, except '<' and '>'
        pattern = ""
        in_tag = False
        for char in path:
            if char == '<':
                in_tag = True
                pattern += char
            elif char == '>':
                in_tag = False
                pattern += char
            else:
                if in_tag:
                    pattern += char
                else:
                    pattern += re.escape(char)
        
        # Replace tags in a single pass to prevent nested substitution bugs
        def replace_tag(match):
            tag = match.group(1)
            if tag.startswith("path:"):
                return f"(?P<{tag[5:]}>.+)"
            return f"(?P<{tag}>[^/]+)"

        pattern = re.sub(r'<([^>]+)>', replace_tag, pattern)
        
        regex = re.compile("^" + pattern + "$")
        self.routes.append((method.upper(), regex, handler))

    def match(self, method, path):
        for r_method, r_regex, handler in self.routes:
            if r_method == method:
                m = r_regex.match(path)
                if m:
                    return handler, m.groupdict()
        return None, None
