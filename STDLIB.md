# Standard Library Substitution Log (STDLIB.md)

This log documents the **11 substitutions** made to replace common third-party production packages with Python's built-in standard library components, avoiding dependency bloat and maintaining a pure zero-dependency codebase.

| # | Third-Party Package / Tool | Standard Library Replacement | Description & Usage | BareBones Implementation File |
|---|----------------------------|-------------------------------|---------------------|-------------------------------|
| 1 | **Flask** / **FastAPI** / **Express** | `socket` | Low-level network socket interface to bind, listen, and accept TCP connections. | [server.py](file:///Users/ayushrthakur/Documents/BareBones/barebones/server.py) |
| 2 | **werkzeug.routing** / **path-to-regexp** | `re` | Parses dynamic path variables and compiles pattern strings into matching regular expressions. | [router.py](file:///Users/ayushrthakur/Documents/BareBones/barebones/router.py) |
| 3 | **body-parser** | `json`, `urllib.parse` | Extracts JSON bodies (`json.loads`) and decodes URL-encoded form submissions (`parse_qsl`). | [middleware.py](file:///Users/ayushrthakur/Documents/BareBones/barebones/middleware.py) |
| 4 | **serve-static** / **sendfile** | `os.path`, `mimetypes` | Resolves absolute file paths on disk, blocks path traversal attacks, and determines correct HTTP MIME types. | [static.py](file:///Users/ayushrthakur/Documents/BareBones/barebones/static.py) |
| 5 | **range-parser** | Custom String Splicing | Parses HTTP `Range` headers to read and serve partial file chunks for instant video seek/scrubbing. | [static.py](file:///Users/ayushrthakur/Documents/BareBones/barebones/static.py) |
| 6 | **itsdangerous** / **cookie-session** | `hmac`, `hashlib`, `base64` | Serializes cookie dicts into Base64 JSON and signs them using HMAC-SHA256 with a secret key. | [sessions.py](file:///Users/ayushrthakur/Documents/BareBones/barebones/sessions.py) |
| 7 | **ws** / **websockets** | `hashlib`, `base64`, `struct` | Handshakes with client key, packs and unpacks raw RFC 6455 data frames with bitwise masks. | [websocket.py](file:///Users/ayushrthakur/Documents/BareBones/barebones/websocket.py) |
| 8 | **compression** / **gzip** | `gzip` | Compresses outgoing response strings dynamically if client indicates `Accept-Encoding: gzip`. | [middleware.py](file:///Users/ayushrthakur/Documents/BareBones/barebones/middleware.py) |
| 9 | **morgan** / **winston** | `time` | Calculates elapsed HTTP processing milliseconds and prints standard dev logs to standard out. | [middleware.py](file:///Users/ayushrthakur/Documents/BareBones/barebones/middleware.py) |
| 10| **cors** | Custom HTTP headers | Validates preflight OPTIONS requests and sets `Access-Control-*` response headers. | [middleware.py](file:///Users/ayushrthakur/Documents/BareBones/barebones/middleware.py) |
| 11| **pytest** | `unittest` | Organizes assertion suites, runs integration/unit cases, and executes thread load benchmarks. | [test_framework.py](file:///Users/ayushrthakur/Documents/BareBones/tests/test_framework.py) / [test_concurrency.py](file:///Users/ayushrthakur/Documents/BareBones/tests/test_concurrency.py) |
