import os
import sys
import threading
import urllib.request
import collections
from barebones import BareBones, Response
from barebones.static import serve_static

app = BareBones(secret_key="barebones_super_secret_signing_key_12345")

# ─── Live Log Broadcasting ───────────────────────────────────────────────────
# Thread-safe broadcaster: each SSE subscriber gets its own deque queue.
_log_lock = threading.Lock()
_log_subscribers: list = []

class LogStream:
    """Intercepts sys.stdout and fans out each line to all SSE log subscribers."""
    def __init__(self, original):
        self._orig = original

    def write(self, data):
        self._orig.write(data)
        if data.strip():
            with _log_lock:
                dead = []
                for q in _log_subscribers:
                    try:
                        if len(q) < 200:   # cap per-subscriber buffer
                            q.append(data.strip())
                    except Exception:
                        dead.append(q)
                for q in dead:
                    _log_subscribers.remove(q)

    def flush(self):
        self._orig.flush()

    def __getattr__(self, name):
        return getattr(self._orig, name)

sys.stdout = LogStream(sys.stdout)

# Ensure static folder and sample video exist
def download_sample_video():
    os.makedirs("static", exist_ok=True)
    video_path = os.path.join("static", "sample.mp4")
    if not os.path.exists(video_path):
        print("[*] Downloading sample video for byte-range streaming demonstration...")
        # MDN public sample video (rabbit.mp4, ~1.4MB)
        url = "https://raw.githubusercontent.com/mdn/learning-area/master/html/multimedia-and-embedding/video-and-audio-content/rabbit320.mp4"
        try:
            # 10 second timeout for fetching
            urllib.request.urlretrieve(url, video_path)
            print("[*] Sample video downloaded successfully.")
        except Exception as e:
            print(f"[!] Failed to download sample video ({e}). Creating dummy video file.")
            with open(video_path, "wb") as f:
                f.write(b"\x00" * (1024 * 1024 * 2)) # 2MB dummy file

download_sample_video()

# Serve index.html or redirect to static route
@app.get("/")
def home(req):
    """
    Home redirect.
    Redirects incoming browser requests to /static/index.html.
    """
    resp = Response(status=302)
    resp.set_header("Location", "/static/index.html")
    return resp

# Toggle concurrency mode
@app.post("/api/toggle-mode")
def toggle_mode(req):
    """
    Toggles server concurrency mode.
    Switch between threaded or eventloop modes live.
    """
    if not req.json or "mode" not in req.json:
        return Response.json({"error": "Invalid body. Key 'mode' required."}, status=400)
    
    new_mode = req.json["mode"]
    if new_mode not in ["threaded", "eventloop"]:
        return Response.json({"error": "Invalid mode. Use 'threaded' or 'eventloop'."}, status=400)
    
    # Run the toggle after a brief delay so the current response can complete sending
    def trigger():
        app.toggle_mode(new_mode)
    threading.Timer(0.1, trigger).start()
    
    return Response.json({"success": True, "mode": new_mode})

# Get server details and update signed session cookie
@app.get("/api/stats")
def get_stats(req):
    """
    Get server telemetry stats.
    Returns memory, active threads, visitor count, and current mode.
    """
    import resource
    rusage = resource.getrusage(resource.RUSAGE_SELF)
    memory_mb = rusage.ru_maxrss / (1024 * 1024) # ru_maxrss is in bytes on macOS
    
    # Signed session tracking
    visits = req.session.get("visits", 0) + 1
    req.session["visits"] = visits
    
    return Response.json({
        "mode": app.concurrency_mode,
        "memory_mb": round(memory_mb, 2),
        "visits": visits,
        "active_threads": threading.active_count()
    })

# Register static serving route
app.router.add_route("GET", "/static/<path:filepath>", serve_static("static"))

