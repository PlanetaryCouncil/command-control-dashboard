#!/usr/bin/env python3
"""A real Claude terminal in the browser, over a pseudo-terminal and a WebSocket.

Not a re-implementation of the command line — the actual `claude` process,
attached to a pseudo-terminal, with its bytes piped to the page. Permission
prompts, plan mode, slash commands and interrupts all work because it is the
same program, unchanged.

Defences, in order of how much they matter:

1. **It spawns `claude`, never a shell.** The socket cannot run arbitrary
   commands. Claude can, of course — but a page that reaches this endpoint gets
   an agent with its own guardrails, not a bare `sh`.
2. **A token minted per server start.** Required to open the socket, and a
   cross-origin page cannot read it.
3. **Origin is checked.** A WebSocket handshake from anywhere but this server's
   own pages is refused outright — browsers send `Origin` on WebSocket upgrades
   and do not let scripts forge it.
4. **Loopback only**, enforced here as well as at the bind.
5. **One session per socket, killed on disconnect.** Closing the tab kills the
   process group; no orphans, no reattaching to someone else's session.
"""

from __future__ import annotations

import base64
import fcntl
import hashlib
import json
import os
import pty
import select
import signal
import struct
import termios
import threading

WS_MAGIC = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
MAX_FRAME = 1 << 20          # 1 MB — a paste, not a file upload


# --------------------------------------------------------------------- framing
def _accept_key(client_key: str) -> str:
    digest = hashlib.sha1((client_key + WS_MAGIC).encode()).digest()
    return base64.b64encode(digest).decode()


def _send(sock, payload: bytes, opcode: int = 0x1) -> None:
    """Server frames are never masked."""
    header = bytearray([0x80 | opcode])
    n = len(payload)
    if n < 126:
        header.append(n)
    elif n < (1 << 16):
        header.append(126)
        header += struct.pack(">H", n)
    else:
        header.append(127)
        header += struct.pack(">Q", n)
    sock.sendall(bytes(header) + payload)


def _recv_exact(sock, n: int) -> bytes | None:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return buf


def _recv_frame(sock):
    """Returns (opcode, payload) or None when the peer goes away."""
    head = _recv_exact(sock, 2)
    if not head:
        return None
    opcode = head[0] & 0x0F
    masked = head[1] & 0x80
    length = head[1] & 0x7F
    if length == 126:
        ext = _recv_exact(sock, 2)
        if not ext:
            return None
        length = struct.unpack(">H", ext)[0]
    elif length == 127:
        ext = _recv_exact(sock, 8)
        if not ext:
            return None
        length = struct.unpack(">Q", ext)[0]
    if length > MAX_FRAME:
        return None
    mask = _recv_exact(sock, 4) if masked else b""
    if masked and mask is None:
        return None
    data = _recv_exact(sock, length) if length else b""
    if data is None:
        return None
    if masked:
        data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
    return opcode, data


# ----------------------------------------------------------------- the session
class Session:
    """One `claude` process on a pseudo-terminal."""

    def __init__(self, cwd: str, cols: int = 120, rows: int = 32,
                 claude_bin: str = "claude"):
        self.pid, self.fd = pty.fork()
        if self.pid == 0:                     # child
            os.chdir(cwd)
            env = dict(os.environ, TERM="xterm-256color", COLORTERM="truecolor")
            # Only ever claude — never a shell.
            os.execvpe(claude_bin, [claude_bin], env)
            os._exit(1)                       # unreachable
        self.resize(cols, rows)
        self.alive = True

    def resize(self, cols: int, rows: int) -> None:
        try:
            fcntl.ioctl(self.fd, termios.TIOCSWINSZ,
                        struct.pack("HHHH", rows, cols, 0, 0))
        except OSError:
            pass

    def write(self, data: bytes) -> None:
        try:
            os.write(self.fd, data)
        except OSError:
            self.alive = False

    def read(self, timeout: float = 0.05) -> bytes:
        try:
            r, _, _ = select.select([self.fd], [], [], timeout)
            if not r:
                return b""
            return os.read(self.fd, 65536)
        except OSError:
            self.alive = False
            return b""

    def close(self) -> None:
        self.alive = False
        # Kill the whole group: claude spawns children of its own.
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(os.getpgid(self.pid), sig)
            except OSError:
                break
        try:
            os.close(self.fd)
        except OSError:
            pass
        try:
            os.waitpid(self.pid, os.WNOHANG)
        except OSError:
            pass


def serve_socket(handler, cwd: str, token: str, claude_bin: str = "claude") -> None:
    """Upgrade an HTTP request to a WebSocket and bridge it to a Claude session.

    `handler` is a BaseHTTPRequestHandler mid-request.
    """
    from urllib.parse import parse_qs, urlparse

    q = parse_qs(urlparse(handler.path).query)
    if q.get("token", [""])[0] != token:
        handler.send_error(403, "bad token")
        return

    # A browser will not let a script forge Origin, so this is a real check —
    # but only if it is required. Skipping it when the header is absent meant
    # any non-browser client could pass by simply not sending one, which is the
    # easier thing to do, not the harder. The socket's other end is a PTY
    # running claude at the repo root, so it fails closed.
    origin = handler.headers.get("Origin", "")
    if not origin.startswith(("http://127.0.0.1", "http://localhost")):
        handler.send_error(403, "bad origin")
        return

    key = handler.headers.get("Sec-WebSocket-Key")
    if not key or handler.headers.get("Upgrade", "").lower() != "websocket":
        handler.send_error(400, "expected a websocket upgrade")
        return

    handler.send_response(101, "Switching Protocols")
    handler.send_header("Upgrade", "websocket")
    handler.send_header("Connection", "Upgrade")
    handler.send_header("Sec-WebSocket-Accept", _accept_key(key))
    handler.end_headers()

    sock = handler.connection
    session = Session(cwd, claude_bin=claude_bin)
    stop = threading.Event()

    def pump_out():
        """Terminal output -> browser."""
        while not stop.is_set() and session.alive:
            data = session.read()
            if data:
                try:
                    _send(sock, data, opcode=0x2)   # binary: raw terminal bytes
                except OSError:
                    break
        stop.set()

    t = threading.Thread(target=pump_out, daemon=True)
    t.start()

    try:
        while not stop.is_set():
            frame = _recv_frame(sock)
            if frame is None:
                break
            opcode, data = frame
            if opcode == 0x8:                      # close
                break
            if opcode == 0x9:                      # ping
                _send(sock, data, opcode=0xA)
                continue
            if opcode == 0x1:                      # text: a control message
                try:
                    msg = json.loads(data.decode())
                except ValueError:
                    continue
                if msg.get("t") == "resize":
                    session.resize(int(msg.get("cols", 120)), int(msg.get("rows", 32)))
                elif msg.get("t") == "input":
                    session.write(str(msg.get("d", "")).encode())
            elif opcode == 0x2:                    # binary: keystrokes
                session.write(data)
    except OSError:
        pass
    finally:
        stop.set()
        session.close()
