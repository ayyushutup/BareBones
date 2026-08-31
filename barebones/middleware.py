import time
import gzip
import json
import urllib.parse
from .router import Response

class MiddlewareChain:
    def __init__(self):
        self.middlewares = []

    def add(self, middleware_func):
        self.middlewares.append(middleware_func)

    def execute(self, request, final_handler):
        def make_next(index):
            if index < len(self.middlewares):
                current_mw = self.middlewares[index]
                return lambda req: current_mw(req, make_next(index + 1))
            else:
                return final_handler
        return make_next(0)(request)

def logger_middleware(req, next_fn):
    start = time.time()
    resp = next_fn(req)
    duration = (time.time() - start) * 1000
    print(f"[{req.method}] {req.path} -> {resp.status} ({duration:.2f}ms)")
    return resp

def cors_middleware(allowed_origins="*", allowed_methods="GET, POST, PUT, DELETE, OPTIONS", allowed_headers="Content-Type, Authorization, Cookie"):
    def middleware(req, next_fn):
        if req.method == "OPTIONS":
            resp = Response(status=204)
            resp.set_header("Access-Control-Allow-Origin", allowed_origins)
            resp.set_header("Access-Control-Allow-Methods", allowed_methods)
            resp.set_header("Access-Control-Allow-Headers", allowed_headers)
            resp.set_header("Access-Control-Allow-Credentials", "true")
            return resp
        
        resp = next_fn(req)
        resp.set_header("Access-Control-Allow-Origin", allowed_origins)
        resp.set_header("Access-Control-Allow-Methods", allowed_methods)
        resp.set_header("Access-Control-Allow-Headers", allowed_headers)
        resp.set_header("Access-Control-Allow-Credentials", "true")
        return resp
    return middleware

def json_parser_middleware(req, next_fn):
    content_type = req.headers.get("content-type", "")
    if "application/json" in content_type and req.body:
        try:
            req.json = json.loads(req.body.decode('utf-8'))
        except Exception:
            return Response.json({"error": "Invalid JSON"}, status=400)
    return next_fn(req)

def form_parser_middleware(req, next_fn):
    content_type = req.headers.get("content-type", "")
    if "application/x-www-form-urlencoded" in content_type and req.body:
        try:
            req.form = dict(urllib.parse.parse_qsl(req.body.decode('utf-8')))
        except Exception:
            return Response.json({"error": "Invalid form data"}, status=400)
    return next_fn(req)

def gzip_middleware(req, next_fn):
    resp = next_fn(req)
    
    # Check if gzip is accepted
    accept_encoding = req.headers.get("accept-encoding", "")
    if "gzip" not in accept_encoding:
        return resp
        
    content_type = resp.headers.get("content-type", "")
    if not resp.body or len(resp.body) < 100:
        return resp
        
    # Check eligibility (text files, json, HTML, scripts)
    eligible_types = ["text/", "json", "javascript", "xml"]
    if not any(t in content_type for t in eligible_types):
        return resp
        
    if "content-encoding" in resp.headers:
        return resp
        
    try:
        compressed = gzip.compress(resp.body)
        if len(compressed) < len(resp.body):
            resp.body = compressed
            resp.set_header("Content-Encoding", "gzip")
            resp.set_header("Content-Length", str(len(compressed)))
    except Exception:
        pass
        
    return resp

import threading

class TokenBucket:
    def __init__(self, capacity, rate):
        self.capacity = float(capacity)
        self.rate = float(rate)
        self.tokens = float(capacity)
        self.last_update = time.time()
        self.lock = threading.Lock()

    def consume(self):
        with self.lock:
            now = time.time()
            elapsed = now - self.last_update
            self.last_update = now
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return True, 0.0
            # Compute wait time for 1 token
            needed = 1.0 - self.tokens
            wait_time = needed / self.rate
            return False, wait_time

class RateLimiter:
    def __init__(self, capacity, rate):
        self.capacity = capacity
        self.rate = rate
        self.buckets = {}
        self.lock = threading.Lock()

    def get_bucket(self, ip):
        with self.lock:
            if ip not in self.buckets:
                self.buckets[ip] = TokenBucket(self.capacity, self.rate)
            return self.buckets[ip]

def rate_limit_middleware(capacity=10, rate=5.0):
    limiter = RateLimiter(capacity, rate)
    def middleware(req, next_fn):
        ip = "127.0.0.1"
        if req.socket:
            try:
                ip = req.socket.getpeername()[0]
            except Exception:
                pass
                
        # Skip rate limiter for WebSockets, Telemetry streaming, or if bypass header is present
        if "x-bypass-rate-limit" in req.headers or req.headers.get("upgrade", "").lower() == "websocket" or req.path == "/api/telemetry":
            return next_fn(req)
            
        bucket = limiter.get_bucket(ip)
        allowed, wait_time = bucket.consume()
        if not allowed:
            resp = Response.json(
                {"error": "Too Many Requests", "retry_after": round(wait_time, 2)},
                status=429
            )
            resp.set_header("Retry-After", str(max(1, int(wait_time))))
            return resp
            
        return next_fn(req)
    return middleware

