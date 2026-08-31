import hmac
import hashlib
import json
import base64
import copy
from .router import Response

def sign_session(session_dict, secret_key):
    # Serialize to JSON and encode to base64
    json_bytes = json.dumps(session_dict).encode('utf-8')
    b64_str = base64.b64encode(json_bytes).decode('utf-8')
    # Sign base64 payload
    sig = hmac.new(secret_key.encode('utf-8'), b64_str.encode('utf-8'), hashlib.sha256).hexdigest()
    return f"{b64_str}.{sig}"

def verify_session(cookie_value, secret_key):
    if not cookie_value:
        return {}
    try:
        parts = cookie_value.split('.', 1)
        if len(parts) != 2:
            return {}
        b64_str, sig = parts
        # Verify HMAC-SHA256 signature
        expected_sig = hmac.new(secret_key.encode('utf-8'), b64_str.encode('utf-8'), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return {}
        # Decode base64 and parse JSON
        json_bytes = base64.b64decode(b64_str.encode('utf-8'))
        return json.loads(json_bytes.decode('utf-8'))
    except Exception:
        return {}

def session_middleware(secret_key, session_cookie_name="session"):
    def middleware(req, next_fn):
        # 1. Load session from cookie
        cookie_val = req.cookies.get(session_cookie_name, "")
        req.session = verify_session(cookie_val, secret_key)
        
        # Keep copy of original session state to see if it changes
        original_session = copy.deepcopy(req.session)
        
        # 2. Process request
        resp = next_fn(req)
        
        # 3. If session changed, sign and set new cookie
        if req.session != original_session:
            new_cookie_val = sign_session(req.session, secret_key)
            resp.set_cookie(session_cookie_name, new_cookie_val, httponly=True, samesite="Lax")
            
        return resp
    return middleware
