"""
Crucible — Bidirectional Live Bridge Protocol.

Shared message framing and type constants used by both the Nuke client
and every DCC server (Houdini, Maya, Blender).

Message wire format (binary framing)
--------------------------------------
  [4 bytes big-endian uint]  = payload length N
  [N bytes UTF-8 JSON]       = message dict

Every message dict MUST have a ``"type"`` key.

Message Types
-------------
Nuke → DCC:
  ``light_state``      Full light mixer state (multipliers + colors).
  ``request_camera``   Ask DCC to stream current camera data.
  ``request_scene``    Ask DCC to stream full scene info.
  ``ping``             Heartbeat — DCC should reply with ``pong``.

DCC → Nuke:
  ``camera_frame``     Single-frame camera data (T/R/focal/aperture...).
  ``camera_sequence``  Full animated camera (array of frames).
  ``scene_info``       Lights + render settings snapshot.
  ``light_state``      DCC-initiated light update (reverse direction).
  ``pong``             Heartbeat reply.
  ``error``            Error message from DCC side.
"""

# ---------------------------------------------------------------------------
# Message type constants
# ---------------------------------------------------------------------------

# Nuke → DCC
MSG_LIGHT_STATE      = "light_state"
MSG_REQUEST_CAMERA   = "request_camera"
MSG_REQUEST_SCENE    = "request_scene"
MSG_PING             = "ping"

# DCC → Nuke
MSG_CAMERA_FRAME     = "camera_frame"
MSG_CAMERA_SEQUENCE  = "camera_sequence"
MSG_SCENE_INFO       = "scene_info"
MSG_PONG             = "pong"
MSG_ERROR            = "error"

# Protocol version — checked on connect to warn about mismatches
PROTOCOL_VERSION = "2.0"

# DCC server ports (DCCs listen on these; Nuke connects outbound)
LIVE_BRIDGE_DEFAULT_PORT = 7890
LIVE_BRIDGE_PORTS = {
    "Houdini": 7890,
    "Maya":    7891,
    "Blender": 7892,
}

# Nuke listener port (Nuke listens here; all DCCs send back to this port)
LIVE_BRIDGE_NUKE_LISTEN_PORT = 7893

# Companion server script filenames (relative to crucible package)
LIVE_SERVER_SCRIPTS = {
    "Houdini": "houdini_live_server.py",
    "Maya":    "maya_live_server.py",
    "Blender": "blender_live_server.py",
}
