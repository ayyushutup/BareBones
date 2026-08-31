# BareBones: A Zero-Dependency HTTP Web Framework

Built entirely on Python's Standard Library — no third-party packages, no installs.

**Track**: C — Web & Network  
**Language**: Python (Standard Library Only)  
**Category**: 72-Hour Zero-Dependency Hackathon  

---

## The Problem

Building a web server or API in Python almost always means reaching for a third-party framework such as Flask, FastAPI, or Django — along with everything those frameworks depend on. Every one of those dependencies is code the team did not write, must trust, and must keep updated.

Python’s standard library already ships with the low-level building blocks needed to handle networking, parsing, hashing, and file serving. Those pieces are simply never assembled into something a developer can use directly.

**BareBones** proves that a real, working, concurrent web framework can be built using only Python’s standard library — with zero third-party runtime dependencies.

---

## Why This Matters

* **No supply-chain risk** — zero third-party code means zero third-party attack surface.
* **No dependency rot** — nothing to install, nothing to break when a package updates or is deprecated.
* **Instant deployment** — runs anywhere Python runs, with no virtual environment or package manager required.
* **Educational transparency** — exposes what frameworks like Flask are actually doing under the hood.

---

## Architecture Overview

BareBones is organized into independent layers, each responsible for one concern, mirroring the structure of production frameworks while staying entirely within the standard library.

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
                           │              ──> [websocket.py (RFC 6455 Frames)]
                           ▼
                [app.py (Web Application)]
```

### Components

* **[server.py](file:///Users/ayushrthakur/Documents/BareBones/barebones/server.py)** — Accepts raw TCP connections and manages concurrency (thread-per-connection or selectors event loop).
* **[router.py](file:///Users/ayushrthakur/Documents/BareBones/barebones/router.py)** — Matches incoming request paths and methods to handler functions, including dynamic path parameters.
* **[middleware.py](file:///Users/ayushrthakur/Documents/BareBones/barebones/middleware.py)** — A chainable pipeline for logging, authentication, CORS, and body parsing.
* **[static.py](file:///Users/ayushrthakur/Documents/BareBones/barebones/static.py)** — Serves files from disk with correct MIME types and byte-range support for streaming.
* **[websocket.py](file:///Users/ayushrthakur/Documents/BareBones/barebones/websocket.py)** — Manages full-duplex WebSocket frames, bitmasking, and handshakes directly.
* **[sessions.py](file:///Users/ayushrthakur/Documents/BareBones/barebones/sessions.py)** — Encrypts and validates cookie states via HMAC-SHA256.

---

## Feature Mapping (Standard Library Only)

| Feature | Standard Library Used | Purpose |
|---------|-----------------------|---------|
| **Concurrent connection handling** | `socket`, `selectors` / `threading` | Non-blocking selectors loop or Thread-per-connection |
| **Routing with path parameters** | `re` | Regex compilation and single-pass dynamic parameter extraction |
| **Middleware chain (logging, auth, CORS)** | Custom logic | Onion execution model wrapping request and response |
| **JSON request/response handling** | `json` | Encoding/decoding payloads |
| **Static file serving with MIME types** | `mimetypes` | Resolving content headers dynamically |
| **Byte-range file streaming** | `os`, `socket` | HTTP 206 partial file serving for audio/video seek |
| **WebSocket handshake (live chat)** | `hashlib`, `base64`, `struct` | Hand-rolled RFC 6455 protocol framing |
| **Signed cookies / sessions** | `hmac`, `hashlib` | SHA256 cookie signing for tamper-detection |
| **Response compression** | `gzip` / `zlib` | Automatic body compression middleware |

---

## Concurrency Models

BareBones supports two interchangeable concurrency models:

| Mode | Approach | Trade-off |
|------|----------|-----------|
| **Threaded** | One thread per connection (`threading`) | Simple to reason about; fine for I/O-bound workloads |
| **Event Loop** | Single thread, `selectors.DefaultSelector()` | Higher throughput; synchronous blocking calls halt the loop |

> [!TIP]
> **Dynamic Hot-Swap**: You can toggle between these modes at runtime directly from the UI dashboard. The framework re-binds the socket and reloads the engine dynamically.

---

## Getting Started

### 1. Run the Server
Launch the application:
```bash
python3 app.py
```
By default, the server binds to `http://127.0.0.1:8080/`.

To start the server in event-loop mode directly from the command line:
```bash
python3 app.py eventloop
```

### 2. Run the Dependency Verification Tool
Verify that zero third-party modules are loaded:
```bash
python3 verify_deps.py
```

### 3. Run the Automated Tests
Execute the comprehensive unit and concurrency integration suites:
```bash
# Run unit tests
python3 -m unittest tests/test_framework.py

# Run concurrency stress tests (15 concurrent client requests in both modes)
python3 -m unittest tests/test_concurrency.py
```

### 4. Build the Single-File Bundle
To bundle the entire core framework into a single, self-contained, and byte-identical module, run:
```bash
python3 build.py
```
This outputs `barebones_single.py`, which is 100% reproducible on repeat runs.

---

## Deliverables Status

- [x] **Public GitHub repository** — `https://github.com/ayyushutup/BareBones.git`
- [x] **One-command build and run instructions** — Documented in README
- [x] **Empty dependency manifest** — `requirements.txt` is empty
- [x] **Dependency proof** — Checked via `verify_deps.py` AST scanner
- [x] **README.md** — Problem statement, architecture, design trade-offs
- [x] **STDLIB.md** — Package-to-standard-library substitution log
- [x] **Automated tests** — Edge cases and concurrency verified
