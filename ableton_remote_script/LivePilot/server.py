"""
LivePilot - TCP server, run entirely on Ableton's main thread.

Source of truth: music/live-pilot/ableton_remote_script/LivePilot/server.py,
deployed by scripts/deploy_remote_handlers.py. Needs a Live restart to take
effect (hot reload skips this module because it owns the socket).

Every tick (~109 ms) the server accepts, reads, runs and answers on the main
thread with non-blocking sockets. The previous design used a listener thread
and a client thread handing commands over through queues; Live's embedded
Python only lets background threads run once per tick, so each hand-off cost
a full tick and a bare ping took ~440 ms (measured 2026-10-14 with lp_clock:
2-4 ticks to reach the main thread, 1-2 more to send the reply).
"""

import json
import socket

from . import router

# ── Commands that modify Live state (need settle delay) ──────────────────────

WRITE_COMMANDS = frozenset([
    # transport
    "set_tempo", "set_time_signature", "start_playback", "stop_playback",
    "continue_playback", "toggle_metronome", "set_session_loop", "undo", "redo",
    # tracks
    "create_midi_track", "create_audio_track", "create_return_track",
    "delete_track", "duplicate_track", "set_track_name", "set_track_color",
    "set_track_mute", "set_track_solo", "set_track_arm", "stop_track_clips",
    "set_group_fold", "set_track_input_monitoring",
    # clips
    "create_clip", "create_audio_clip", "delete_clip", "duplicate_clip", "fire_clip", "stop_clip",
    "set_clip_name", "set_clip_color", "set_clip_loop", "set_clip_launch",
    "set_clip_warp_mode",
    # notes
    "add_notes", "remove_notes", "remove_notes_by_id", "modify_notes",
    "duplicate_notes", "transpose_notes", "quantize_clip",
    # devices
    "set_device_parameter", "batch_set_parameters", "toggle_device",
    "delete_device", "load_device_by_uri", "find_and_load_device",
    "set_chain_volume", "set_simpler_playback_mode",
    # scenes
    "create_scene", "delete_scene", "duplicate_scene", "fire_scene",
    "set_scene_name", "set_scene_color", "set_scene_tempo",
    "fire_scene_clips", "stop_all_clips",
    # tracks (freeze/flatten)
    "freeze_track", "flatten_track",
    # mixing
    "set_track_volume", "set_track_pan", "set_track_send",
    "set_master_volume", "set_track_routing",
    # browser
    "load_browser_item",
    # arrangement
    "jump_to_time", "jump_to_cue", "capture_midi", "start_recording",
    "stop_recording", "toggle_cue_point", "back_to_arranger",
    "create_arrangement_clip", "add_arrangement_notes",
    "remove_arrangement_notes", "remove_arrangement_notes_by_id",
    "modify_arrangement_notes", "duplicate_arrangement_notes",
    "transpose_arrangement_notes", "set_arrangement_automation",
    "set_arrangement_clip_name",
    # clip automation
    "set_clip_automation",
    "clear_clip_automation",
])

TICK = 1  # schedule_message delay in Live ticks
MAX_BUF = 4 * 1024 * 1024  # 4 MB


