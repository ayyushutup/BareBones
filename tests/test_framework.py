import unittest
import json
import gzip
from barebones.router import Router, Request, Response
from barebones.websocket import calculate_accept_key
from barebones.static import parse_range_header
from barebones.sessions import sign_session, verify_session
from barebones.middleware import MiddlewareChain, gzip_middleware

class MockSocket:
    def __init__(self):
        self.sent_data = bytearray()
    def sendall(self, data):
        self.sent_data.extend(data)
    def close(self):
        pass

class TestBareBonesFramework(unittest.TestCase):
    
    def test_routing_path_parameters(self):
        router = Router()
        
        # Define test routes
        router.add_route("GET", "/users/<user_id>/profile", lambda r, user_id: f"user-{user_id}")
        router.add_route("GET", "/static/<path:filepath>", lambda r, filepath: f"path-{filepath}")
        
        # Test basic match
        handler, params = router.match("GET", "/users/123/profile")
        self.assertIsNotNone(handler)
        self.assertEqual(params, {"user_id": "123"})
        self.assertEqual(handler(None, **params), "user-123")
        
        # Test path wildcards
        handler, params = router.match("GET", "/static/css/styles.css")
        self.assertIsNotNone(handler)
        self.assertEqual(params, {"filepath": "css/styles.css"})
        self.assertEqual(handler(None, **params), "path-css/styles.css")
        
        # Test no match
        handler, params = router.match("GET", "/users/123")
        self.assertIsNone(handler)

    def test_middleware_ordering(self):
        chain = MiddlewareChain()
        execution_order = []
        
        def mw1(req, next_fn):
            execution_order.append("mw1-in")
            resp = next_fn(req)
            execution_order.append("mw1-out")
            return resp
            
        def mw2(req, next_fn):
            execution_order.append("mw2-in")
            resp = next_fn(req)
            execution_order.append("mw2-out")
            return resp
            
        chain.add(mw1)
        chain.add(mw2)
        
        req = Request("GET", "/", {}, {}, b"", {})
        final_handler = lambda r: Response(b"handler")
        
        resp = chain.execute(req, final_handler)
        self.assertEqual(resp.body, b"handler")
        self.assertEqual(execution_order, ["mw1-in", "mw2-in", "mw2-out", "mw1-out"])

    def test_byte_range_header_parsing(self):
        # 1. Standard Range
        start, end = parse_range_header("bytes=100-200", 1000)
        self.assertEqual((start, end), (100, 200))
        
        # 2. Open ended range
        start, end = parse_range_header("bytes=500-", 1000)
        self.assertEqual((start, end), (500, 999))
        
        # 3. Suffix length range
        start, end = parse_range_header("bytes=-300", 1000)
        self.assertEqual((start, end), (700, 999))
        
        # 4. Out of bounds range
        res = parse_range_header("bytes=1200-1300", 1000)
        self.assertIsNone(res)

    def test_websocket_accept_key(self):
        # Test vector from RFC 6455
        client_key = "dGhlIHNhbXBsZSBub25jZQ=="
        expected_accept = "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="
        self.assertEqual(calculate_accept_key(client_key), expected_accept)

    def test_signed_session_cookies(self):
        secret = "test_signing_key_123"
        session_data = {"user": "admin", "role": "superuser"}
        
        # 1. Sign
        cookie_val = sign_session(session_data, secret)
        self.assertTrue("." in cookie_val)
        
        # 2. Verify and decode
        decoded = verify_session(cookie_val, secret)
        self.assertEqual(decoded, session_data)
        
        # 3. Tamper detection
        payload, signature = cookie_val.split(".", 1)
        tampered_sig = signature[:-3] + "abc"
        tampered_cookie = f"{payload}.{tampered_sig}"
        self.assertEqual(verify_session(tampered_cookie, secret), {})

    def test_gzip_compression(self):
        # Create a mock route chain with gzip middleware
        req = Request("GET", "/test", {"accept-encoding": "gzip"}, {}, b"", {})
        
        # Large body eligible for compression
        large_body = "Hello World! " * 100
        handler = lambda r: Response.html(large_body)
        
        resp = gzip_middleware(req, handler)
        
        self.assertEqual(resp.headers.get("content-encoding"), "gzip")
        # Decompress and verify
        decompressed = gzip.decompress(resp.body).decode('utf-8')
        self.assertEqual(decompressed, large_body)

if __name__ == "__main__":
    unittest.main()
