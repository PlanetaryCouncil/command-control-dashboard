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
import shutil
import signal
import struct
import subprocess
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


def tmux_bin() -> str:
    """tmux, if this machine has it. Empty string otherwise."""
    return shutil.which("tmux") or ""


def session_argv(cwd: str, claude_bin: str, name: str) -> list[str]:
    """What to exec so the session outlives the thing that started it.

    The board used to fork `claude` directly, which made the board process
    its parent -- so every restart of the board killed the session. Reloads
    survived (the pty outlives one websocket) but restarts did not, and the
    board gets restarted every time it is improved: twelve times on
    2026-09-02 alone, each one landing on whatever Marsita was mid-way
    through. "the board terminal needs to stay alive ---> that's the point".

    So tmux owns the process instead and the board is only a viewer.
    `new-session -A` attaches to the session if it exists and creates it
    otherwise, which is the entire mechanism: the first connection starts
    claude, every later one -- after a reload, after a restart, from a real
    terminal with `tmux attach -t board` -- joins the same running session.
    tmux redraws the screen on attach, so the scrollback comes back too.

    Without tmux installed it behaves exactly as before, because a board that
    refuses to open a terminal is worse than one whose terminal is fragile.
    """
    inner = [claude_bin]
    if has_prior_session(cwd):
        inner.append("--continue")
    tmux = tmux_bin()
    if not tmux:
        return inner
    # -A: attach if it exists, create if not. -2: force 256 colour, since the
    # environment tmux inherits from a daemon has no opinion about TERM.
    # `--` so a claude flag is never read as one of tmux's.
    return [tmux, "-2", "new-session", "-A", "-s", name, "--", *inner]