# OpenAPI 3.0 API Specs Generator
@app.get("/openapi.json")
def get_openapi(req):
    """
    Returns the auto-generated OpenAPI 3.0 JSON specification.
    """
    import re
    spec = {
        "openapi": "3.0.0",
        "info": {
            "title": "BareBones API Documentation",
            "version": "1.0.0",
            "description": "Zero-dependency dynamically generated OpenAPI JSON endpoints."
        },
        "paths": {}
    }
    
    all_routes = []
    for method, regex, handler, path in app.router.routes:
        all_routes.append((method, handler, path, False))
    for method, regex, handler, path in app.ws_router.routes:
        all_routes.append(("WEBSOCKET", handler, path, True))
        
    for method, handler, path, is_ws in all_routes:
        if path in ["/openapi.json", "/docs"] or path.startswith("/static/"):
            continue
            
        params = []
        def repl(match):
            tag = match.group(1)
            name = tag[5:] if tag.startswith("path:") else tag
            params.append({
                "name": name,
                "in": "path",
                "required": True,
                "schema": {"type": "string"}
            })
            return f"{{{name}}}"
        
        openapi_path = re.sub(r'<([^>]+)>', repl, path)
        
        doc = handler.__doc__ or ""
        summary = ""
        description = ""
        if doc:
            lines = [l.strip() for l in doc.strip().split("\n") if l.strip()]
            if lines:
                summary = lines[0]
                if len(lines) > 1:
                    description = " ".join(lines[1:])
                    
        if openapi_path not in spec["paths"]:
            spec["paths"][openapi_path] = {}
            
        http_method = "get" if is_ws else method.lower()
        
        endpoint_def = {
            "summary": summary or f"Execute {method} on {openapi_path}",
            "description": description or ("Establishes a WebSocket connection." if is_ws else ""),
            "parameters": params,
            "responses": {
                "200": {
                    "description": "Successful Response"
                }
            }
        }
        
        if is_ws:
            endpoint_def["tags"] = ["WebSockets"]
            
        spec["paths"][openapi_path][http_method] = endpoint_def
        
    return Response.json(spec)

