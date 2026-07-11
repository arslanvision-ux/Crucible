"""
Crucible — Bidirectional Live Bridge (Nuke side).

Architecture
------------
                 ┌─────────────────────────────────┐
                 │           NUKE                  │
                 │  NukeLiveSender ──────────────► │──── TCP ──► Houdini server  (port 7890)
                 │  NukeLiveListener ◄──────────── │◄─── TCP ─── Houdini sender  (port 7893)
                 └─────────────────────────────────┘

NukeLiveSender   — fire-and-forget TCP client.  Sends JSON messages to
                   the DCC listener (existing behaviour, unchanged).

NukeLiveListener — background thread that listens on a second port for
                   incoming messages FROM the DCC (camera data, scene info,
                   reverse light state).  Dispatches via registered callbacks
                   on Nuke's updateUI so all Nuke API calls stay main-thread-safe.

Registered callbacks receive a fully-parsed dict with a ``"type"`` key:
    ``camera_frame``     → single frame camera update
    ``camera_sequence``  → full animated camera (array of frames)
    ``scene_info``       → lights + render settings snapshot
    ``pong``             → heartbeat reply

Usage
-----
::

    sender   = NukeLiveSender(host="localhost", port=7890)
    listener = NukeLiveListener(port=7893)

    listener.register(MSG_CAMERA_FRAME,   my_camera_handler)
    listener.register(MSG_CAMERA_SEQUENCE, my_sequence_handler)
    listener.register(MSG_SCENE_INFO,      my_scene_handler)

    listener.start()
    sender.connect()

    # Send light state as before
    sender.send({"type": "light_state", "lighting_multipliers": {...}})

    # Ask Houdini for the current camera
    sender.send({"type": "request_camera"})
    # → Houdini responds on port 7893 with camera_frame or camera_sequence

    listener.stop()
"""

from __future__ import annotations

