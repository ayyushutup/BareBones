import hashlib
import base64
import struct
from .router import Response

WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

def calculate_accept_key(sec_key):
    concat = sec_key + WEBSOCKET_GUID
    sha1 = hashlib.sha1(concat.encode('utf-8')).digest()
    return base64.b64encode(sha1).decode('utf-8')

class WebSocketConnection:
    def __init__(self, sock):
        self.sock = sock
        self.closed = False

    def send_message(self, message, opcode=1):
        """
        Sends a WebSocket frame to the client.
        opcode 1 is Text, opcode 2 is Binary.
        """
        if self.closed:
            return
        
        payload = message.encode('utf-8') if isinstance(message, str) else message
        length = len(payload)
        
        # Byte 1: FIN = 1, RSV = 0, Opcode
        header = bytearray([0x80 | opcode])
        
        # Byte 2: Mask = 0 (server to client must be unmasked), Payload length
        if length < 126:
            header.append(length)
        elif length < 65536:
            header.append(126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(127)
            header.extend(struct.pack("!Q", length))
            
        try:
            self.sock.sendall(header + payload)
        except Exception:
            self.closed = True

    def recv_message(self):
        """
        Reads and decodes a single frame from the client.
        Blocks until a complete message is received, or connection closes.
        """
        if self.closed:
            return None
            
        try:
            # Read first 2 bytes: FIN/Opcode (1B), Mask/Len (1B)
            header = self._read_exact(2)
            if not header:
                return None
                
            fin = (header[0] & 0x80) != 0
            opcode = header[0] & 0x0f
            
            masked = (header[1] & 0x80) != 0
            payload_len = header[1] & 0x7f
            
            if payload_len == 126:
                len_bytes = self._read_exact(2)
                if not len_bytes:
                    return None
                payload_len = struct.unpack("!H", len_bytes)[0]
            elif payload_len == 127:
                len_bytes = self._read_exact(8)
                if not len_bytes:
                    return None
                payload_len = struct.unpack("!Q", len_bytes)[0]
                
            masking_key = b""
            if masked:
                masking_key = self._read_exact(4)
                if not masking_key:
                    return None
                    
            payload = self._read_exact(payload_len)
            if payload is None:
                return None
                
            if masked:
                # Unmask payload
                payload = bytes(b ^ masking_key[i % 4] for i, b in enumerate(payload))
                
            if opcode == 8: # Connection Close
                self.close()
                return None
            elif opcode == 9: # Ping
                # Respond with Pong
                self.send_message(payload, opcode=10)
                return self.recv_message() # read next message
            elif opcode == 10: # Pong
                return self.recv_message() # read next message
            elif opcode == 1: # Text
                return payload.decode('utf-8')
            elif opcode == 2: # Binary
                return payload
            else:
                return payload # Fallback
                
        except Exception:
            self.closed = True
            return None

    def _read_exact(self, n):
        data = bytearray()
        while len(data) < n:
            packet = self.sock.recv(n - len(data))
            if not packet:
                return None
            data.extend(packet)
        return bytes(data)

    def close(self):
        if not self.closed:
            self.closed = True
            try:
                # Send close frame
                self.sock.sendall(bytearray([0x80 | 8, 0]))
                self.sock.close()
            except Exception:
                pass
