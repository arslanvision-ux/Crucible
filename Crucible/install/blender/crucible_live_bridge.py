"""
Crucible — Real-Time Live Bridge

Provides a socket-based live link between Nuke's LightMixer and Houdini Solaris.
When a slider changes in Nuke the full light state is broadcast to Houdini over
a TCP socket, and Houdini updates its light node parameters immediately on the
main thread via hou.ui.addEventLoopCallback.

The sender auto-reconnects silently on send failure — no manual toggle needed.
"""

import json
import socket
import threading
import time

# ---------------------------------------------------------------------------
# Nuke-side sender (runs inside Nuke)
# ---------------------------------------------------------------------------

LIVE_BRIDGE_DEFAULT_HOST = "localhost"
LIVE_BRIDGE_DEFAULT_PORT = 7890

# Per-DCC default ports
LIVE_BRIDGE_PORTS = {
    "Houdini": 7890,
    "Maya":    7891,
    "Blender": 7892,
}

# Auto-reconnect settings
_RECONNECT_TRIES    = 3      # attempts before giving up a single send
_RECONNECT_DELAY    = 0.5    # seconds between reconnect attempts
_SOCKET_TIMEOUT     = 2.0    # seconds per connection attempt


class NukeLiveSender:
    """Non-blocking TCP client that sends light state dicts to the DCC receiver.

    Automatically attempts to reconnect on send failure so the user never
    has to manually toggle Live Link off and on again.
    """

    def __init__(self, host=LIVE_BRIDGE_DEFAULT_HOST, port=LIVE_BRIDGE_DEFAULT_PORT):
        self.host = host
        self.port = port
        self._connected = False
        self._lock = threading.Lock()

    def is_connected(self):
        return self._connected

    def connect(self):
        """Test the connection. Returns True on success."""
        try:
            s = socket.create_connection((self.host, self.port), timeout=_SOCKET_TIMEOUT)
            s.close()
            self._connected = True
            return True
        except (ConnectionRefusedError, OSError):
            self._connected = False
            return False

    def disconnect(self):
        self._connected = False

    def send(self, state: dict):
        """Fire-and-forget: serialize state and send. Runs in a daemon thread."""
        if not self._connected:
            return
        payload = json.dumps(state).encode("utf-8")
        t = threading.Thread(
            target=self._send_with_retry,
            args=(payload,),
            daemon=True,
            name="CrucibleLiveSend"
        )
        t.start()

    def _send_with_retry(self, payload: bytes):
        """Try to send payload, auto-reconnecting up to _RECONNECT_TRIES times.

        If every attempt fails the link marks itself disconnected so the UI
        button reflects the real state. The user can re-enable Live Link once
        the DCC receiver is reachable again.
        """
        for attempt in range(1, _RECONNECT_TRIES + 1):
            try:
                with socket.create_connection(
                    (self.host, self.port), timeout=_SOCKET_TIMEOUT
                ) as s:
                    length = len(payload).to_bytes(4, "big")
                    s.sendall(length + payload)
                # Send succeeded — ensure connected flag is set
                self._connected = True
                return
            except OSError:
                if attempt < _RECONNECT_TRIES:
                    # Brief pause before next attempt
                    time.sleep(_RECONNECT_DELAY)
                else:
                    # All attempts exhausted — mark as disconnected
                    print(
                        f"[Crucible LiveBridge] Lost connection to "
                        f"{self.host}:{self.port} after {_RECONNECT_TRIES} attempts."
                    )
                    self._connected = False
