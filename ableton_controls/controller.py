"""
Ableton Live OSC Control Module

Handles all OSC communication with Ableton Live via AbletonOSC bridge.
All track indices are 0-based (Track 1 in Ableton = index 0 in code).

IMPORTANT: Per AbletonOSC documentation, track_id/scene_id/clip_id are
PARAMETERS, not part of the OSC path.

Example:
  CORRECT: /live/track/set/mute [track_id, mute_value]
  WRONG:   /live/track/{track_id}/set/mute [mute_value]
"""

from pythonosc.udp_client import SimpleUDPClient
import json
import os
import socket
import struct
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

class AbletonController:
    """Main controller for Ableton Live via OSC"""
    
    def __init__(self, ip="127.0.0.1", port=11000, response_port=11001):
        """
        Initialize OSC client for Ableton communication
        
        Args:
            ip: IP address of OSC bridge (default: 127.0.0.1)
            port: Port number of OSC bridge (default: 11000)
            response_port: Port AbletonOSC sends responses to (default: 11001)
        """
        self.ip = ip
        self.port = port
        self.response_port = response_port
        self.client = SimpleUDPClient(ip, port)
        self.connected = False
        self.osc_paths = self._load_osc_paths()

        # AbletonOSC "get/*" endpoints are async; responses arrive on response_port.
        # We run a UDP listener so we can do request/response for queries like
        # parameter names/min/max, device counts, etc.
        self._resp_sock: Optional[socket.socket] = None
        self._resp_thread: Optional[threading.Thread] = None
        self._resp_running = False
        self._resp_lock = threading.Lock()
        self._resp_cv = threading.Condition(self._resp_lock)
        # address -> (timestamp, args)
        self._last_response: Dict[str, Tuple[float, List[Any]]] = {}
        # (track, device) -> (mins, maxs, timestamp)
        self._param_range_cache: Dict[Tuple[int, int], Tuple[List[float], List[float], float]] = {}

        self._start_response_listener()
    
    def _load_osc_paths(self):
        """Load OSC paths from config file"""
        config_path = "config/osc_paths.json"
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                return json.load(f)
        return None
    
    def test_connection(self):
        """
        Test if OSC bridge is responding
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            self.client.send_message("/live/test", [])
            self.connected = True
            return True
        except Exception as e:
            print(f"OSC Connection Error: {e}")
            self.connected = False
            return False

    # ==================== OSC REQUEST/RESPONSE (AbletonOSC replies on 11001) ====================

    def _start_response_listener(self):
        """Start UDP listener for AbletonOSC responses (best-effort)."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((self.ip, self.response_port))
            sock.settimeout(0.5)
            self._resp_sock = sock
            self._diag_listener_ok = True
            self._diag_listener_addr = (self.ip, self.response_port)
        except Exception as exc:
            # If we can't bind, queries will be fire-and-forget.
            self._resp_sock = None
            self._diag_listener_ok = False
            self._diag_listener_error = str(exc)
            return

        self._resp_running = True
        self._resp_thread = threading.Thread(target=self._response_loop, daemon=True)
        self._resp_thread.start()

    def shutdown(self):
        """Stop the response listener (best-effort)."""
        self._resp_running = False
        try:
            if self._resp_sock:
                self._resp_sock.close()
        except Exception:
            pass
        self._resp_sock = None

    def _response_loop(self):
        """Receive and store AbletonOSC responses."""
        if self._resp_sock is None:
            return
        while self._resp_running:
            try:
                data, _addr = self._resp_sock.recvfrom(65536)
            except socket.timeout:
                continue
            except Exception:
                continue

            try:
                address, args = self._parse_osc_message(data)
            except Exception:
                continue

            with self._resp_cv:
                self._last_response[address] = (time.time(), args)
                self._resp_cv.notify_all()

    def _build_osc_message(self, address: str, args: List[Any]) -> bytes:
        """Build a minimal OSC message (address + typetags + args)."""
        addr_bytes = address.encode("utf-8") + b"\x00"
        addr_padded = addr_bytes + b"\x00" * ((4 - len(addr_bytes) % 4) % 4)

        type_tag = ","
        arg_data = b""

        for arg in args:
            if isinstance(arg, bool):
                type_tag += "i"
                arg_data += struct.pack(">i", 1 if arg else 0)
            elif isinstance(arg, int):
                type_tag += "i"
                arg_data += struct.pack(">i", arg)
            elif isinstance(arg, float):
                type_tag += "f"
                arg_data += struct.pack(">f", arg)
            else:
                type_tag += "s"
                s = str(arg)
                s_bytes = s.encode("utf-8") + b"\x00"
                s_padded = s_bytes + b"\x00" * ((4 - len(s_bytes) % 4) % 4)
                arg_data += s_padded

        type_bytes = type_tag.encode("utf-8") + b"\x00"
        type_padded = type_bytes + b"\x00" * ((4 - len(type_bytes) % 4) % 4)

        return addr_padded + type_padded + arg_data

    def _parse_osc_message(self, data: bytes) -> Tuple[str, List[Any]]:
        """Parse a minimal OSC message (address + typetags + args)."""
        null_idx = data.index(b"\x00")
        address = data[:null_idx].decode("utf-8")
        addr_size = (null_idx + 4) & ~3
        if len(data) <= addr_size:
            return address, []

        type_start = addr_size
        if data[type_start:type_start + 1] != b",":
            return address, []
        type_null = data.index(b"\x00", type_start)
        type_tag = data[type_start + 1:type_null].decode("utf-8")
        type_size = ((type_null - type_start) + 4) & ~3

        args: List[Any] = []
        offset = type_start + type_size
        for tag in type_tag:
            if tag == "i":
                args.append(struct.unpack(">i", data[offset:offset + 4])[0])
                offset += 4
            elif tag == "f":
                args.append(struct.unpack(">f", data[offset:offset + 4])[0])
                offset += 4
            elif tag == "s":
                s_null = data.index(b"\x00", offset)
                args.append(data[offset:s_null].decode("utf-8"))
                offset = ((s_null + 1) + 3) & ~3

        return address, args

    def _send_and_wait(self,
                       address: str,
                       args: List[Any],
                       timeout: float = 2.0,
                       accept_addresses: Optional[List[str]] = None) -> Optional[Tuple[str, List[Any]]]:
        """
        Send an OSC message and wait for a matching response on response_port.

        AbletonOSC response address patterns can vary; we accept a small set
        of likely options: [address, address + '/response'].
        """
        if self._resp_sock is None:
            return None

        accept = accept_addresses or [address, f"{address}/response"]
        start_time = time.time()

        try:
            msg = self._build_osc_message(address, args)
            # Send from the LISTENER socket so AbletonOSC replies to response_port.
            # Previous approach created a throwaway socket (random ephemeral port)
            # which was closed before the reply arrived.
            self._resp_sock.sendto(msg, (self.ip, self.port))
        except Exception:
            # Fallback: try a separate socket (fire-and-forget send).
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.sendto(msg, (self.ip, self.port))
                sock.close()
            except Exception:
                return None

        with self._resp_cv:
            while time.time() - start_time < timeout:
                # Return most recent acceptable response after we sent.
                best_addr = None
                best_args = None
                best_ts = 0.0
                for a in accept:
                    if a in self._last_response:
                        ts, rargs = self._last_response[a]
                        if ts >= start_time and ts > best_ts:
                            best_ts = ts
                            best_addr = a
                            best_args = rargs
                if best_addr is not None and best_args is not None:
                    return best_addr, best_args

                # Also check for ANY response (address mismatch detection).
                # Stored for diagnostics but not returned here.
                for resp_addr, (ts, _) in list(self._last_response.items()):
                    if ts >= start_time and resp_addr not in accept:
                        if not hasattr(self, '_diag_unmatched'):
                            self._diag_unmatched = []
                        self._diag_unmatched.append(resp_addr)

                remaining = timeout - (time.time() - start_time)
                if remaining <= 0:
                    break
                self._resp_cv.wait(timeout=min(0.2, remaining))

        return None

    # ==================== VERIFIED SET (track-level) ====================

    def _verified_set(self,
                      set_address, set_args,
                      get_address, get_args,
                      expected_value, value_key,
                      value_compare=None,
                      retries=3, base_delay=0.1, max_delay=2.0, timeout=2.0):
        """
        SET→GET→compare verification loop with exponential backoff.

        Sends a SET command, waits, reads back with GET, and compares.
        Mirrors the pattern from reliable_params._retry_with_backoff.

        Args:
            set_address: OSC address for the SET command
            set_args: Arguments for the SET command
            get_address: OSC address for the GET readback
            get_args: Arguments for the GET command
            expected_value: The value we expect to read back
            value_key: Dict key for the readback value (e.g. "muted", "volume")
            value_compare: Optional callable(actual, expected) -> bool.
                           Defaults: int uses ==, float uses abs diff < 0.02
            retries: Maximum number of attempts (default 3)
            base_delay: Initial delay in seconds before first readback
            max_delay: Maximum delay between retries
            timeout: Timeout for each GET readback

        Returns:
            dict: {"success": bool, "verified": bool, "attempts": int,
                   "expected": value, "actual": value|None, "message": str}
        """
        if value_compare is None:
            def value_compare(actual, expected):
                if isinstance(expected, float) or isinstance(actual, float):
                    return abs(float(actual) - float(expected)) < 0.02
                return actual == expected

        last_actual = None

        for attempt in range(1, retries + 1):
            try:
                # 1. Fire-and-forget SET
                self.client.send_message(set_address, set_args)

                # 2. Exponential backoff delay
                delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                time.sleep(delay)

                # 3. Synchronous GET readback
                resp = self._send_and_wait(get_address, get_args, timeout=timeout)
                if resp:
                    _addr, args = resp
                    # Extract the value — last numeric arg is the value
                    actual = None
                    if args:
                        for a in reversed(args):
                            if isinstance(a, (int, float)):
                                actual = a
                                break
                    last_actual = actual

                    # 4. Compare
                    if actual is not None and value_compare(actual, expected_value):
                        return {
                            "success": True,
                            "verified": True,
                            "attempts": attempt,
                            "expected": expected_value,
                            "actual": actual,
                            "message": f"Verified after {attempt} attempt(s)"
                        }
            except Exception:
                pass

        # All retries exhausted — SET almost certainly went through, but
        # we couldn't confirm the readback matched.
        return {
            "success": True,
            "verified": False,
            "attempts": retries,
            "expected": expected_value,
            "actual": last_actual,
            "message": f"Unverified after {retries} attempt(s)"
        }

    # ==================== PLAYBACK CONTROLS ====================
    
    def play(self):
        """
        Start playback
        
        Returns:
            dict: {"success": bool, "message": str}
        """
        try:
            self.client.send_message("/live/song/start_playing", [])
            return {"success": True, "message": "Playback started"}
        except Exception as e:
            return {"success": False, "message": f"Failed to start playback: {e}"}
    
    def stop(self):
        """
        Stop playback
        
        Returns:
            dict: {"success": bool, "message": str}
        """
        try:
            self.client.send_message("/live/song/stop_playing", [])
            return {"success": True, "message": "Playback stopped"}
        except Exception as e:
            return {"success": False, "message": f"Failed to stop playback: {e}"}
    
    def continue_playback(self):
        """
        Continue playback from current position
        
        Returns:
            dict: {"success": bool, "message": str}
        """
        try:
            self.client.send_message("/live/song/continue_playing", [])
            return {"success": True, "message": "Playback continued"}
        except Exception as e:
            return {"success": False, "message": f"Failed to continue playback: {e}"}
    
    def start_recording(self):
        """
        Start recording (enable record mode)
        
        Returns:
            dict: {"success": bool, "message": str}
        """
        try:
            self.client.send_message("/live/song/set/record_mode", [1])
            return {"success": True, "message": "Recording started"}
        except Exception as e:
            return {"success": False, "message": f"Failed to start recording: {e}"}
    
    def stop_recording(self):
        """
        Stop recording (disable record mode)
        
        Returns:
            dict: {"success": bool, "message": str}
        """
        try:
            self.client.send_message("/live/song/set/record_mode", [0])
            return {"success": True, "message": "Recording stopped"}
        except Exception as e:
            return {"success": False, "message": f"Failed to stop recording: {e}"}
    
    def toggle_metronome(self, state=None):
        """
        Toggle metronome on/off
        
        Args:
            state: 1 for on, 0 for off
            
        Returns:
            dict: {"success": bool, "message": str}
        """
        try:
            if state is None:
                return {"success": False, "message": "Please specify metronome state (on/off)"}
            
            self.client.send_message("/live/song/set/metronome", [state])
            state_str = "on" if state == 1 else "off"
            return {"success": True, "message": f"Metronome turned {state_str}"}
        except Exception as e:
            return {"success": False, "message": f"Failed to toggle metronome: {e}"}
    
    # ==================== TRANSPORT CONTROLS ====================
    
    def set_tempo(self, bpm):
        """
        Set the tempo/BPM
        
        Args:
            bpm: Tempo in beats per minute (20-999)
            
        Returns:
            dict: {"success": bool, "message": str}
        """
        try:
            if not 20 <= bpm <= 999:
                return {"success": False, "message": "BPM must be between 20 and 999"}
            
            self.client.send_message("/live/song/set/tempo", [float(bpm)])
            return {"success": True, "message": f"Tempo set to {bpm} BPM"}
        except Exception as e:
            return {"success": False, "message": f"Failed to set tempo: {e}"}
    
    def set_position(self, beat):
        """
        Set playback position
        
        Args:
            beat: Position in beats
            
        Returns:
            dict: {"success": bool, "message": str}
        """
        try:
            self.client.send_message("/live/song/set/current_song_time", [float(beat)])
            return {"success": True, "message": f"Position set to beat {beat}"}
        except Exception as e:
            return {"success": False, "message": f"Failed to set position: {e}"}
    
    def set_loop(self, enabled):
        """
        Enable/disable loop
        
        Args:
            enabled: 1 for on, 0 for off
            
        Returns:
            dict: {"success": bool, "message": str}
        """
        try:
            self.client.send_message("/live/song/set/loop", [enabled])
            state_str = "enabled" if enabled == 1 else "disabled"
            return {"success": True, "message": f"Loop {state_str}"}
        except Exception as e:
            return {"success": False, "message": f"Failed to set loop: {e}"}
    
    def set_loop_start(self, beat):
        """
        Set loop start position
        
        Args:
            beat: Start position in beats
            
        Returns:
            dict: {"success": bool, "message": str}
        """
        try:
            self.client.send_message("/live/song/set/loop_start", [float(beat)])
            return {"success": True, "message": f"Loop start set to beat {beat}"}
        except Exception as e:
            return {"success": False, "message": f"Failed to set loop start: {e}"}
    
    def set_loop_length(self, beats):
        """
        Set loop length
        
        Args:
            beats: Length in beats
            
        Returns:
            dict: {"success": bool, "message": str}
        """
        try:
            self.client.send_message("/live/song/set/loop_length", [float(beats)])
            return {"success": True, "message": f"Loop length set to {beats} beats"}
        except Exception as e:
            return {"success": False, "message": f"Failed to set loop length: {e}"}
    
    # ==================== TRACK CONTROLS ====================
    # CRITICAL: Track indices are 0-based (Track 1 = index 0)
    # CRITICAL: Track ID is a PARAMETER, not part of the path!
    # Format: /live/track/set/property [track_id, value]
    
    def mute_track(self, track_index, muted, verify=False):
        """
        Mute/unmute a track

        Args:
            track_index: Track index (0-based, so Track 1 = 0)
            muted: 1 for muted, 0 for unmuted
            verify: If True, read back the value to confirm it was set

        Returns:
            dict: {"success": bool, "message": str, ...}
        """
        try:
            if verify:
                return self._verified_set(
                    "/live/track/set/mute", [track_index, muted],
                    "/live/track/get/mute", [track_index],
                    muted, "muted")
            # CORRECT FORMAT: /live/track/set/mute [track_id, mute_value]
            self.client.send_message("/live/track/set/mute", [track_index, muted])
            state_str = "muted" if muted == 1 else "unmuted"
            return {"success": True, "message": f"Track {track_index + 1} {state_str}"}
        except Exception as e:
            return {"success": False, "message": f"Failed to mute track: {e}"}
    
    def solo_track(self, track_index, soloed, verify=False):
        """
        Solo/unsolo a track

        Args:
            track_index: Track index (0-based, so Track 1 = 0)
            soloed: 1 for soloed, 0 for unsoloed
            verify: If True, read back the value to confirm it was set

        Returns:
            dict: {"success": bool, "message": str, ...}
        """
        try:
            if verify:
                return self._verified_set(
                    "/live/track/set/solo", [track_index, soloed],
                    "/live/track/get/solo", [track_index],
                    soloed, "soloed")
            # CORRECT FORMAT: /live/track/set/solo [track_id, solo_value]
            self.client.send_message("/live/track/set/solo", [track_index, soloed])
            state_str = "soloed" if soloed == 1 else "unsoloed"
            return {"success": True, "message": f"Track {track_index + 1} {state_str}"}
        except Exception as e:
            return {"success": False, "message": f"Failed to solo track: {e}"}
    
    def arm_track(self, track_index, armed, verify=False):
        """
        Arm/disarm a track for recording

        Args:
            track_index: Track index (0-based, so Track 1 = 0)
            armed: 1 for armed, 0 for disarmed
            verify: If True, read back the value to confirm it was set

        Returns:
            dict: {"success": bool, "message": str, ...}
        """
        try:
            if verify:
                return self._verified_set(
                    "/live/track/set/arm", [track_index, armed],
                    "/live/track/get/arm", [track_index],
                    armed, "armed")
            # CORRECT FORMAT: /live/track/set/arm [track_id, arm_value]
            self.client.send_message("/live/track/set/arm", [track_index, armed])
            state_str = "armed" if armed == 1 else "disarmed"
            return {"success": True, "message": f"Track {track_index + 1} {state_str}"}
        except Exception as e:
            return {"success": False, "message": f"Failed to arm track: {e}"}

    def get_track_mute(self, track_index):
        """
        Get track mute status

        Args:
            track_index: Track index (0-based, so Track 1 = 0)

        Returns:
            dict: {"success": bool, "muted": bool (or None), "message": str}
        """
        try:
            response = self._send_and_wait("/live/track/get/mute", [track_index], timeout=2.0)

            if response:
                address, args = response
                if args and len(args) > 0:
                    muted = bool(args[0])
                    return {
                        "success": True,
                        "muted": muted,
                        "message": f"Track {track_index + 1} is {'muted' if muted else 'unmuted'}"
                    }
                else:
                    return {"success": False, "muted": None, "message": "Empty response from Ableton"}
            else:
                return {"success": False, "muted": None, "message": "No response from Ableton (timeout)"}
        except Exception as e:
            return {"success": False, "muted": None, "message": f"Failed to query track mute: {e}"}

    def get_track_solo(self, track_index):
        """
        Get track solo status

        Args:
            track_index: Track index (0-based, so Track 1 = 0)

        Returns:
            dict: {"success": bool, "soloed": bool (or None), "message": str}
        """
        try:
            response = self._send_and_wait("/live/track/get/solo", [track_index], timeout=2.0)

            if response:
                address, args = response
                if args and len(args) > 0:
                    soloed = bool(args[0])
                    return {
                        "success": True,
                        "soloed": soloed,
                        "message": f"Track {track_index + 1} is {'soloed' if soloed else 'not soloed'}"
                    }
                else:
                    return {"success": False, "soloed": None, "message": "Empty response from Ableton"}
            else:
                return {"success": False, "soloed": None, "message": "No response from Ableton (timeout)"}
        except Exception as e:
            return {"success": False, "soloed": None, "message": f"Failed to query track solo: {e}"}

    def get_track_arm(self, track_index):
        """
        Get track arm status

        Args:
            track_index: Track index (0-based, so Track 1 = 0)

        Returns:
            dict: {"success": bool, "armed": bool (or None), "message": str}
        """
        try:
            response = self._send_and_wait("/live/track/get/arm", [track_index], timeout=2.0)

            if response:
                address, args = response
                if args and len(args) > 0:
                    armed = bool(args[0])
                    return {
                        "success": True,
                        "armed": armed,
                        "message": f"Track {track_index + 1} is {'armed' if armed else 'not armed'}"
                    }
                else:
                    return {"success": False, "armed": None, "message": "Empty response from Ableton"}
            else:
                return {"success": False, "armed": None, "message": "No response from Ableton (timeout)"}
        except Exception as e:
            return {"success": False, "armed": None, "message": f"Failed to query track arm: {e}"}

    def set_track_volume(self, track_index, volume, verify=False):
        """
        Set track volume

        Args:
            track_index: Track index (0-based, so Track 1 = 0)
            volume: Volume level (0.0 to 1.0)
            verify: If True, read back the value to confirm it was set

        Returns:
            dict: {"success": bool, "message": str, ...}
        """
        try:
            if not 0.0 <= volume <= 1.0:
                return {"success": False, "message": "Volume must be between 0.0 and 1.0"}

            if verify:
                return self._verified_set(
                    "/live/track/set/volume", [track_index, float(volume)],
                    "/live/track/get/volume", [track_index],
                    float(volume), "volume")
            # CORRECT FORMAT: /live/track/set/volume [track_id, volume_value]
            self.client.send_message("/live/track/set/volume", [track_index, float(volume)])
            return {"success": True, "message": f"Track {track_index + 1} volume set to {volume:.2f}"}
        except Exception as e:
            return {"success": False, "message": f"Failed to set track volume: {e}"}

    def get_track_volume(self, track_index):
        """
        Get track volume level

        Args:
            track_index: Track index (0-based, so Track 1 = 0)

        Returns:
            dict: {"success": bool, "volume": float|None, "message": str}
        """
        try:
            response = self._send_and_wait("/live/track/get/volume", [track_index], timeout=2.0)

            if response:
                address, args = response
                if args and len(args) > 0:
                    # Response may be [track_id, volume] or [volume]
                    value = float(args[-1]) if isinstance(args[-1], (int, float)) else None
                    if value is not None:
                        return {
                            "success": True,
                            "volume": value,
                            "message": f"Track {track_index + 1} volume is {value:.2f}"
                        }
                return {"success": False, "volume": None, "message": "Empty response from Ableton"}
            else:
                return {"success": False, "volume": None, "message": "No response from Ableton (timeout)"}
        except Exception as e:
            return {"success": False, "volume": None, "message": f"Failed to query track volume: {e}"}

    def set_track_pan(self, track_index, pan, verify=False):
        """
        Set track pan

        Args:
            track_index: Track index (0-based, so Track 1 = 0)
            pan: Pan value (-1.0 left to 1.0 right, 0.0 center)
            verify: If True, read back the value to confirm it was set

        Returns:
            dict: {"success": bool, "message": str, ...}
        """
        try:
            if not -1.0 <= pan <= 1.0:
                return {"success": False, "message": "Pan must be between -1.0 and 1.0"}

            if verify:
                return self._verified_set(
                    "/live/track/set/panning", [track_index, float(pan)],
                    "/live/track/get/panning", [track_index],
                    float(pan), "pan")
            # CORRECT FORMAT: /live/track/set/panning [track_id, pan_value]
            self.client.send_message("/live/track/set/panning", [track_index, float(pan)])
            return {"success": True, "message": f"Track {track_index + 1} pan set to {pan:.2f}"}
        except Exception as e:
            return {"success": False, "message": f"Failed to set track pan: {e}"}

    def get_track_pan(self, track_index):
        """
        Get track pan position

        Args:
            track_index: Track index (0-based, so Track 1 = 0)

        Returns:
            dict: {"success": bool, "pan": float|None, "message": str}
        """
        try:
            response = self._send_and_wait("/live/track/get/panning", [track_index], timeout=2.0)

            if response:
                address, args = response
                if args and len(args) > 0:
                    value = float(args[-1]) if isinstance(args[-1], (int, float)) else None
                    if value is not None:
                        return {
                            "success": True,
                            "pan": value,
                            "message": f"Track {track_index + 1} pan is {value:.2f}"
                        }
                return {"success": False, "pan": None, "message": "Empty response from Ableton"}
            else:
                return {"success": False, "pan": None, "message": "No response from Ableton (timeout)"}
        except Exception as e:
            return {"success": False, "pan": None, "message": f"Failed to query track pan: {e}"}

    def set_track_send(self, track_index, send_index, level, verify=False):
        """
        Set track send level

        Args:
            track_index: Track index (0-based, so Track 1 = 0)
            send_index: Send index (0-based)
            level: Send level (0.0 to 1.0)
            verify: If True, read back the value to confirm it was set

        Returns:
            dict: {"success": bool, "message": str, ...}
        """
        try:
            if not 0.0 <= level <= 1.0:
                return {"success": False, "message": "Send level must be between 0.0 and 1.0"}

            if verify:
                return self._verified_set(
                    "/live/track/set/send", [track_index, send_index, float(level)],
                    "/live/track/get/send", [track_index, send_index],
                    float(level), "level")
            # CORRECT FORMAT: /live/track/set/send [track_id, send_id, value]
            self.client.send_message("/live/track/set/send", [track_index, send_index, float(level)])
            return {"success": True, "message": f"Track {track_index + 1} send {send_index + 1} set to {level:.2f}"}
        except Exception as e:
            return {"success": False, "message": f"Failed to set track send: {e}"}

    def get_track_send(self, track_index, send_index):
        """
        Get track send level

        Args:
            track_index: Track index (0-based, so Track 1 = 0)
            send_index: Send index (0-based)

        Returns:
            dict: {"success": bool, "level": float|None, "message": str}
        """
        try:
            response = self._send_and_wait("/live/track/get/send", [track_index, send_index], timeout=2.0)

            if response:
                address, args = response
                if args and len(args) > 0:
                    value = float(args[-1]) if isinstance(args[-1], (int, float)) else None
                    if value is not None:
                        return {
                            "success": True,
                            "level": value,
                            "message": f"Track {track_index + 1} send {send_index + 1} level is {value:.2f}"
                        }
                return {"success": False, "level": None, "message": "Empty response from Ableton"}
            else:
                return {"success": False, "level": None, "message": "No response from Ableton (timeout)"}
        except Exception as e:
            return {"success": False, "level": None, "message": f"Failed to query track send: {e}"}

    # ==================== SCENE CONTROLS ====================
    
    def fire_scene(self, scene_index):
        """
        Fire a scene (launch all clips in the scene)
        
        Args:
            scene_index: Scene index (0-based)
            
        Returns:
            dict: {"success": bool, "message": str}
        """
        try:
            # CORRECT FORMAT: /live/scene/fire [scene_id]
            self.client.send_message("/live/scene/fire", [scene_index])
            return {"success": True, "message": f"Scene {scene_index + 1} fired"}
        except Exception as e:
            return {"success": False, "message": f"Failed to fire scene: {e}"}
    
    # ==================== CLIP CONTROLS ====================
    
    def fire_clip(self, track_index, clip_index):
        """
        Fire a clip (launch it)
        
        Args:
            track_index: Track index (0-based, so Track 1 = 0)
            clip_index: Clip slot index (0-based)
            
        Returns:
            dict: {"success": bool, "message": str}
        """
        try:
            # CORRECT FORMAT: /live/clip/fire [track_id, clip_id]
            self.client.send_message("/live/clip/fire", [track_index, clip_index])
            return {"success": True, "message": f"Clip fired on track {track_index + 1}, slot {clip_index + 1}"}
        except Exception as e:
            return {"success": False, "message": f"Failed to fire clip: {e}"}
    
    def stop_clip(self, track_index):
        """
        Stop all clips on a track
        
        Args:
            track_index: Track index (0-based, so Track 1 = 0)
            
        Returns:
            dict: {"success": bool, "message": str}
        """
        try:
            # CORRECT FORMAT: /live/track/stop_all_clips [track_id]
            self.client.send_message("/live/track/stop_all_clips", [track_index])
            return {"success": True, "message": f"All clips stopped on track {track_index + 1}"}
        except Exception as e:
            return {"success": False, "message": f"Failed to stop clips: {e}"}
    
    def stop_all_clips(self):
        """
        Stop all clips in the session
        
        Returns:
            dict: {"success": bool, "message": str}
        """
        try:
            self.client.send_message("/live/song/stop_all_clips", [])
            return {"success": True, "message": "All clips stopped"}
        except Exception as e:
            return {"success": False, "message": f"Failed to stop all clips: {e}"}
    
    # ==================== DEVICE CONTROLS ====================
    # Query and control devices (plugins/effects/instruments) on tracks
    # IMPORTANT: Device indices are 0-based (first device = 0)
    
    def get_num_devices(self, track_index):
        """
        Get the number of devices on a track
        
        Args:
            track_index: Track index (0-based)
            
        Returns:
            dict: {"success": bool, "message": str}
        """
        try:
            self.client.send_message("/live/track/get/num_devices", [track_index])
            return {"success": True, "message": f"Requested device count for track {track_index + 1}"}
        except Exception as e:
            return {"success": False, "message": f"Failed to get device count: {e}"}

    def get_num_devices_sync(self, track_index: int, timeout: float = 2.0) -> Dict[str, Any]:
        """
        Get the number of devices on a track (request/response via port 11001).

        Returns:
            dict: {"success": bool, "count": int, "message": str}
        """
        resp = self._send_and_wait("/live/track/get/num_devices", [track_index], timeout=timeout)
        if not resp:
            return {"success": False, "count": 0, "message": "No response (is AbletonOSC sending replies to port 11001?)"}

        _addr, args = resp
        # Common formats:
        # - [track_id, num_devices]
        # - [num_devices]
        count = None
        if len(args) >= 2 and isinstance(args[0], int) and args[0] == track_index and isinstance(args[1], int):
            count = args[1]
        elif len(args) >= 1 and isinstance(args[0], int):
            count = args[0]

        if count is None:
            return {"success": False, "count": 0, "message": f"Unexpected response args: {args}"}

        return {"success": True, "count": int(count), "message": f"Track {track_index + 1} has {count} devices"}
    
    def get_track_devices(self, track_index):
        """
        Get all device names on a track
        
        Args:
            track_index: Track index (0-based)
            
        Returns:
            dict: {"success": bool, "message": str}
        """
        try:
            self.client.send_message("/live/track/get/devices/name", [track_index])
            return {"success": True, "message": f"Requested device names for track {track_index + 1}"}
        except Exception as e:
            return {"success": False, "message": f"Failed to get device names: {e}"}

    def get_track_devices_sync(self, track_index: int, timeout: float = 2.0) -> Dict[str, Any]:
        """
        Get all device names on a track (request/response).

        Returns:
            dict: {"success": bool, "devices": list[str], "message": str}
        """
        resp = self._send_and_wait("/live/track/get/devices/name", [track_index], timeout=timeout)
        if not resp:
            return {"success": False, "devices": [], "message": "No response"}

        _addr, args = resp
        # Common formats:
        # - [track_id, "Dev1", "Dev2", ...]
        # - ["Dev1", "Dev2", ...]
        if len(args) >= 1 and isinstance(args[0], int) and args[0] == track_index:
            names = [a for a in args[1:] if isinstance(a, str)]
        else:
            names = [a for a in args if isinstance(a, str)]

        return {"success": True, "devices": names, "count": len(names), "message": f"Found {len(names)} devices"}
    
    def get_device_name(self, track_index, device_index):
        """
        Get a specific device's name
        
        Args:
            track_index: Track index (0-based)
            device_index: Device index on track (0-based)
            
        Returns:
            dict: {"success": bool, "message": str}
        """
        try:
            self.client.send_message("/live/device/get/name", [track_index, device_index])
            return {"success": True, "message": f"Requested name for device {device_index + 1} on track {track_index + 1}"}
        except Exception as e:
            return {"success": False, "message": f"Failed to get device name: {e}"}
    
    def get_device_name_sync(self, track_index: int, device_index: int, timeout: float = 2.0) -> Dict[str, Any]:
        """
        Get a specific device's name (request/response).

        Returns:
            dict: {"success": bool, "name": str, "message": str}
        """
        resp = self._send_and_wait(
            "/live/device/get/name", [track_index, device_index], timeout=timeout
        )
        if not resp:
            return {"success": False, "name": "", "message": "No response"}

        _addr, args = resp
        # Response format: [track_id, device_id, name] or [name]
        name = ""
        if len(args) >= 3 and isinstance(args[2], str):
            name = args[2]
        elif len(args) >= 1 and isinstance(args[-1], str):
            name = args[-1]

        if not name:
            return {"success": False, "name": "", "message": f"Unexpected response: {args}"}

        return {"success": True, "name": name, "message": f"Device name: {name}"}

    def select_device(self, track_index: int, device_index: int) -> Dict[str, Any]:
        """
        Select a device to show it in Ableton's Detail View.

        Sends OSC to JarvisDeviceLoader on port 11002.

        Args:
            track_index: 0-based track index
            device_index: 0-based device index on track

        Returns:
            dict: {"success": bool, "message": str}
        """
        import socket
        import struct

        try:
            address = "/jarvis/device/select"

            addr_bytes = address.encode('utf-8') + b'\x00'
            addr_padded = addr_bytes + b'\x00' * ((4 - len(addr_bytes) % 4) % 4)

            type_tag = ',ii'
            type_bytes = type_tag.encode('utf-8') + b'\x00'
            type_padded = type_bytes + b'\x00' * ((4 - len(type_bytes) % 4) % 4)

            arg_data = struct.pack('>i', track_index) + struct.pack('>i', device_index)

            message = addr_padded + type_padded + arg_data

            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(5.0)
            sock.bind(('127.0.0.1', 11003))
            sock.sendto(message, ('127.0.0.1', 11002))

            data, addr = sock.recvfrom(65535)
            sock.close()

            return {"success": True, "message": f"Device {device_index} on track {track_index} selected in Detail View"}

        except socket.timeout:
            return {"success": False, "message": "Timeout: JarvisDeviceLoader not responding"}
        except Exception as e:
            return {"success": False, "message": f"OSC error: {e}"}

    def get_device_class_name(self, track_index, device_index):
        """
        Get device class name (e.g., "Reverb", "Compressor", "Operator")
        
        Args:
            track_index: Track index (0-based)
            device_index: Device index on track (0-based)
            
        Returns:
            dict: {"success": bool, "message": str}
        """
        try:
            self.client.send_message("/live/device/get/class_name", [track_index, device_index])
            return {"success": True, "message": f"Requested class name for device {device_index + 1} on track {track_index + 1}"}
        except Exception as e:
            return {"success": False, "message": f"Failed to get device class name: {e}"}
    
    def get_device_type(self, track_index, device_index):
        """
        Get device type (1=audio_effect, 2=instrument, 4=midi_effect)
        
        Args:
            track_index: Track index (0-based)
            device_index: Device index on track (0-based)
            
        Returns:
            dict: {"success": bool, "message": str}
        """
        try:
            self.client.send_message("/live/device/get/type", [track_index, device_index])
            return {"success": True, "message": f"Requested type for device {device_index + 1} on track {track_index + 1}"}
        except Exception as e:
            return {"success": False, "message": f"Failed to get device type: {e}"}
    
    def get_device_parameters(self, track_index, device_index):
        """
        Get device parameter names (query only)
        
        Args:
            track_index: Track index (0-based)
            device_index: Device index on track (0-based)
            
        Returns:
            dict: {"success": bool, "message": str}
        """
        try:
            self.client.send_message("/live/device/get/parameters/name", [track_index, device_index])
            return {"success": True, "message": f"Requested parameters for device {device_index + 1} on track {track_index + 1}"}
        except Exception as e:
            return {"success": False, "message": f"Failed to get device parameters: {e}"}

    def get_device_parameters_name_sync(self, track_index: int, device_index: int, timeout: float = 3.0) -> Dict[str, Any]:
        """
        Get device parameter names (request/response).

        Returns:
            dict: {"success": bool, "names": list[str], "message": str}
        """
        resp = self._send_and_wait("/live/device/get/parameters/name", [track_index, device_index], timeout=timeout)
        if not resp:
            return {"success": False, "names": [], "message": "No response"}

        _addr, args = resp
        # Common formats:
        # - [track_id, device_id, "Param1", "Param2", ...]
        # - ["Param1", "Param2", ...]
        start = 0
        if len(args) >= 2 and isinstance(args[0], int) and isinstance(args[1], int):
            start = 2
        names = [a for a in args[start:] if isinstance(a, str)]
        return {"success": True, "names": names, "count": len(names), "message": f"Found {len(names)} parameters"}
    
    def get_device_parameter_value(self, track_index, device_index, param_index):
        """
        Get a specific device parameter value
        
        Args:
            track_index: Track index (0-based)
            device_index: Device index on track (0-based)
            param_index: Parameter index (0-based)
            
        Returns:
            dict: {"success": bool, "message": str}
        """
        try:
            self.client.send_message("/live/device/get/parameter/value", [track_index, device_index, param_index])
            return {"success": True, "message": f"Requested value for parameter {param_index} on device {device_index + 1}"}
        except Exception as e:
            return {"success": False, "message": f"Failed to get parameter value: {e}"}

    def get_device_parameter_value_sync(
        self,
        track_index: int,
        device_index: int,
        param_index: int,
        timeout: float = 2.0,
    ) -> Dict[str, Any]:
        """
        Get a specific device parameter value (request/response).

        Returns:
            dict: {"success": bool, "value": float|None, "message": str}
        """
        resp = self._send_and_wait(
            "/live/device/get/parameter/value",
            [track_index, device_index, param_index],
            timeout=timeout,
        )
        if not resp:
            return {"success": False, "value": None, "message": "No response"}

        _addr, args = resp
        for arg in reversed(args):
            if isinstance(arg, (int, float)):
                return {"success": True, "value": float(arg), "message": "ok"}
        return {"success": False, "value": None, "message": f"Unexpected response: {args}"}

    def get_device_parameter_value_string_sync(
        self,
        track_index: int,
        device_index: int,
        param_index: int,
        timeout: float = 2.0,
    ) -> Dict[str, Any]:
        """
        Get a specific device parameter display string (request/response).

        Uses AbletonOSC path `/live/device/get/parameter/value_string` when
        available. If the bridge does not support this endpoint, it falls back
        to returning the numeric value as a string.

        Returns:
            dict: {"success": bool, "value_string": str, "message": str}
        """
        addr = "/live/device/get/parameter/value_string"
        resp = self._send_and_wait(
            addr,
            [track_index, device_index, param_index],
            timeout=timeout,
            accept_addresses=[
                addr,
                f"{addr}/response",
                "/live/device/get/parameter/value",
                "/live/device/get/parameter/value/response",
            ],
        )
        if resp:
            _resp_addr, args = resp
            for arg in reversed(args):
                if isinstance(arg, str):
                    return {"success": True, "value_string": arg, "message": "ok"}
            for arg in reversed(args):
                if isinstance(arg, (int, float)):
                    return {"success": True, "value_string": str(arg), "message": "ok (numeric fallback)"}

        numeric = self.get_device_parameter_value_sync(
            track_index, device_index, param_index, timeout=timeout
        )
        if numeric.get("success"):
            return {
                "success": True,
                "value_string": str(numeric.get("value")),
                "message": "numeric fallback",
            }
        return {"success": False, "value_string": "", "message": "No response"}
    
    def get_device_parameters_values(self, track_index, device_index):
        """
        Get all device parameter values at once
        
        Args:
            track_index: Track index (0-based)
            device_index: Device index on track (0-based)
            
        Returns:
            dict: {"success": bool, "message": str}
        """
        try:
            self.client.send_message("/live/device/get/parameters/value", [track_index, device_index])
            return {"success": True, "message": f"Requested all parameter values for device {device_index + 1} on track {track_index + 1}"}
        except Exception as e:
            return {"success": False, "message": f"Failed to get parameter values: {e}"}
    
    def get_device_parameters_min(self, track_index, device_index):
        """
        Get minimum values for all device parameters
        
        Args:
            track_index: Track index (0-based)
            device_index: Device index on track (0-based)
            
        Returns:
            dict: {"success": bool, "message": str}
        """
        try:
            self.client.send_message("/live/device/get/parameters/min", [track_index, device_index])
            return {"success": True, "message": f"Requested min values for device {device_index + 1} on track {track_index + 1}"}
        except Exception as e:
            return {"success": False, "message": f"Failed to get parameter min values: {e}"}
    
    def get_device_parameters_max(self, track_index, device_index):
        """
        Get maximum values for all device parameters
        
        Args:
            track_index: Track index (0-based)
            device_index: Device index on track (0-based)
            
        Returns:
            dict: {"success": bool, "message": str}
        """
        try:
            self.client.send_message("/live/device/get/parameters/max", [track_index, device_index])
            return {"success": True, "message": f"Requested max values for device {device_index + 1} on track {track_index + 1}"}
        except Exception as e:
            return {"success": False, "message": f"Failed to get parameter max values: {e}"}

    def get_device_parameters_minmax_sync(self,
                                          track_index: int,
                                          device_index: int,
                                          timeout: float = 3.0,
                                          cache_ttl_s: float = 30.0) -> Dict[str, Any]:
        """
        Get min/max arrays for all parameters (request/response) and cache them.

        Returns:
            dict: {"success": bool, "mins": list[float], "maxs": list[float], "message": str}
        """
        cache_key = (track_index, device_index)
        now = time.time()
        if cache_key in self._param_range_cache:
            mins, maxs, ts = self._param_range_cache[cache_key]
            if now - ts <= cache_ttl_s and mins and maxs:
                return {"success": True, "mins": mins, "maxs": maxs, "message": "Using cached min/max"}

        resp_min = self._send_and_wait("/live/device/get/parameters/min", [track_index, device_index], timeout=timeout)
        resp_max = self._send_and_wait("/live/device/get/parameters/max", [track_index, device_index], timeout=timeout)
        if not resp_min or not resp_max:
            return {"success": False, "mins": [], "maxs": [], "message": "No response for min/max"}

        _addr_min, args_min = resp_min
        _addr_max, args_max = resp_max

        # Strip optional leading track/device ids
        def _strip_prefix(args: List[Any]) -> List[Any]:
            if len(args) >= 2 and isinstance(args[0], int) and isinstance(args[1], int):
                return args[2:]
            return args

        raw_mins = _strip_prefix(args_min)
        raw_maxs = _strip_prefix(args_max)

        mins = [float(x) for x in raw_mins if isinstance(x, (int, float))]
        maxs = [float(x) for x in raw_maxs if isinstance(x, (int, float))]

        if not mins or not maxs:
            return {"success": False, "mins": [], "maxs": [], "message": f"Unexpected min/max response: {args_min} / {args_max}"}

        # Cache
        self._param_range_cache[cache_key] = (mins, maxs, now)
        return {"success": True, "mins": mins, "maxs": maxs, "message": f"Fetched min/max for {min(len(mins), len(maxs))} params"}

    def safe_set_device_parameter(self,
                                  track_index: int,
                                  device_index: int,
                                  param_index: int,
                                  value: float,
                                  timeout: float = 3.0) -> Dict[str, Any]:
        """
        Set a device parameter, clamping value to the true min/max range when available.

        This prevents AbletonOSC RuntimeError: Invalid value (which can destabilize the session).
        """
        # Best-effort: fetch min/max; if unavailable, apply heuristic scaling.
        minmax = self.get_device_parameters_minmax_sync(track_index, device_index, timeout=timeout)

        original_v = float(value)
        v = original_v
        clamped = False
        pmin = None
        pmax = None
        if minmax.get("success"):
            mins: List[float] = minmax["mins"]
            maxs: List[float] = minmax["maxs"]
            if param_index < 0 or param_index >= min(len(mins), len(maxs)):
                return {"success": False, "message": f"Param index {param_index} out of range (have {min(len(mins), len(maxs))})"}
            pmin = mins[param_index]
            pmax = maxs[param_index]

            # Percent-to-normalized heuristic (common for Dry/Wet when some devices report 0..1)
            if pmin >= 0.0 and pmax <= 1.0 and v > 1.0:
                if v <= 100.0:
                    v = v / 100.0
                else:
                    v = 1.0
                clamped = True

            # Clamp to range
            if v < pmin:
                v = pmin
                clamped = True
            if v > pmax:
                v = pmax
                clamped = True
        else:
            # If we don't know the range, avoid obviously dangerous values for normalized params
            if v > 1.0 and v <= 100.0:
                # conservative: many params are 0..1; try scaling
                v = v / 100.0
                clamped = True
        result = self.set_device_parameter(track_index, device_index, param_index, v)
        # Enrich for debugging
        result.setdefault("original_value", original_v)
        result.setdefault("sent_value", v)
        result.setdefault("clamped", clamped)
        if pmin is not None and pmax is not None:
            result.setdefault("min", pmin)
            result.setdefault("max", pmax)
        return result
    
    def set_device_parameter(self, track_index, device_index, param_index, value):
        """
        Set a device parameter value
        
        Args:
            track_index: Track index (0-based)
            device_index: Device index on track (0-based)
            param_index: Parameter index (0-based)
            value: Parameter value (float)
            
        Returns:
            dict: {"success": bool, "message": str}
        """
        try:
            self.client.send_message("/live/device/set/parameter/value", 
                                     [track_index, device_index, param_index, float(value)])
            return {"success": True, "message": f"Set parameter {param_index} on device {device_index + 1} to {value}"}
        except Exception as e:
            return {"success": False, "message": f"Failed to set device parameter: {e}"}
    
    def set_device_parameters_bulk(self, track_index, device_index, values):
        """
        Set multiple device parameters at once
        
        Args:
            track_index: Track index (0-based)
            device_index: Device index on track (0-based)
            values: List of parameter values (in order)
            
        Returns:
            dict: {"success": bool, "message": str}
        """
        try:
            # Build message with track, device, then all values
            params = [track_index, device_index] + [float(v) for v in values]
            self.client.send_message("/live/device/set/parameters/value", params)
            return {"success": True, "message": f"Set {len(values)} parameters on device {device_index + 1}"}
        except Exception as e:
            return {"success": False, "message": f"Failed to set device parameters: {e}"}
    
    def set_device_parameters_batch(self, track_index: int, device_index: int,
                                     params: Dict[int, float],
                                     inter_delay: float = 0.03) -> Dict[str, Any]:
        """
        Set multiple device parameters individually with small delays between sends.

        Unlike set_device_parameters_bulk (which sends all values in one OSC message),
        this method sends each parameter as a separate safe_set_device_parameter call
        with a configurable delay to avoid overwhelming the OSC bridge.

        Args:
            track_index: Track index (0-based)
            device_index: Device index on track (0-based)
            params: Dict mapping param_index -> value
            inter_delay: Seconds to wait between parameter sends

        Returns:
            dict with applied/failed lists
        """
        import time as _time
        applied = []
        failed = []

        for param_index, value in params.items():
            result = self.safe_set_device_parameter(track_index, device_index,
                                                     int(param_index), float(value))
            entry = {"param_index": int(param_index), "value": float(value)}
            if result.get("success"):
                applied.append(entry)
            else:
                entry["error"] = result.get("message", "unknown")
                failed.append(entry)
            _time.sleep(inter_delay)

        return {
            "success": len(failed) == 0,
            "applied": applied,
            "failed": failed,
            "message": f"Set {len(applied)}/{len(applied)+len(failed)} parameters on device {device_index + 1}"
        }

    def set_device_enabled(self, track_index, device_index, enabled):
        """
        Enable or disable (bypass) a device
        
        Args:
            track_index: Track index (0-based)
            device_index: Device index on track (0-based)
            enabled: 1 for enabled, 0 for bypassed
            
        Returns:
            dict: {"success": bool, "message": str}
        """
        try:
            # Device on/off is typically parameter 0 on most devices
            self.client.send_message("/live/device/set/parameter/value", 
                                     [track_index, device_index, 0, enabled])
            state_str = "enabled" if enabled == 1 else "bypassed"
            return {"success": True, "message": f"Device {device_index + 1} on track {track_index + 1} {state_str}"}
        except Exception as e:
            return {"success": False, "message": f"Failed to set device state: {e}"}
    
    # ==================== TRACK MANAGEMENT ====================
    # Create, delete, duplicate, and rename tracks
    
    def create_audio_track(self, index=-1, name=None):
        """
        Create a new audio track
        
        Args:
            index: Position to insert track (-1 = end of list, 0 = first position)
            name: Optional track name to apply after creation
            
        Returns:
            dict: {"success": bool, "message": str}
        """
        try:
            track_index = None
            before = self.get_track_list()
            if before.get("success"):
                before_count = len(before.get("tracks", []))
                track_index = before_count if index == -1 else int(index)

            self.client.send_message("/live/song/create_audio_track", [index])
            position = "at end" if index == -1 else f"at position {index + 1}"
            if name and track_index is not None:
                time.sleep(0.1)
                rename_result = self.set_track_name(track_index, name)
                if not rename_result.get("success"):
                    return {
                        "success": False,
                        "track_index": track_index,
                        "message": rename_result.get(
                            "message",
                            f"Audio track created {position}, but rename failed",
                        ),
                    }
            return {
                "success": True,
                "track_index": track_index,
                "message": f"Audio track created {position}",
            }
        except Exception as e:
            return {"success": False, "message": f"Failed to create audio track: {e}"}

    def set_clip_path(self, track_index, clip_index, audio_path):
        """
        Place a local audio file into a Session clip slot.

        This is intentionally not faked: stock AbletonOSC in this repo does not
        currently expose clip import from an arbitrary file path, and
        JarvisDeviceLoader only handles device loading.
        """
        raise NotImplementedError(
            "set_clip_path requires a Live clip-import endpoint in AbletonOSC "
            "or JarvisDeviceLoader; no reachable bridge endpoint exists yet."
        )

    def get_clip_audio_path(self, track_index, clip_index):
        """
        Return the backing file path for an audio clip.

        This needs Live's clip API exposed through a remote script. The current
        AbletonOSC/JarvisDeviceLoader bridge does not provide it.
        """
        raise NotImplementedError(
            "get_clip_audio_path requires clip.file_path exposure through "
            "AbletonOSC or JarvisDeviceLoader; no reachable endpoint exists yet."
        )

    def set_clip_detune(self, track_index, clip_index, cents):
        """
        Detune an audio clip in cents.

        Stubbed until the bridge exposes clip-level pitch controls.
        """
        raise NotImplementedError(
            "set_clip_detune requires clip-level pitch controls through "
            "AbletonOSC or JarvisDeviceLoader; no reachable endpoint exists yet."
        )
    
    def create_midi_track(self, index=-1):
        """
        Create a new MIDI track
        
        Args:
            index: Position to insert track (-1 = end of list, 0 = first position)
            
        Returns:
            dict: {"success": bool, "message": str}
        """
        try:
            self.client.send_message("/live/song/create_midi_track", [index])
            position = "at end" if index == -1 else f"at position {index + 1}"
            return {"success": True, "message": f"MIDI track created {position}"}
        except Exception as e:
            return {"success": False, "message": f"Failed to create MIDI track: {e}"}
    
    def create_return_track(self):
        """
        Create a new return track
        
        Returns:
            dict: {"success": bool, "message": str}
        """
        try:
            self.client.send_message("/live/song/create_return_track", [])
            return {"success": True, "message": "Return track created"}
        except Exception as e:
            return {"success": False, "message": f"Failed to create return track: {e}"}
    
    def delete_track(self, track_index):
        """
        Delete a track
        
        Args:
            track_index: Track index (0-based, so Track 1 = 0)
            
        Returns:
            dict: {"success": bool, "message": str}
        """
        try:
            self.client.send_message("/live/song/delete_track", [track_index])
            return {"success": True, "message": f"Track {track_index + 1} deleted"}
        except Exception as e:
            return {"success": False, "message": f"Failed to delete track: {e}"}
    
    def delete_return_track(self, track_index):
        """
        Delete a return track
        
        Args:
            track_index: Return track index (0-based, so Return A = 0)
            
        Returns:
            dict: {"success": bool, "message": str}
        """
        try:
            self.client.send_message("/live/song/delete_return_track", [track_index])
            return {"success": True, "message": f"Return track {track_index + 1} deleted"}
        except Exception as e:
            return {"success": False, "message": f"Failed to delete return track: {e}"}
    
    def duplicate_track(self, track_index):
        """
        Duplicate a track
        
        Args:
            track_index: Track index (0-based, so Track 1 = 0)
            
        Returns:
            dict: {"success": bool, "message": str}
        """
        try:
            self.client.send_message("/live/song/duplicate_track", [track_index])
            return {"success": True, "message": f"Track {track_index + 1} duplicated"}
        except Exception as e:
            return {"success": False, "message": f"Failed to duplicate track: {e}"}
    
    def set_track_name(self, track_index, name):
        """
        Set/rename a track
        
        Args:
            track_index: Track index (0-based, so Track 1 = 0)
            name: New track name
            
        Returns:
            dict: {"success": bool, "message": str}
        """
        try:
            self.client.send_message("/live/track/set/name", [track_index, name])
            return {"success": True, "message": f"Track {track_index + 1} renamed to '{name}'"}
        except Exception as e:
            return {"success": False, "message": f"Failed to rename track: {e}"}
    
    def set_track_color(self, track_index, color_index):
        """
        Set track color
        
        Args:
            track_index: Track index (0-based, so Track 1 = 0)
            color_index: Color index (0-69 in Ableton's color palette)
            
        Returns:
            dict: {"success": bool, "message": str}
        """
        try:
            self.client.send_message("/live/track/set/color_index", [track_index, color_index])
            return {"success": True, "message": f"Track {track_index + 1} color set to index {color_index}"}
        except Exception as e:
            return {"success": False, "message": f"Failed to set track color: {e}"}
    
    # ==================== QUERY CONTROLS ====================
    
    def get_tempo(self):
        """Query current tempo"""
        try:
            self.client.send_message("/live/song/get/tempo", [])
            return {"success": True, "message": "Tempo query sent"}
        except Exception as e:
            return {"success": False, "message": f"Failed to query tempo: {e}"}
    
    def get_track_names(self):
        """
        Query all track names with response handling

        Returns:
            dict: {"success": bool, "track_names": List[str], "message": str}
        """
        try:
            # Send request and wait for response
            response = self._send_and_wait("/live/song/get/track_names", [], timeout=2.0)

            if response:
                address, args = response
                # args should be a list of track names
                if args and len(args) > 0:
                    # First arg might be the list, or each arg is a track name
                    if isinstance(args[0], list):
                        track_names = args[0]
                    else:
                        track_names = args

                    return {
                        "success": True,
                        "track_names": track_names,
                        "message": f"Found {len(track_names)} tracks"
                    }
                else:
                    return {"success": False, "track_names": [], "message": "Empty response from Ableton"}
            else:
                return {"success": False, "track_names": [], "message": "No response from Ableton (timeout)"}
        except Exception as e:
            return {"success": False, "track_names": [], "message": f"Failed to query track names: {e}"}
    
    def get_num_tracks(self):
        """Query number of tracks"""
        try:
            self.client.send_message("/live/song/get/num_tracks", [])
            return {"success": True, "message": "Track count query sent"}
        except Exception as e:
            return {"success": False, "message": f"Failed to query track count: {e}"}
    
    def get_num_scenes(self):
        """Query number of scenes"""
        try:
            self.client.send_message("/live/song/get/num_scenes", [])
            return {"success": True, "message": "Scene count query sent"}
        except Exception as e:
            return {"success": False, "message": f"Failed to query scene count: {e}"}

    def get_track_list(self):
        """
        Get a detailed list of all tracks with their indices and names

        Returns:
            dict: {
                "success": bool,
                "tracks": List[{"index": int, "display_index": int, "name": str}],
                "message": str
            }
        """
        try:
            result = self.get_track_names()
            if result["success"] and "track_names" in result:
                tracks = []
                for i, name in enumerate(result["track_names"]):
                    tracks.append({
                        "index": i,  # 0-based index for code
                        "display_index": i + 1,  # 1-based for user display
                        "name": name
                    })
                return {
                    "success": True,
                    "tracks": tracks,
                    "message": f"Found {len(tracks)} tracks"
                }
            else:
                return {"success": False, "tracks": [], "message": result.get("message", "Failed to get tracks")}
        except Exception as e:
            return {"success": False, "tracks": [], "message": f"Failed to get track list: {e}"}
    
    # ==================== DEVICE LOADING (via JarvisDeviceLoader) ====================
    # These methods communicate with the JarvisDeviceLoader Remote Script on port 11002
    
    def load_device(self, track_index, device_name, position=-1, timeout=None):
        """
        Load a device/plugin onto a track
        
        This requires the JarvisDeviceLoader Remote Script to be installed
        and selected in Ableton's preferences.
        
        Args:
            track_index: Track index (0-based, so Track 1 = 0)
            device_name: Name of the device to load (e.g., "EQ Eight", "FabFilter Pro-Q 3")
            position: Position in device chain (-1 = end, 0 = first)
            timeout: Optional JarvisDeviceLoader response timeout in seconds
            
        Returns:
            dict: {"success": bool, "message": str}
        """
        try:
            from discovery.vst_discovery import get_vst_discovery
            discovery = get_vst_discovery()
            result = discovery.load_device_on_track(track_index, device_name, position, timeout=timeout)
            return result
        except ImportError:
            # Fallback to direct OSC if vst_discovery not available
            return self._load_device_osc(track_index, device_name, position)
        except Exception as e:
            return {"success": False, "message": f"Failed to load device: {e}"}
    
    def _load_device_osc(self, track_index, device_name, position=-1):
        """Direct OSC call to load a device (via JarvisDeviceLoader)"""
        import socket
        import struct
        
        try:
            # Build OSC message for JarvisDeviceLoader
            address = "/jarvis/device/load"
            
            # Address (null-terminated, padded to 4 bytes)
            addr_bytes = address.encode('utf-8') + b'\x00'
            addr_padded = addr_bytes + b'\x00' * ((4 - len(addr_bytes) % 4) % 4)
            
            # Type tag: int, string, int
            type_tag = ',isi'
            type_bytes = type_tag.encode('utf-8') + b'\x00'
            type_padded = type_bytes + b'\x00' * ((4 - len(type_bytes) % 4) % 4)
            
            # Arguments
            arg_data = struct.pack('>i', track_index)
            str_bytes = device_name.encode('utf-8') + b'\x00'
            str_padded = str_bytes + b'\x00' * ((4 - len(str_bytes) % 4) % 4)
            arg_data += str_padded
            arg_data += struct.pack('>i', position)
            
            message = addr_padded + type_padded + arg_data
            
            # Send to JarvisDeviceLoader port (11002)
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(10.0)
            sock.bind(('127.0.0.1', 11003))  # Bind to response port
            sock.sendto(message, ('127.0.0.1', 11002))
            
            # Wait for response
            data, addr = sock.recvfrom(65535)
            sock.close()
            
            # Parse response (simplified)
            return {"success": True, "message": f"Device load request sent: {device_name}"}
            
        except socket.timeout:
            return {"success": False, "message": "Timeout: JarvisDeviceLoader not responding"}
        except Exception as e:
            return {"success": False, "message": f"OSC error: {e}"}
    
    def load_device_with_preset(self, track_index, device_name, preset_path):
        """
        Load a device with a specific preset
        
        Args:
            track_index: Track index (0-based)
            device_name: Name of the device
            preset_path: Path to the preset file
            
        Returns:
            dict: {"success": bool, "message": str}
        """
        # First load the device
        load_result = self.load_device(track_index, device_name)
        if not load_result.get("success"):
            return load_result
        
        # TODO: Implement preset loading via OSC
        # This would require extending JarvisDeviceLoader
        return {"success": True, "message": f"Device {device_name} loaded (preset loading not yet implemented)"}
    
    def get_available_plugins(self, category=None):
        """
        Get list of available plugins from Ableton
        
        Args:
            category: Optional category filter (eq, compressor, reverb, etc.)
            
        Returns:
            dict: {"success": bool, "plugins": list, "message": str}
        """
        try:
            from discovery.vst_discovery import get_vst_discovery
            discovery = get_vst_discovery()
            
            if category:
                plugins = discovery.get_plugins_by_category(category)
            else:
                plugins = discovery.get_all_plugins()
            
            return {
                "success": True,
                "plugins": [p.to_dict() for p in plugins],
                "count": len(plugins),
                "message": f"Found {len(plugins)} plugins"
            }
        except Exception as e:
            return {"success": False, "plugins": [], "message": f"Failed to get plugins: {e}"}
    
    def refresh_plugin_list(self):
        """
        Refresh the list of available plugins from Ableton
        
        Returns:
            dict: {"success": bool, "message": str}
        """
        try:
            from discovery.vst_discovery import get_vst_discovery
            discovery = get_vst_discovery()
            success = discovery.refresh_plugins()
            
            if success:
                count = len(discovery.get_all_plugins())
                return {"success": True, "message": f"Plugin list refreshed: {count} plugins found"}
            else:
                return {"success": False, "message": "Failed to refresh plugin list from Ableton"}
        except Exception as e:
            return {"success": False, "message": f"Failed to refresh plugins: {e}"}
    
    def find_plugin(self, query, category=None):
        """
        Find a plugin by name with fuzzy matching
        
        Args:
            query: Plugin name or partial match
            category: Optional category filter
            
        Returns:
            dict: {"success": bool, "plugin": dict or None, "message": str}
        """
        try:
            from discovery.vst_discovery import get_vst_discovery
            discovery = get_vst_discovery()
            plugin = discovery.find_plugin(query, category)
            
            if plugin:
                return {
                    "success": True,
                    "plugin": plugin.to_dict(),
                    "message": f"Found plugin: {plugin.name}"
                }
            else:
                return {
                    "success": False,
                    "plugin": None,
                    "message": f"No plugin found matching: {query}"
                }
        except Exception as e:
            return {"success": False, "plugin": None, "message": f"Search failed: {e}"}
    
    def load_plugin_chain(self, track_index, chain_config):
        """
        Load a complete plugin chain onto a track
        
        Args:
            track_index: Track index (0-based)
            chain_config: List of dicts with plugin info:
                [{"name": "EQ Eight", "settings": {...}}, ...]
            
        Returns:
            dict: {"success": bool, "loaded": list, "failed": list, "message": str}
        """
        loaded = []
        failed = []
        
        for i, plugin_config in enumerate(chain_config):
            plugin_name = plugin_config.get("name") or plugin_config.get("type")
            if not plugin_name:
                failed.append({"index": i, "reason": "No plugin name specified"})
                continue
            
            result = self.load_device(track_index, plugin_name, position=-1)
            
            if result.get("success"):
                loaded.append({"index": i, "name": plugin_name})
            else:
                failed.append({"index": i, "name": plugin_name, "reason": result.get("message")})
        
        success = len(loaded) > 0 and len(failed) == 0
        partial = len(loaded) > 0 and len(failed) > 0
        
        message = f"Loaded {len(loaded)}/{len(chain_config)} plugins"
        if partial:
            message += f" ({len(failed)} failed)"
        
        return {
            "success": success or partial,
            "loaded": loaded,
            "failed": failed,
            "message": message
        }
    
    def test_device_loader_connection(self):
        """
        Test connection to the JarvisDeviceLoader Remote Script
        
        Returns:
            dict: {"success": bool, "message": str}
        """
        try:
            from discovery.vst_discovery import get_vst_discovery
            discovery = get_vst_discovery()
            
            if discovery.test_connection():
                return {"success": True, "message": "JarvisDeviceLoader is connected"}
            else:
                return {"success": False, "message": "JarvisDeviceLoader not responding. Make sure it's selected in Ableton preferences."}
        except Exception as e:
            return {"success": False, "message": f"Connection test failed: {e}"}


    # ==================== PROCESS MANAGEMENT ====================
    # Convenience methods that delegate to AbletonProcessManager

    def _get_process_manager(self):
        """Get or create the process manager singleton"""
        from ableton_controls.process_manager import get_ableton_manager
        return get_ableton_manager()

    def close_ableton(self, force: bool = False) -> dict:
        """
        Close Ableton Live.

        Args:
            force: Force kill if graceful close fails

        Returns:
            dict: {"success": bool, "message": str}
        """
        try:
            pm = self._get_process_manager()
            success = pm.close_ableton(force=force)
            if success:
                return {"success": True, "message": "Ableton closed"}
            return {"success": False, "message": "Failed to close Ableton"}
        except Exception as e:
            return {"success": False, "message": f"Error closing Ableton: {e}"}

    def open_ableton(self, project_path: str = None) -> dict:
        """
        Launch Ableton Live, optionally opening a project file.

        Args:
            project_path: Path to .als project file (optional)

        Returns:
            dict: {"success": bool, "message": str}
        """
        try:
            pm = self._get_process_manager()
            success = pm.launch_ableton(project_path=project_path, wait_for_ready=True)
            if success:
                return {"success": True, "message": "Ableton launched"}
            return {"success": False, "message": "Failed to launch Ableton"}
        except Exception as e:
            return {"success": False, "message": f"Error launching Ableton: {e}"}

    def restart_ableton(self, reopen_project: bool = True,
                        force_kill: bool = False) -> dict:
        """
        Restart Ableton Live (close then relaunch).

        Args:
            reopen_project: Accept crash recovery dialog (True=Yes, False=No)
            force_kill: Force kill if graceful close fails

        Returns:
            dict: {"success": bool, "message": str}
        """
        try:
            pm = self._get_process_manager()
            success = pm.restart_ableton(
                reopen_project=reopen_project,
                force_kill=force_kill,
                handle_recovery=True,
            )
            if success:
                return {"success": True, "message": "Ableton restarted"}
            return {"success": False, "message": "Failed to restart Ableton"}
        except Exception as e:
            return {"success": False, "message": f"Error restarting Ableton: {e}"}

    # ==================== DIAGNOSTICS ====================

    def diag_osc(self, timeout: float = 3.0) -> dict:
        """
        Comprehensive OSC connectivity diagnostic.

        Sends multiple known AbletonOSC requests and reports exactly what
        happens at every stage: listener bind, send, raw receive, address
        matching.  All results are returned as a single JSON-friendly dict.
        """
        diag: Dict[str, Any] = {
            "send_to": f"{self.ip}:{self.port}",
            "response_port": self.response_port,
        }

        # --- 1. Listener status ---
        diag["listener_bound"] = getattr(self, "_diag_listener_ok", False)
        if not diag["listener_bound"]:
            diag["listener_error"] = getattr(self, "_diag_listener_error", "unknown")
            diag["listener_addr"] = None
        else:
            diag["listener_addr"] = str(getattr(self, "_diag_listener_addr", None))

        # --- 2. Send a minimal /live/test via pythonosc client ---
        try:
            self.client.send_message("/live/test", [])
            diag["pythonosc_send"] = "ok"
        except Exception as exc:
            diag["pythonosc_send"] = f"error: {exc}"

        # --- 3. Direct socket probe — send /live/song/get/tempo FROM listener socket ---
        probes = [
            ("/live/test", []),
            ("/live/song/get/tempo", []),
            ("/live/song/get/num_tracks", []),
        ]
        diag["probes"] = []

        for probe_addr, probe_args in probes:
            entry: Dict[str, Any] = {"address": probe_addr}
            msg = self._build_osc_message(probe_addr, probe_args)
            entry["msg_hex"] = msg[:64].hex()
            entry["msg_len"] = len(msg)

            # Try sending from listener socket (preferred)
            sent_from = "none"
            if self._resp_sock is not None:
                try:
                    self._resp_sock.sendto(msg, (self.ip, self.port))
                    sent_from = f"listener ({self.ip}:{self.response_port})"
                except Exception as exc:
                    sent_from = f"listener_error: {exc}"
            else:
                # Fallback: send from new socket
                try:
                    tmp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    tmp.sendto(msg, (self.ip, self.port))
                    tmp.close()
                    sent_from = "ephemeral (response unlikely)"
                except Exception as exc:
                    sent_from = f"ephemeral_error: {exc}"

            entry["sent_from"] = sent_from
            diag["probes"].append(entry)

        # --- 4. Wait and capture ANY responses ---
        time.sleep(0.1)  # small settle
        start = time.time()
        received: List[Dict[str, Any]] = []

        # Also try a raw socket listener to see absolutely anything
        raw_sock = None
        try:
            raw_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            raw_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # Try binding to a secondary diagnostic port
            for diag_port in [11005, 11006, 11007]:
                try:
                    raw_sock.bind(("0.0.0.0", diag_port))
                    raw_sock.settimeout(0.3)
                    diag["diag_raw_port"] = diag_port
                    # Send one more probe from THIS socket to see if response comes back to sender
                    probe_msg = self._build_osc_message("/live/song/get/tempo", [])
                    raw_sock.sendto(probe_msg, (self.ip, self.port))
                    diag["raw_probe_sent_from"] = f"0.0.0.0:{diag_port}"
                    break
                except OSError:
                    continue
            else:
                diag["diag_raw_port"] = "all_failed"
        except Exception as exc:
            diag["diag_raw_port"] = f"error: {exc}"

        # Collect from raw socket
        if raw_sock is not None:
            deadline = start + timeout
            while time.time() < deadline:
                try:
                    data, addr = raw_sock.recvfrom(65536)
                    try:
                        r_addr, r_args = self._parse_osc_message(data)
                    except Exception:
                        r_addr = f"<parse_error: {data[:32].hex()}>"
                        r_args = []
                    received.append({
                        "from": f"{addr[0]}:{addr[1]}",
                        "on_port": diag.get("diag_raw_port"),
                        "osc_address": r_addr,
                        "osc_args": [str(a) for a in r_args],
                        "raw_hex": data[:80].hex(),
                        "elapsed_ms": int((time.time() - start) * 1000),
                    })
                except socket.timeout:
                    continue
                except Exception:
                    break
            try:
                raw_sock.close()
            except Exception:
                pass

        # Also collect from the response listener's buffer
        with self._resp_cv:
            for resp_addr, (ts, resp_args) in list(self._last_response.items()):
                if ts >= start - 0.5:
                    received.append({
                        "from": "listener_buffer",
                        "on_port": self.response_port,
                        "osc_address": resp_addr,
                        "osc_args": [str(a) for a in resp_args],
                        "elapsed_ms": int((ts - start) * 1000),
                    })

        diag["received"] = received
        diag["total_received"] = len(received)

        # --- 5. Check for unmatched addresses ---
        diag["unmatched_addresses"] = getattr(self, "_diag_unmatched", [])

        # --- 6. Verdict ---
        if not diag["listener_bound"]:
            diag["verdict"] = "FAIL: Response listener could not bind to port " \
                              f"{self.response_port}. Another process may hold it."
        elif len(received) == 0:
            diag["verdict"] = (
                "FAIL: No OSC responses received on any port. "
                "Possible causes: (1) AbletonOSC control surface not loaded in Ableton, "
                "(2) Ableton not running, (3) firewall blocking UDP localhost."
            )
        elif any(r.get("on_port") == self.response_port or r.get("from") == "listener_buffer"
                 for r in received):
            diag["verdict"] = f"OK: Responses arriving on port {self.response_port}."
        else:
            ports = set(r.get("on_port") for r in received)
            diag["verdict"] = (
                f"PARTIAL: Responses seen on port(s) {ports} but NOT on "
                f"{self.response_port}. AbletonOSC may be replying to sender port."
            )

        diag["success"] = "OK" in diag.get("verdict", "")
        return diag


# Singleton instance for easy import
ableton = AbletonController()