import json
import queue
import socket
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from .live_bridge_protocol import (
    LIVE_BRIDGE_DEFAULT_PORT,
    LIVE_BRIDGE_PORTS,
    MSG_CAMERA_FRAME,
    MSG_CAMERA_SEQUENCE,
    MSG_SCENE_INFO,
    MSG_PONG,
    MSG_ERROR,
    PROTOCOL_VERSION,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LIVE_BRIDGE_LISTEN_PORT  = 7893   # Port Nuke listens ON for incoming DCC data
_RECONNECT_TRIES         = 3
_RECONNECT_DELAY         = 0.5
_SOCKET_TIMEOUT          = 2.0


# ---------------------------------------------------------------------------
# Shared framing helpers
# ---------------------------------------------------------------------------

def _recv_exactly(conn: socket.socket, n: int) -> bytes:
    """Read exactly *n* bytes from a connected socket."""
    buf = b""
    while len(buf) < n:
        chunk = conn.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("Connection closed mid-read.")
        buf += chunk
    return buf


def _send_message(sock: socket.socket, data: dict) -> None:
    """Frame and send a JSON dict over *sock*."""
    payload = json.dumps(data).encode("utf-8")
    sock.sendall(len(payload).to_bytes(4, "big") + payload)


def _read_message(conn: socket.socket) -> dict:
    """Read one framed message from *conn* and return the parsed dict."""
    length_bytes = _recv_exactly(conn, 4)
    length       = int.from_bytes(length_bytes, "big")
    payload      = _recv_exactly(conn, length)
    return json.loads(payload.decode("utf-8"))


# ---------------------------------------------------------------------------
# NukeLiveSender  (Nuke → DCC,  unchanged API, enhanced protocol)
# ---------------------------------------------------------------------------

class NukeLiveSender:
    """Non-blocking TCP client that sends typed messages to the DCC server.

    Automatically reconnects on send failure.  All public methods are
    thread-safe.

    The ``send()`` method accepts any dict.  If the dict has no ``"type"``
    key it is wrapped as a ``light_state`` for backward compatibility with
    the v1 Houdini server.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = LIVE_BRIDGE_DEFAULT_PORT,
    ) -> None:
        self.host = host
        self.port = port
        self._connected = False
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ #

    def is_connected(self) -> bool:
        return self._connected

    def connect(self) -> bool:
        """Test-connect.  Returns True on success."""
        try:
            s = socket.create_connection((self.host, self.port), timeout=_SOCKET_TIMEOUT)
            s.close()
            self._connected = True
            return True
        except (ConnectionRefusedError, OSError):
            self._connected = False
            return False

    def disconnect(self) -> None:
        self._connected = False

    # ------------------------------------------------------------------ #

    def send(self, data: dict) -> None:
        """Fire-and-forget: send *data* to the DCC.

        Adds ``"type": "light_state"`` if the key is absent (v1 compat).
        Runs in a daemon thread — never blocks the caller.
        """
        if not self._connected:
            return
        if "type" not in data:
            data = dict(data)
            data["type"] = "light_state"
        payload = json.dumps(data).encode("utf-8")
        t = threading.Thread(
            target=self._send_with_retry,
            args=(payload,),
            daemon=True,
            name="CrucibleLiveSend",
        )
        t.start()

    def request_camera(self, frame_range: Optional[tuple] = None) -> None:
        """Ask the DCC to send its current camera data.

        Args:
            frame_range: Optional (start, end) tuple.  If None the DCC
                         sends only the current frame.
        """
        msg: Dict[str, Any] = {"type": "request_camera", "protocol": PROTOCOL_VERSION}
        if frame_range:
            msg["frame_start"] = int(frame_range[0])
            msg["frame_end"]   = int(frame_range[1])
        self.send(msg)

    def request_scene(self) -> None:
        """Ask the DCC to send a full scene info snapshot."""
        self.send({"type": "request_scene", "protocol": PROTOCOL_VERSION})

    def ping(self) -> None:
        """Send a heartbeat ping.  DCC should reply with pong."""
        self.send({"type": "ping", "protocol": PROTOCOL_VERSION})

    # ------------------------------------------------------------------ #

    def _send_with_retry(self, payload: bytes) -> None:
        for attempt in range(1, _RECONNECT_TRIES + 1):
            try:
                with socket.create_connection(
                    (self.host, self.port), timeout=_SOCKET_TIMEOUT
                ) as s:
                    s.sendall(len(payload).to_bytes(4, "big") + payload)
                self._connected = True
                return
            except OSError:
                if attempt < _RECONNECT_TRIES:
                    time.sleep(_RECONNECT_DELAY)
                else:
                    print(
                        f"[Crucible LiveBridge] Lost connection to "
                        f"{self.host}:{self.port} after {_RECONNECT_TRIES} attempts."
                    )
                    self._connected = False


# ---------------------------------------------------------------------------
# NukeLiveListener  (DCC → Nuke,  NEW)
# ---------------------------------------------------------------------------

class NukeLiveListener:
    """Background TCP server that receives typed messages from the DCC.

    Incoming messages are queued and dispatched inside Nuke's ``updateUI``
    callback so all Nuke API calls remain on the main thread.

    Callbacks are registered per message type::

        listener.register("camera_frame", my_func)

    Each callback receives a single argument: the parsed message dict.
    """

    def __init__(self, port: int = LIVE_BRIDGE_LISTEN_PORT) -> None:
        self.port            = port
        self._running        = False
        self._thread: Optional[threading.Thread] = None
        self._server_sock: Optional[socket.socket] = None
        self._queue: queue.Queue = queue.Queue()
        self._callbacks: Dict[str, List[Callable]] = {}

        # Nuke updateUI integration (set True after start() to enable)
        self._nuke_callback_registered = False

    # ------------------------------------------------------------------ #
    # Registration
    # ------------------------------------------------------------------ #

    def register(self, msg_type: str, callback: Callable) -> None:
        """Register *callback* to be called when *msg_type* arrives.

        Multiple callbacks can be registered for the same type.
        """
        self._callbacks.setdefault(msg_type, []).append(callback)

    def unregister(self, msg_type: str, callback: Callable) -> None:
        if msg_type in self._callbacks:
            try:
                self._callbacks[msg_type].remove(callback)
            except ValueError:
                pass

    # ------------------------------------------------------------------ #
    # Start / Stop
    # ------------------------------------------------------------------ #

    def start(self) -> bool:
        """Start the listener.  Returns True if successfully bound."""
        if self._running:
            return True
        try:
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind(("0.0.0.0", self.port))
            srv.listen(5)
            self._server_sock = srv
        except OSError as e:
            print(f"[Crucible LiveListener] Failed to bind port {self.port}: {e}")
            return False

        self._running = True
        self._thread  = threading.Thread(
            target=self._listen_loop,
            args=(srv,),
            daemon=True,
            name="CrucibleLiveListener",
        )
        self._thread.start()
        self._register_nuke_update()
        print(f"[Crucible LiveListener] Listening on port {self.port}.")
        return True

    def stop(self) -> None:
        """Stop the listener and clean up."""
        self._running = False
        if self._server_sock:
            try:
                self._server_sock.close()
            except Exception:
                pass
            self._server_sock = None
        self._unregister_nuke_update()
        print("[Crucible LiveListener] Stopped.")

    @property
    def is_running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------ #
    # Internal
    # ------------------------------------------------------------------ #

    def _listen_loop(self, srv_sock: socket.socket) -> None:
        srv_sock.settimeout(1.0)
        while self._running:
            try:
                conn, addr = srv_sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                with conn:
                    msg = _read_message(conn)
                    print(f"[Crucible LiveListener] Received message type: {msg.get('type')}")
                    self._queue.put(msg)
            except Exception as e:
                print(f"[Crucible LiveListener] recv error: {e}")

    def _dispatch_queue(self) -> None:
        """Drain the queue and fire callbacks.  Called from Nuke updateUI."""
        while not self._queue.empty():
            try:
                msg = self._queue.get_nowait()
                msg_type = msg.get("type", "unknown")
                print(f"[Crucible LiveListener] Dispatching queued message: {msg_type}")
                for cb in self._callbacks.get(msg_type, []):
                    try:
                        cb(msg)
                    except Exception as e:
                        print(f"[Crucible LiveListener] callback error ({msg_type}): {e}")
            except Exception as e:
                print(f"[Crucible LiveListener] dispatch error: {e}")

    def _register_nuke_update(self) -> None:
        try:
            import nuke
            nuke.addUpdateUI(self._dispatch_queue)
            self._nuke_callback_registered = True
        except Exception:
            pass  # Not inside Nuke — callbacks won't fire, but listener still works

    def _unregister_nuke_update(self) -> None:
        if not self._nuke_callback_registered:
            return
        try:
            import nuke
            nuke.removeUpdateUI(self._dispatch_queue)
        except Exception:
            pass
        self._nuke_callback_registered = False
