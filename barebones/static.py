import os
import mimetypes
from .router import Response

def parse_range_header(range_header, file_size):
    """
    Parses Range headers like 'bytes=0-1024' or 'bytes=500-'.
    Returns (start, end) or None.
    """
    if not range_header or not range_header.startswith("bytes="):
        return None
    val = range_header.split("bytes=", 1)[1].strip()
    if not val:
        return None
        
    # We only handle single range requests
    if "," in val:
        val = val.split(",")[0].strip()
        
    try:
        if val.startswith("-"):
            suffix_len = int(val[1:])
            start = max(0, file_size - suffix_len)
            end = file_size - 1
        elif val.endswith("-"):
            start = int(val[:-1])
            end = file_size - 1
        else:
            parts = val.split("-")
            start = int(parts[0])
            end = int(parts[1])
            
        if start >= file_size or start > end:
            return None
        end = min(end, file_size - 1)
        return start, end
    except ValueError:
        return None

def serve_static(static_dir):
    """
    Returns a route handler that serves files from static_dir.
    Matches route param 'filepath'.
    """
    def handler(req, **kwargs):
        filepath = kwargs.get("filepath", "")
        # Sanitize path to prevent directory traversal
        normalized = os.path.normpath(filepath)
        if normalized.startswith("..") or os.path.isabs(normalized):
            return Response(b"Forbidden", status=403)
            
        full_path = os.path.join(static_dir, normalized)
        if not os.path.exists(full_path) or os.path.isdir(full_path):
            return Response(b"Not Found", status=404)
            
        mime_type, _ = mimetypes.guess_type(full_path)
        if not mime_type:
            mime_type = "application/octet-stream"
            
        file_size = os.path.getsize(full_path)
        range_header = req.headers.get("range", "")
        parsed_range = parse_range_header(range_header, file_size)
        
        if parsed_range:
            start, end = parsed_range
            content_length = end - start + 1
            resp = Response(status=206)
            resp.file_path = full_path
            resp.file_offset = start
            resp.file_length = content_length
            resp.set_header("Content-Type", mime_type)
            resp.set_header("Content-Length", str(content_length))
            resp.set_header("Content-Range", f"bytes {start}-{end}/{file_size}")
            resp.set_header("Accept-Ranges", "bytes")
            return resp
        else:
            resp = Response(status=200)
            resp.file_path = full_path
            resp.file_offset = 0
            resp.file_length = file_size
            resp.set_header("Content-Type", mime_type)
            resp.set_header("Content-Length", str(file_size))
            resp.set_header("Accept-Ranges", "bytes")
            return resp
            
    return handler
