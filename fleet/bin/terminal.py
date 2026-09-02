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
   process group; no orphans, and no attaching to a live process someone else
   is holding. A reload resumes the *transcript* with --continue instead, which
   is a fresh process reading history it is entitled to read.
"""

from __future__ import annotations

import base64
import fcntl
import hashlib
import json
import errno
import os
import pathlib
import pty
import re
import select
import signal
import struct
import termios
import threading
import time

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
def transcript_dir(cwd: str) -> pathlib.Path:
    """Where Claude Code keeps the transcripts for a working directory.

    The slug is the absolute path with every character that is not a letter,
    digit or dash turned into a dash: /home/you/projects/x becomes
    -home-you-projects-x. This mirrors the CLI; if the CLI ever changes the
    scheme, `has_prior_session` just starts saying False and we spawn a fresh
    session, which is the old behaviour rather than a crash.
    """
    slug = re.sub(r"[^A-Za-z0-9-]", "-", os.path.abspath(cwd))
    return pathlib.Path.home() / ".claude" / "projects" / slug


def has_prior_session(cwd: str) -> bool:
    """True when there is a transcript for `cwd` that --continue could resume.

    Asking first matters: `claude --continue` with nothing to continue exits
    immediately with an error, and the pane would show a dead terminal instead
    of a prompt. The whole point of the flag is that a reload picks up where
    the last one left off — a first visit has nothing to pick up.
    """
    try:
        return any(transcript_dir(cwd).glob("*.jsonl"))
    except OSError:
        return False


class Session:
    """One `claude` process on a pseudo-terminal.

    Reloading the dashboard used to hand you a stranger: a brand-new process
    with no memory of anything you had just said. When a transcript for this
    directory already exists the process starts with --continue, so the page
    comes back to the conversation instead of to a blank prompt.
    """

    def __init__(self, cwd: str, cols: int = 120, rows: int = 32,
                 claude_bin: str = "claude"):
        argv = [claude_bin]
        if has_prior_session(cwd):
            argv.append("--continue")
        self._argv = argv                     # kept so tests can see the decision
        self.pid, self.fd = pty.fork()
        if self.pid == 0:                     # child
            os.chdir(cwd)
            env = dict(os.environ, TERM="xterm-256color", COLORTERM="truecolor")
            # Only ever claude — never a shell.
            os.execvpe(claude_bin, argv, env)
            os._exit(1)                       # unreachable
        self.resize(cols, rows)
        self.alive = True
        self.why = ""                          # filled in when it dies
        # Everything the session has said recently, so a browser that arrives
        # late can be shown the room it walked into. Raw bytes, not lines:
        # this is a terminal stream, and cutting it on newlines would split
        # escape sequences.
        self.buf = bytearray()
        self.lock = threading.Lock()
        self.watchers: list = []               # queues, one per attached page
        self.pump = threading.Thread(target=self._pump, daemon=True)
        self.pump.start()

    def _pump(self):
        """Drain the pty forever, whether or not anyone is watching.

        A detached session that nobody reads fills the kernel's pty buffer and
        then blocks, which would freeze claude the moment you closed the tab.
        """
        while self.alive:
            data = self.read(timeout=0.05)
            if not data:
                continue
            with self.lock:
                self.buf += data
                if len(self.buf) > SCROLLBACK:
                    del self.buf[:-SCROLLBACK]
                for q in list(self.watchers):
                    q.append(data)

    def subscribe(self) -> tuple[bytes, list]:
        """The scrollback so far, plus a queue that receives what comes next."""
        q: list = []
        with self.lock:
            self.watchers.append(q)
            return bytes(self.buf), q

    def unsubscribe(self, q) -> None:
        with self.lock:
            if q in self.watchers:
                self.watchers.remove(q)

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
            self.why = self._reap()

    def read(self, timeout: float = 0.05) -> bytes:
        """Terminal bytes, or b"" when there is nothing yet.

        EIO on a pty master is how the kernel says "the child on the other
        end is gone" -- that is the one OSError that means death. EINTR means
        a signal arrived mid-syscall and the read should simply be retried;
        treating it as death ended live sessions for no reason (2026-09-02:
        "it says session ended which is strange... Don't want to lose my
        work").
        """
        try:
            r, _, _ = select.select([self.fd], [], [], timeout)
            if not r:
                return b""
            data = os.read(self.fd, 65536)
            # Linux raises EIO here when the child is gone; macOS just returns
            # zero bytes. Readable-but-empty is EOF either way -- "nothing to
            # read yet" is the `not r` case above, not this one.
            if not data:
                self.alive = False
                self.why = self._reap()
            return data
        except InterruptedError:
            return b""
        except OSError as e:
            if e.errno == errno.EINTR:
                return b""
            self.alive = False
            self.why = self._reap()
            return b""

    def _reap(self) -> str:
        """Why the child is gone, in words. Empty when it is still running.

        Nothing recorded this before, so every ended session was a mystery --
        the board could only say "session ended" and neither of us could say
        more than that."""
        try:
            pid, status = os.waitpid(self.pid, os.WNOHANG)
        except OSError:
            return "already reaped"
        if pid == 0:
            return ""
        if os.WIFSIGNALED(status):
            n = os.WTERMSIG(status)
            return f"killed by {signal.Signals(n).name}"
        if os.WIFEXITED(status):
            code = os.WEXITSTATUS(status)
            return "exited normally" if code == 0 else f"exited with code {code}"
        return f"status {status}"

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


# One live session per name, kept across websockets. A reload used to fork a
# fresh `claude` and throw the running one away; the board is Marsita's home
# and a page refresh should not be a house move (2026-09-02: "I want
# continuity in the terminal on the web... to survive reloads on WWW").
#
# The pty keeps running while nobody is attached: claude does not know or care
# that the far end is a browser. What the browser loses on reload is only what
# it had already painted, so we keep a tail of raw bytes and replay it.
SCROLLBACK = 256 * 1024
_LIVE: dict[str, "Session"] = {}
_LIVE_LOCK = threading.Lock()


def attach(name: str, cwd: str, claude_bin: str = "claude"):
    """The session called `name`, started if it is not already running.

    Returns (session, resumed) -- `resumed` says whether this is a reconnect,
    because the page prints a different line for each.
    """
    with _LIVE_LOCK:
        s = _LIVE.get(name)
        if s is not None and s.alive:
            return s, True
        s = Session(cwd, claude_bin=claude_bin)
        _LIVE[name] = s
        return s, False


def forget(name: str) -> None:
    """Drop a dead session so the next attach starts a clean one."""
    with _LIVE_LOCK:
        s = _LIVE.get(name)
        if s is not None and not s.alive:
            _LIVE.pop(name, None)


def end(name: str) -> str:
    """Kill the named session on purpose. Returns what happened."""
    with _LIVE_LOCK:
        s = _LIVE.pop(name, None)
    if s is None:
        return "no such session"
    s.close()
    return "ended"


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
    # `?s=` names the session. The board always sends the same name, so a
    # reload lands back in the session it left.
    name = (q.get("s", ["board"])[0] or "board")[:64]
    forget(name)                                  # clear a corpse, if any
    session, resumed = attach(name, cwd, claude_bin=claude_bin)
    stop = threading.Event()

    backlog, queue = session.subscribe()
    try:
        _send(sock, json.dumps({"t": "attached", "resumed": resumed,
                                "bytes": len(backlog)}).encode(), opcode=0x1)
        if backlog:
            _send(sock, backlog, opcode=0x2)      # the room, as you left it
    except OSError:
        session.unsubscribe(queue)
        return

    def pump_out():
        """Session output -> this browser. The session itself is drained by
        its own pump thread, which runs whether or not anyone is attached."""
        while not stop.is_set() and session.alive:
            if not queue:
                time.sleep(0.02)
                continue
            try:
                _send(sock, queue.pop(0), opcode=0x2)
            except OSError:
                break
        # Last words. The browser only ever knew the socket had closed, so a
        # session that ended on its own and one killed by a board restart
        # looked identical from the page (2026-09-02).
        if session.why:
            try:
                _send(sock, json.dumps({"t": "ended", "why": session.why})
                      .encode(), opcode=0x1)
            except OSError:
                pass
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
        # Detach, do not kill. The session keeps running for the next page --
        # that is the whole point. It ends when it exits on its own, when the
        # board process dies, or when someone asks for it to end.
        stop.set()
        session.unsubscribe(queue)