class Session:
    """One `claude` process on a pseudo-terminal.

    Reloading the dashboard used to hand you a stranger: a brand-new process
    with no memory of anything you had just said. When a transcript for this
    directory already exists the process starts with --continue, so the page
    comes back to the conversation instead of to a blank prompt.
    """

    def __init__(self, cwd: str, cols: int = 120, rows: int = 32,
                 claude_bin: str = "claude", name: str = "board"):
        argv = session_argv(cwd, claude_bin, name)
        self._argv = argv                     # kept so tests can see the decision
        self.pid, self.fd = pty.fork()
        if self.pid == 0:                     # child
            os.chdir(cwd)
            env = dict(os.environ, TERM="xterm-256color", COLORTERM="truecolor")
            # The board sets TRUST_PROXY=1 for itself, correctly: it sits
            # behind the Tailscale funnel and must read the caller from
            # X-Forwarded-For. This terminal does not sit behind anything.
            #
            # Inheriting it leaked the board's networking assumption into
            # every shell in the session -- and into every test run from one.
            # The TestClient sends no such header, so `steering_caller`
            # returned "" and 28 local-only writes were refused as strangers.
            # The suite passed outside this terminal and failed inside it,
            # which makes a test run worth nothing (2026-09-04).
            #
            # tmux copies its environment into a server that outlives every
            # pane, so this has to be dropped before the fork, not after.
            env.pop("TRUST_PROXY", None)
            # Only ever claude, or tmux running claude — never a shell.
            os.execvpe(argv[0], argv, env)
            os._exit(1)                       # unreachable
        self.resize(cols, rows)
        self.alive = True
        self.why = ""                          # filled in when it dies
        # Whether tmux owns the screen. When it does, tmux can be asked to
        # repaint it, which is a far better answer on reattach than replaying
        # our own byte log -- see `repaint`.
        self.tmux_name = name if tmux_bin() else ""
        if self.tmux_name:
            # tmux sizes a window to its SMALLEST client by default. With two
            # attached -- the board pane and `tmux attach -t board` on the
            # laptop -- the smaller one clamped the other, so the browser drew
            # a status bar two-thirds up the pane and dead black below it.
            # Marsita, 2026-09-04: "loads of empty space... claude should take
            # more."
            #
            # `largest`, not `latest`: latest follows the most recently ACTIVE
            # client, and this pane is read-only, so it is never the active one
            # and would never get the window. Under `largest` the big viewer
            # sets the size and a smaller client scrolls around it, which is
            # the right way round -- the empty space was the browser being
            # given less than it had room for.
            # In a thread, NEVER inline. Two `subprocess.run`s here delay the
            # end of __init__ by seconds, and a session created moments after
            # the previous one was killed then attaches to the dying session
            # instead of a new one -- `test_a_late_arrival_is_shown_what_it
            # _missed` went from green to reliably red on that alone. These
            # options are cosmetic sizing; nothing should wait on them.
            threading.Thread(target=self._tmux_setup, daemon=True).start()
        # Everything the session has said recently, so a browser that arrives
        # late can be shown the room it walked into. Raw bytes, not lines:
        # this is a terminal stream, and cutting it on newlines would split
        # escape sequences.
        self.buf = bytearray()
        self.lock = threading.Lock()
        self.watchers: list = []               # queues, one per attached page
        # Every attached page's window size, keyed per socket. One pty is
        # shared by all of them, so without this the last tab to resize set
        # the width for everyone and two differently-sized tabs fought over
        # it -- whichever you touched most recently won and the other drew at
        # a width it did not have.
        self.sizes: dict[int, tuple[int, int]] = {}
        self.pump = threading.Thread(target=self._pump, daemon=True)
        self.pump.start()

    def _tmux_setup(self) -> None:
        """Size options, applied once the session is actually up."""
        self.tmux_opt("window-size", "largest")
        self.tmux_opt("aggressive-resize", "on", window=True)

    def tmux_opt(self, name: str, value: str, *, window: bool = False) -> None:
        """Set one tmux option on this session, best effort.

        Best effort on purpose: the session may still be starting up when this
        runs, and an option that failed to apply is a slightly wrong window
        size, not a reason to refuse to open a terminal.
        """
        tmux = tmux_bin()
        if not tmux:
            return
        flags = ["-w"] if window else []
        try:
            subprocess.run([tmux, "set-option", *flags, "-t", self.tmux_name,
                            name, value], capture_output=True, timeout=5)
        except (OSError, subprocess.SubprocessError):
            pass

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

    def repaint(self) -> bool:
        """Ask tmux to redraw the current screen. True if it was asked.

        `self.buf` is a raw byte log, not a snapshot: it holds every redraw
        the session has ever emitted. Replaying it does not restore the
        screen, it re-renders the whole history -- so a reattached page showed
        the same conversation stacked several times over, two status bars and
        all, and live output then landed somewhere the reader was not looking
        (2026-09-03: "I need to reload the browser tab with every message").

        tmux already holds the one true screen. Ask it, and get exactly one.
        """
        if not self.tmux_name:
            return False
        try:
            subprocess.run([tmux_bin(), "refresh-client", "-t",
                            self.tmux_name], capture_output=True, timeout=5)
        except (OSError, subprocess.SubprocessError):
            return False
        return True

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

    def set_size(self, key: int, cols: int, rows: int) -> None:
        """Record one page's size and fit the pty to the smallest of them.

        The same rule tmux uses for several attached clients, and for the same
        reason: a screen drawn wider than a viewer's window wraps into
        nonsense there, while one drawn narrower merely leaves a margin. The
        smallest window is the only size every viewer can actually display.
        """
        with self.lock:
            self.sizes[key] = (max(int(cols), 2), max(int(rows), 2))
            cols = min(c for c, _ in self.sizes.values())
            rows = min(r for _, r in self.sizes.values())
        self.resize(cols, rows)

    def drop_size(self, key: int) -> None:
        """Forget a page that has gone, and give the room back to the rest.

        Without this a closed tab kept its vote forever: shut a narrow one and
        every remaining tab stayed cramped to a window nobody was looking at.
        """
        with self.lock:
            self.sizes.pop(key, None)
            if not self.sizes:
                return                         # nobody left; keep the last fit
            cols = min(c for c, _ in self.sizes.values())
            rows = min(r for _, r in self.sizes.values())
        self.resize(cols, rows)

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


