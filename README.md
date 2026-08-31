# BareBones: A Zero-Dependency HTTP Web Framework

BareBones is a lightweight, concurrent HTTP web server and framework built entirely from Python's standard library. It requires **zero third-party packages, zero installations, and zero virtual environments** to run.

Designed as a Flask-style replacement for low-latency web environments, BareBones exposes routing decorators, cookie signing, gzip compression, non-blocking selectors, and WebSockets directly over raw TCP sockets.

---

## Architecture Overview

BareBones handles requests through a series of decoupled layers:

```
[Client Socket] ──> [server.py (Listen Loop)]
                           │
                           ▼
                    [parser_request]
                           │
                           ▼
               [middleware.py (Onion Chain)]
                    ├── json_parser
                    ├── form_parser
                    ├── session_middleware
                    └── gzip_middleware
                           │
                           ▼
                 [router.py (Regex match)] ──> [static.py (MIME / Byte-range)]
                           │               ──> [websocket.py (RFC 6455 Frames)]
                           ▼
                  [handlers.py / app.py]
```

1. **`server.py`**: Manages socket bindings and handles incoming connections using one of two concurrency models.
2. **`router.py`**: Matches incoming request paths (supporting regex groups and wildcard path parameters) to target route handlers.
3. **`middleware.py`**: Intercepts requests/responses in an onion execution model (JSON parsing, CORS preflights, Gzip compression).
4. **`sessions.py`**: Encrypts and validates cookie states via HMAC-SHA256.
5. **`static.py`**: Delivers static files from disk and supports HTTP 206 Partial Content range seeking.
6. **`websocket.py`**: Manages full-duplex WebSocket frames, bitmasking, and close codes.

---

## Concurrency Models

BareBones supports two interchangeable models for handling concurrent connections:

*   **Threaded Mode (Default)**: Spawns a dedicated thread (`threading.Thread`) for each connection. This is robust, simple, and excels at handling blocking I/O (such as disk operations and long-lived WebSocket connections).
*   **Event Loop Mode**: Employs a single thread using `selectors.DefaultSelector` to monitor non-blocking sockets. This provides higher throughput for fast, non-blocking HTTP endpoints, although CPU-bound or synchronous blocking functions inside handlers will halt the loop.

*Live Toggle*: The frontend dashboard includes a control panel that lets you switch between these modes dynamically, reloading the listening socket on the fly.

---

## Getting Started

### 1. Run the Server
Launch the application:
```bash
python3 app.py
```
By default, the server binds to `http://127.0.0.1:8080/`. Open this address in your web browser.

To start the server in event-loop mode directly from the command line:
```bash
python3 app.py eventloop
```

### 2. Run the Bundle Build Script
To bundle the entire core framework into a single, self-contained, and byte-identical module, run:
```bash
python3 build.py
```
This outputs `barebones_single.py`, which is 100% reproducible on repeat runs.

### 3. Run the Automated Tests
Execute the comprehensive unit and concurrency integration suites:
```bash
# Run unit tests (routing, sessions, gzip, WS)
python3 -m unittest tests/test_framework.py

# Run concurrency tests (15 concurrent stress requests in both modes)
python3 -m unittest tests/test_concurrency.py
```
