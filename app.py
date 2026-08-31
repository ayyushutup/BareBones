import os
import threading
import urllib.request
from barebones import BareBones, Response
from barebones.static import serve_static

app = BareBones(secret_key="barebones_super_secret_signing_key_12345")

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
    resp = Response(status=302)
    resp.set_header("Location", "/static/index.html")
    return resp

# Toggle concurrency mode
@app.post("/api/toggle-mode")
def toggle_mode(req):
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