def tmux_has(name: str) -> bool:
    """Is there a tmux session by this name, right now?

    Asked rather than remembered: after the board restarts, `_LIVE` is empty
    but the tmux session is still there, and reporting that reconnect as a
    fresh start would be a lie about the one thing this was built to fix.
    """
    tmux = tmux_bin()
    if not tmux:
        return False
    try:
        return subprocess.run([tmux, "has-session", "-t", name],
                              capture_output=True, timeout=5).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def attach(name: str, cwd: str, claude_bin: str = "claude"):
    """The session called `name`, started if it is not already running.

    Returns (session, resumed) -- `resumed` says whether this is a reconnect,
    because the page prints a different line for each.
    """
    with _LIVE_LOCK:
        s = _LIVE.get(name)
        if s is not None and s.alive:
            return s, True
        # A tmux session that outlived the board is still a resume, even
        # though this process has never seen it before.
        resumed = tmux_has(name)
        s = Session(cwd, claude_bin=claude_bin, name=name)
        _LIVE[name] = s
        return s, resumed


def forget(name: str) -> None:
    """Drop a dead session so the next attach starts a clean one."""
    with _LIVE_LOCK:
        s = _LIVE.get(name)
        if s is not None and not s.alive:
            _LIVE.pop(name, None)


def end(name: str) -> str:
    """Kill the named session on purpose. Returns what happened.

    Both halves: the local viewer AND the tmux session behind it. Closing
    only the viewer is what every other path does, deliberately -- this is
    the one place that means it.
    """
    with _LIVE_LOCK:
        s = _LIVE.pop(name, None)
    if s is not None:
        s.close()
    tmux = tmux_bin()
    if tmux:
        try:
            subprocess.run([tmux, "kill-session", "-t", name],
                           capture_output=True, timeout=5)
        except (OSError, subprocess.SubprocessError):
            pass
    return "ended" if (s is not None or tmux) else "no such session"


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
    # Two ways to show an arriving page the room it walked into, and only one
    # of them is right when tmux is behind the session.
    #
    # The byte log is a LOG, not a snapshot -- it is every redraw the session
    # ever emitted. Replaying it re-renders the whole history: the same
    # conversation painted several times down the page, two tmux status bars,
    # and a cursor left wherever the last replayed frame put it, so live output
    # arrived off-screen and the page looked frozen until you reloaded it.
    #
    # tmux holds the real screen, so ask it to draw that instead. Clear what
    # the browser has first, or the repaint lands on top of the old frame.
    # Without tmux there is nothing to ask, and the log is all we have.
    try:
        _send(sock, json.dumps({"t": "attached", "resumed": resumed,
                                "bytes": len(backlog)}).encode(), opcode=0x1)
        if session.tmux_name:
            # \x1b[2J clears the SCREEN. \x1b[3J, which used to be here too,
            # clears the browser's saved scrollback -- so the page arrived with
            # nothing above the fold and the wheel did nothing. The history
            # comes from tmux instead, written in above the repaint, and the
            # conversation can be scrolled back through like any other page.
            _send(sock, b"\x1b[H\x1b[2J", opcode=0x2)
            past = history(name)
            if past.strip():
                _send(sock, past.replace("\n", "\r\n").encode() + b"\r\n",
                      opcode=0x2)
            # The repaint itself waits for the browser's first resize: drawing
            # now would draw at whatever size the last viewer had, and the new
            # page would get a screen laid out for someone else's window.
        elif backlog:
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

    def pump_state():
        """Is it done yet? -- the one question the board pane answers.

        A separate frame from the output because it is a different kind of
        thing: the bytes are what happened, this is what is happening. It
        keeps arriving while the session is silent, which is exactly when
        somebody is standing there wondering.
        """
        w = watch(name)
        while not stop.is_set() and session.alive:
            try:
                _send(sock, json.dumps(w.poll()).encode(), opcode=0x1)
            except OSError:
                break
            time.sleep(1.0)

    t = threading.Thread(target=pump_out, daemon=True)
    t.start()
    threading.Thread(target=pump_state, daemon=True).start()

    first_resize = True
    viewer = id(queue)          # this page's identity for as long as it is here
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
                    # This page's own vote, not a decree for every other tab.
                    session.set_size(viewer,
                                     int(msg.get("cols", 120)),
                                     int(msg.get("rows", 32)))
                    # tmux sizes a window to its smallest client and redraws on
                    # its own schedule, so the first resize from a new page is
                    # the moment its screen is finally the right shape. Ask for
                    # the repaint here, once.
                    if first_resize and session.tmux_name:
                        first_resize = False
                        session.repaint()
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
        # Give this page's share of the width back to whoever is still here.
        session.drop_size(viewer)