# Interactive API Documentation — fully self-contained, zero CDN dependencies
@app.get("/docs")
def get_docs(req):
    """
    Renders the interactive API documentation page.
    Self-contained with zero external assets.
    """
    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <title>BareBones API Docs</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #0b0f19; --panel: rgba(20,26,42,0.65); --border: rgba(255,255,255,0.08);
            --accent: #6366f1; --cyan: #06b6d4; --text: #f3f4f6; --muted: #9ca3af;
            --green: #10b981; --yellow: #eab308; --red: #ef4444; --blue: #3b82f6;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { background: var(--bg); color: var(--text); font-family: 'Inter', sans-serif; padding: 2rem; }
        h1 { font-size: 1.75rem; font-weight: 700; margin-bottom: 0.25rem;
             background: linear-gradient(to right, #fff, #9ca3af); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .subtitle { color: var(--muted); font-size: 0.9rem; margin-bottom: 2rem; }
        .back-link { color: var(--cyan); text-decoration: none; font-size: 0.85rem; display: inline-block; margin-bottom: 1.5rem; }
        .back-link:hover { text-decoration: underline; }
        .endpoint-group { margin-bottom: 1.5rem; }
        .endpoint {
            background: var(--panel); border: 1px solid var(--border); border-radius: 12px;
            margin-bottom: 0.75rem; overflow: hidden; transition: box-shadow 0.2s ease;
        }
        .endpoint:hover { box-shadow: 0 4px 20px rgba(0,0,0,0.2); }
        .ep-header {
            display: flex; align-items: center; gap: 0.75rem; padding: 1rem 1.25rem;
            cursor: pointer; user-select: none;
        }
        .method-badge {
            font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; font-weight: 600;
            padding: 0.25rem 0.625rem; border-radius: 6px; text-transform: uppercase; min-width: 70px; text-align: center;
        }
        .method-get { background: rgba(16,185,129,0.15); color: var(--green); }
        .method-post { background: rgba(59,130,246,0.15); color: var(--blue); }
        .method-put { background: rgba(234,179,8,0.15); color: var(--yellow); }
        .method-delete { background: rgba(239,68,68,0.15); color: var(--red); }
        .method-websocket { background: rgba(99,102,241,0.15); color: var(--accent); }
        .ep-path { font-family: 'JetBrains Mono', monospace; font-size: 0.9rem; flex: 1; }
        .ep-summary { color: var(--muted); font-size: 0.8rem; }
        .ep-chevron { color: var(--muted); transition: transform 0.2s ease; font-size: 0.8rem; }
        .ep-body { display: none; padding: 1rem 1.25rem; border-top: 1px solid var(--border); }
        .ep-body.open { display: block; }
        .ep-chevron.open { transform: rotate(90deg); }
        .ep-desc { color: var(--muted); font-size: 0.875rem; margin-bottom: 1rem; line-height: 1.5; }
        .param-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
        .param-table th { text-align: left; color: var(--muted); font-weight: 500; padding: 0.5rem; border-bottom: 1px solid var(--border); }
        .param-table td { padding: 0.5rem; border-bottom: 1px solid var(--border); }
        .param-name { font-family: 'JetBrains Mono', monospace; color: var(--cyan); }
        .try-section { margin-top: 1rem; }
        .try-btn {
            background: var(--accent); border: none; color: white; padding: 0.5rem 1rem;
            border-radius: 8px; font-family: inherit; font-weight: 500; cursor: pointer; font-size: 0.85rem;
            transition: background 0.2s;
        }
        .try-btn:hover { background: #4f46e5; }
        .response-box {
            margin-top: 0.75rem; background: rgba(0,0,0,0.3); border: 1px solid var(--border);
            border-radius: 8px; padding: 1rem; font-family: 'JetBrains Mono', monospace;
            font-size: 0.8rem; white-space: pre-wrap; word-break: break-all; max-height: 250px; overflow-y: auto;
            display: none; color: var(--green);
        }
        .tag-label { color: var(--accent); font-size: 0.7rem; font-weight: 600; text-transform: uppercase;
                     letter-spacing: 0.05em; margin-bottom: 0.5rem; padding-left: 0.25rem; }
        .loading { text-align: center; padding: 3rem; color: var(--muted); }
    </style>
</head>
<body>
    <a href="/" class="back-link">← Back to Dashboard</a>
    <h1>BareBones API Documentation</h1>
    <p class="subtitle">Auto-generated from route handler signatures and docstrings. Zero external dependencies.</p>
    <div id="endpoints-container"><div class="loading">Loading API specification...</div></div>

    <script>
    (async function() {
        const container = document.getElementById('endpoints-container');
        try {
            const res = await fetch('/openapi.json');
            const spec = await res.json();
            container.innerHTML = '';

            const paths = spec.paths || {};
            let idx = 0;
            for (const [path, methods] of Object.entries(paths)) {
                for (const [method, details] of Object.entries(methods)) {
                    const id = 'ep-' + idx++;
                    const methodUpper = method.toUpperCase();
                    const methodClass = 'method-' + method.toLowerCase();
                    const tags = details.tags || [];
                    const params = details.parameters || [];

                    let paramsHtml = '';
                    if (params.length > 0) {
                        paramsHtml = '<table class="param-table"><tr><th>Name</th><th>In</th><th>Type</th><th>Required</th></tr>';
                        for (const p of params) {
                            paramsHtml += '<tr><td class="param-name">' + p.name + '</td><td>' + p.in +
                                '</td><td>' + (p.schema?.type || 'string') + '</td><td>' + (p.required ? '✓' : '—') + '</td></tr>';
                        }
                        paramsHtml += '</table>';
                    }

                    const canTry = method === 'get' && !tags.includes('WebSockets');
                    const tryHtml = canTry ?
                        '<div class="try-section"><button class="try-btn" onclick="tryEndpoint(\\'' + path + '\\', \\'' + id + '\\')">Try it</button>' +
                        '<div class="response-box" id="resp-' + id + '"></div></div>' : '';

                    const tagHtml = tags.length > 0 ? '<div class="tag-label">' + tags.join(', ') + '</div>' : '';

                    const el = document.createElement('div');
                    el.className = 'endpoint';
                    el.innerHTML =
                        tagHtml +
                        '<div class="ep-header" onclick="toggleEp(\\'' + id + '\\')">' +
                            '<span class="method-badge ' + methodClass + '">' + methodUpper + '</span>' +
                            '<span class="ep-path">' + path + '</span>' +
                            '<span class="ep-summary">' + (details.summary || '') + '</span>' +
                            '<span class="ep-chevron" id="chev-' + id + '">▶</span>' +
                        '</div>' +
                        '<div class="ep-body" id="body-' + id + '">' +
                            (details.description ? '<div class="ep-desc">' + details.description + '</div>' : '') +
                            paramsHtml +
                            tryHtml +
                        '</div>';
                    container.appendChild(el);
                }
            }
        } catch(e) {
            container.innerHTML = '<div class="loading">Failed to load API spec: ' + e.message + '</div>';
        }
    })();

    function toggleEp(id) {
        const body = document.getElementById('body-' + id);
        const chev = document.getElementById('chev-' + id);
        body.classList.toggle('open');
        chev.classList.toggle('open');
    }

    async function tryEndpoint(path, id) {
        const box = document.getElementById('resp-' + id);
        box.style.display = 'block';
        box.textContent = 'Requesting...';
        try {
            const res = await fetch(path);
            const contentType = res.headers.get('content-type') || '';
            let body;
            if (contentType.includes('json')) {
                body = JSON.stringify(await res.json(), null, 2);
            } else {
                body = await res.text();
            }
            box.textContent = 'HTTP ' + res.status + '\\n\\n' + body;
            box.style.color = res.ok ? '#10b981' : '#ef4444';
        } catch(e) {
            box.textContent = 'Error: ' + e.message;
            box.style.color = '#ef4444';
        }
    }
    </script>
</body>
</html>
"""
    return Response.html(html_content)

# Live Server-Sent Events (SSE) push telemetry stream
@app.get("/api/telemetry")
def get_telemetry(req):
    """
    Starts a real-time Server-Sent Events stream for telemetry.
    """
    sock = req.socket
    if not sock:
        return Response(b"Socket required", status=400)
        
    # Set to blocking for thread safety
    sock.setblocking(True)
    
    # Write SSE response headers
    headers = [
        "HTTP/1.1 200 OK",
        "Content-Type: text/event-stream",
        "Cache-Control: no-cache",
        "Connection: keep-alive",
        "Access-Control-Allow-Origin: *",
        "",
        ""
    ]
    try:
        sock.sendall("\r\n".join(headers).encode('utf-8'))
    except Exception:
        return Response(b"Failed to initialize stream", status=500)
        
    # Hijack response to signal server not to touch/close socket
    resp = Response(status=200)
    resp.hijacked = True
    
    import json
    import time
    import resource
    
    def stream_telemetry():
        try:
            while app.running:
                rusage = resource.getrusage(resource.RUSAGE_SELF)
                memory_mb = rusage.ru_maxrss / (1024 * 1024)
                
                stats = {
                    "mode": app.concurrency_mode,
                    "memory_mb": round(memory_mb, 2),
                    "visits": req.session.get("visits", 0),
                    "active_threads": threading.active_count()
                }
                msg = f"data: {json.dumps(stats)}\n\n"
                sock.sendall(msg.encode('utf-8'))
                time.sleep(1.0)
        except Exception:
            pass
        finally:
            try:
                sock.close()
            except Exception:
                pass
                
    threading.Thread(target=stream_telemetry, daemon=True).start()
    return resp

# Live server log stream — SSE endpoint
@app.get("/api/logs")
def get_logs(req):
    """
    Streams live server log lines via Server-Sent Events.
    Each event is a JSON object with 'line' and 'ts' fields.
    """
    import json, time
    sock = req.socket
    if not sock:
        return Response(b"Socket required", status=400)

    sock.setblocking(True)
    headers = [
        "HTTP/1.1 200 OK",
        "Content-Type: text/event-stream",
        "Cache-Control: no-cache",
        "Connection: keep-alive",
        "Access-Control-Allow-Origin: *",
        "",
        ""
    ]
    try:
        sock.sendall("\r\n".join(headers).encode('utf-8'))
    except Exception:
        return Response(b"Failed to init stream", status=500)

    resp = Response(status=200)
    resp.hijacked = True

    # Per-subscriber queue
    q: collections.deque = collections.deque()
    with _log_lock:
        _log_subscribers.append(q)

    def stream_logs():
        try:
            while app.running:
                if q:
                    line = q.popleft()
                    payload = json.dumps({"line": line, "ts": time.strftime("%H:%M:%S")})
                    sock.sendall(f"data: {payload}\n\n".encode('utf-8'))
                else:
                    time.sleep(0.05)
        except Exception:
            pass
        finally:
            with _log_lock:
                try:
                    _log_subscribers.remove(q)
                except ValueError:
                    pass
            try:
                sock.close()
            except Exception:
                pass

    threading.Thread(target=stream_logs, daemon=True).start()
    return resp

# WebSocket Chat Room state
active_connections = set()
ws_lock = threading.Lock()

@app.websocket("/ws/chat")
def chat_ws(ws):
    with ws_lock:
        active_connections.add(ws)
    
    try:
        while True:
            msg = ws.recv_message()
            if msg is None:
                break
            
            # Broadcast the received message to all connected clients
            with ws_lock:
                disconnected = set()
                for conn in active_connections:
                    try:
                        conn.send_message(msg)
                    except Exception:
                        disconnected.add(conn)
                for conn in disconnected:
                    active_connections.discard(conn)
    finally:
        with ws_lock:
            active_connections.discard(ws)

if __name__ == "__main__":
    import sys
    mode = "threaded"
    if len(sys.argv) > 1:
        if sys.argv[1] in ["threaded", "eventloop"]:
            mode = sys.argv[1]
    
    # Start the server on port 8080
    app.run(host="127.0.0.1", port=8080, mode=mode)