class LivePilotServer(object):
    """Single-client JSON-over-TCP server driven by Live's tick.

    A new connection replaces the current one. Requests are newline-delimited
    JSON {"id", "type", "params"}; replies are {"id", "ok", "result"|"error"}.
    Write commands answer on the next tick (settle delay), and nothing after
    them is read until then, so replies stay in request order.
    """

    def __init__(self, control_surface, host="127.0.0.1", port=9878):
        self._cs = control_surface
        self._host = host
        self._port = port
        self._running = False
        self._server_socket = None
        self._client = None
        self._buf = bytearray()
        self._held = None  # (client, response) for a write awaiting its settle tick

    # ── Public API ───────────────────────────────────────────────────────

    def start(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((self._host, self._port))
            sock.listen(2)
            sock.setblocking(False)
        except OSError as exc:
            self._log("Failed to bind: %s" % exc)
            return
        self._server_socket = sock
        self._running = True
        self._log("Listening on %s:%d (main-thread polling)" % (self._host, self._port))
        self._schedule()

    def stop(self):
        self._running = False
        self._drop_client()
        if self._server_socket is not None:
            try:
                self._server_socket.close()
            except OSError:
                pass
            self._server_socket = None
        self._log("Server stopped")

    # ── Logging ──────────────────────────────────────────────────────────

    def _log(self, message):
        try:
            self._cs.log_message("[LivePilot] " + str(message))
        except Exception:
            pass

    # ── Tick loop (main thread) ──────────────────────────────────────────

    def _schedule(self):
        if not self._running:
            return
        try:
            self._cs.schedule_message(TICK, self._tick)
        except AssertionError:
            self._running = False  # ControlSurface disconnecting

    def _tick(self):
        try:
            self._accept()
            if self._held is not None:
                client, response = self._held
                self._held = None
                self._send(client, response)
            self._read()
            self._process()
        except Exception as exc:  # never let one bad tick stop the loop
            self._log("Tick error: %s" % exc)
        finally:
            self._schedule()

    def _accept(self):
        while True:
            try:
                client, addr = self._server_socket.accept()
            except (BlockingIOError, InterruptedError):
                return
            except OSError as exc:
                self._log("Accept error: %s" % exc)
                return
            if self._client is not None:
                self._log("Replacing client with new connection from %s:%d" % addr)
            self._drop_client()
            client.setblocking(False)
            self._client = client

    def _drop_client(self):
        if self._client is not None:
            try:
                self._client.close()
            except OSError:
                pass
        self._client = None
        self._buf = bytearray()
        self._held = None

    def _read(self):
        while self._client is not None:
            try:
                data = self._client.recv(65536)
            except (BlockingIOError, InterruptedError):
                return
            except OSError as exc:
                self._log("Recv error: %s" % exc)
                self._drop_client()
                return
            if not data:
                self._drop_client()
                return
            self._buf.extend(data)
            if len(self._buf) > MAX_BUF:
                self._log("Client buffer overflow, disconnecting")
                self._drop_client()
                return

    def _process(self):
        # Bytes are split on newlines before decoding so a multi-byte UTF-8
        # character straddling two recv chunks is never corrupted.
        while self._client is not None and self._held is None:
            nl = self._buf.find(b"\n")
            if nl < 0:
                return
            raw_line = bytes(self._buf[:nl])
            del self._buf[: nl + 1]
            try:
                line = raw_line.decode("utf-8").strip()
            except UnicodeDecodeError as exc:
                self._send(self._client, {"id": "unknown", "ok": False, "error": {
                    "code": "INVALID_PARAM", "message": "Invalid UTF-8 in request: %s" % exc}})
                continue
            if line:
                self._run_line(line)

    def _run_line(self, line):
        try:
            command = json.loads(line)
        except (ValueError, TypeError) as exc:
            self._send(self._client, {"id": "unknown", "ok": False,
                                      "error": {"code": "INVALID_PARAM", "message": "Bad JSON: %s" % exc}})
            return
        try:
            result = router.dispatch(self._cs.song(), command)
        except Exception as exc:
            result = {"id": command.get("id", "unknown"), "ok": False,
                      "error": {"code": "INTERNAL", "message": str(exc)}}
        if command.get("type", "") in WRITE_COMMANDS:
            self._held = (self._client, result)  # answer after one settle tick
        else:
            self._send(self._client, result)

    # ── Socket I/O ───────────────────────────────────────────────────────

    def _send(self, client, response):
        """Send one JSON reply, blocking briefly so a large reply goes out whole."""
        from .utils import serialize_json
        if client is None:
            return
        try:
            client.settimeout(5.0)
            client.sendall(serialize_json(response).encode("utf-8"))
        except OSError as exc:
            self._log("Send error: %s" % exc)
        finally:
            try:
                client.setblocking(False)
            except OSError:
                pass