# ------------------------------------------------------------------ what it is
# The board pane is a WATCHER, not a driver: Marsita types in the real terminal
# and asks the browser one question -- is it done yet? Answering that needs a
# state, and a state needs to come from the session rather than from guessing at
# gaps in the output. tmux already holds the true screen, so ask tmux.

TURNS = pathlib.Path(__file__).resolve().parent.parent / "logs" / "turns.jsonl"

WORKING_MARKS = (
    "esc to interrupt",       # Claude Code's spinner line, every model
    "tokens · esc",
)
WAITING_MARKS = (
    "do you want",            # a permission prompt
    "would you like",
    "❯ 1.",
    "> 1. yes",
)


def classify(pane: str) -> str:
    """working | waiting | idle, from the tail of the visible screen.

    Three states because they mean three different things to a human across
    the room: keep doing what you are doing, come back, and it needs you NOW.
    Reading the screen beats timing the output -- a model that thinks for two
    minutes without printing is still working, and a gap in the bytes says
    nothing about which of the three it is.
    """
    tail = "\n".join(pane.strip().splitlines()[-20:]).lower()
    if any(m in tail for m in WORKING_MARKS):
        return "working"
    if any(m in tail for m in WAITING_MARKS):
        return "waiting"
    return "idle"


def _capture(name: str, *args: str) -> str:
    tmux = tmux_bin()
    if not tmux:
        return ""
    try:
        r = subprocess.run([tmux, "capture-pane", "-p", "-t", name, *args],
                           capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout if r.returncode == 0 else ""


def capture(name: str) -> str:
    """The visible screen of a tmux session, without attaching to it."""
    return _capture(name)


def history(name: str, lines: int = 3000) -> str:
    """What scrolled off the top -- the conversation, not the current screen.

    A page that shows only the live screen cannot be scrolled back, because
    there is nothing above it: tmux owns the scrollback, and the repaint on
    attach paints one screen. Marsita, 2026-09-04: "I also want to scroll up
    on the Claude messages back."

    `-S -N -E -1` is the history region ONLY. tmux numbers the top visible
    line 0 and counts backwards into the past, so ending at -1 stops exactly
    where the repaint is about to start -- no line appears twice.
    """
    return _capture(name, "-S", f"-{int(lines)}", "-E", "-1")


def record_turn(seconds: float, path: pathlib.Path = TURNS) -> None:
    """Remember how long one working spell took, so the next one can be guessed."""
    if seconds < 2:                       # a blip, not a turn
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as fh:
            fh.write(json.dumps({"at": time.time(), "seconds": round(seconds, 1)}) + "\n")
    except OSError:
        pass


def estimate(path: pathlib.Path = TURNS, window: int = 20) -> float | None:
    """A guess at how long the current turn will take: median of the last few.

    Median, not mean: one turn that ran for an hour should not move the number
    everything else is measured against. None when there is no history -- a
    guess with nothing behind it is worse than saying nothing.
    """
    try:
        rows = path.read_text().splitlines()[-window:]
    except OSError:
        return None
    secs = []
    for line in rows:
        try:
            secs.append(float(json.loads(line)["seconds"]))
        except (ValueError, KeyError, TypeError):
            continue
    if not secs:
        return None
    secs.sort()
    mid = len(secs) // 2
    return secs[mid] if len(secs) % 2 else (secs[mid - 1] + secs[mid]) / 2


class _Watch:
    """One poller per session name, however many browsers are looking.

    Shared because the capture costs a subprocess and the turn log must not be
    written twice for one turn -- two open tabs would otherwise double every
    duration in the history the estimate is built from.
    """

    def __init__(self, name: str):
        self.name = name
        self.state = "idle"
        self.since = time.time()
        self.lock = threading.Lock()
        self.checked = 0.0

    def poll(self, every: float = 1.0) -> dict:
        now = time.time()
        with self.lock:
            if now - self.checked >= every:
                self.checked = now
                state = classify(capture(self.name))
                if state != self.state:
                    if self.state == "working":
                        record_turn(now - self.since)
                    self.state, self.since = state, now
            return {"t": "state", "state": self.state,
                    "since": self.since, "estimate": estimate()}


_WATCH: dict[str, _Watch] = {}


def watch(name: str) -> _Watch:
    with _LIVE_LOCK:
        w = _WATCH.get(name)
        if w is None:
            w = _WATCH[name] = _Watch(name)
        return w
