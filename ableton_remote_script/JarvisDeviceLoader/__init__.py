"""
JarvisDeviceLoader - Ableton Live Remote Script for Plugin/Device Loading

This script extends Ableton Live's capabilities to support loading devices
via OSC commands. It listens on port 11002 for device loading requests.

Installation:
    Copy this folder to:
    Windows: C:/ProgramData/Ableton/Live 11/Resources/MIDI Remote Scripts/JarvisDeviceLoader
    Mac: /Applications/Ableton Live 11 Suite.app/Contents/App-Resources/MIDI Remote Scripts/JarvisDeviceLoader

Usage:
    1. Open Ableton Live
    2. Go to Preferences > Link/Tempo/MIDI > Control Surface
    3. Select "JarvisDeviceLoader" from the dropdown
    4. The script will start listening for OSC commands on port 11002
"""

from __future__ import with_statement
import Live
import json
import os
import threading
import socket
import struct
import time
import tempfile

# Import Ableton Framework components
try:
    from _Framework.ControlSurface import ControlSurface
    from _Framework.Task import Task
except ImportError:
    # Fallback for standalone testing
    ControlSurface = object
    Task = None


def _file_seconds(clip):
    """Length of an audio clip's file in seconds, which is the unit of unwarped markers."""
    frames = getattr(clip, "sample_length", 0)
    rate = getattr(clip, "sample_rate", 0)
    if frames and rate:
        return float(frames) / float(rate)
    import wave
    try:
        w = wave.open(str(clip.file_path), "rb")
        try:
            return w.getnframes() / float(w.getframerate())
        finally:
            w.close()
    except Exception as exc:
        raise RuntimeError("Cannot read the length of {} to place it unwarped ({}); "
                           "place it warped (warping=1) instead.".format(clip.file_path, exc))


def _whole_file_markers(clip, seconds):
    """Unwarped clip plays the whole file: end first (keeps start < end), then start at 0."""
    clip.end_marker = seconds
    clip.loop_end = seconds
    clip.start_marker = 0.0
    clip.loop_start = 0.0


class JarvisDeviceLoader(ControlSurface):
    """
    Main control surface class for Jarvis Device Loader
    
    Provides OSC-based device loading and plugin discovery for Jarvis AI assistant.
    """
    
    def __init__(self, c_instance):
        """Initialize the control surface"""
        if ControlSurface != object:
            ControlSurface.__init__(self, c_instance)
        
        self._c_instance = c_instance
        self._osc_port = 11002
        self._response_port = 11003
        self._running = False
        self._socket = None
        self._listener_thread = None
        
        # Cache for available plugins
        self._plugin_cache = None
        self._plugin_cache_time = 0
        self._cache_ttl = 300  # 5 minutes
        
        # Start OSC listener
        self._start_osc_listener()
        
        self.log_message("JarvisDeviceLoader initialized on port {}".format(self._osc_port))
    
    def disconnect(self):
        """Clean up when the script is unloaded"""
        self._running = False
        if self._socket:
            try:
                self._socket.close()
            except:
                pass
        if self._listener_thread:
            try:
                self._listener_thread.join(timeout=1.0)
            except:
                pass
        if ControlSurface != object:
            ControlSurface.disconnect(self)
        self.log_message("JarvisDeviceLoader disconnected")
    
    def log_message(self, message):
        """Log a message to Ableton's log"""
        if hasattr(self, '_c_instance') and hasattr(self._c_instance, 'log_message'):
            self._c_instance.log_message("[JarvisDeviceLoader] " + str(message))
        else:
            print("[JarvisDeviceLoader] " + str(message))
    
    # ==================== OSC SERVER ====================
    
    def _start_osc_listener(self):
        """Start the OSC listener thread"""
        self._running = True
        self._listener_thread = threading.Thread(target=self._osc_listener_loop)
        self._listener_thread.daemon = True
        self._listener_thread.start()
    
    def _osc_listener_loop(self):
        """Main OSC listener loop running in a separate thread"""
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._socket.bind(('127.0.0.1', self._osc_port))
            self._socket.settimeout(1.0)
            
            self.log_message("OSC listener started on port {}".format(self._osc_port))
            
            while self._running:
                try:
                    data, addr = self._socket.recvfrom(65535)
                    self._handle_osc_message(data, addr)
                except socket.timeout:
                    continue
                except Exception as e:
                    self.log_message("OSC receive error: {}".format(str(e)))
                    
        except Exception as e:
            self.log_message("OSC listener error: {}".format(str(e)))
        finally:
            if self._socket:
                self._socket.close()
    
    def _handle_osc_message(self, data, addr):
        """Parse and handle incoming OSC message"""
        try:
            # Simple OSC parsing - extract address pattern and arguments
            address, args = self._parse_osc(data)
            
            self.log_message("Received OSC: {} {}".format(address, args))
            
            # Route to appropriate handler
            if address == "/jarvis/device/load":
                self._handle_load_device(args, addr)
            elif address == "/jarvis/device/load_by_uri":
                self._handle_load_device_by_uri(args, addr)
            elif address == "/jarvis/plugins/get":
                self._handle_get_plugins(args, addr)
            elif address == "/jarvis/plugins/refresh":
                self._handle_refresh_plugins(args, addr)
            elif address == "/jarvis/device/delete":
                self._handle_delete_device(args, addr)
            elif address == "/jarvis/track/type":
                self._handle_get_track_type(args, addr)
            elif address == "/jarvis/device/select":
                self._handle_select_device(args, addr)
            elif address == "/jarvis/device/tree":
                self._handle_device_tree(args, addr)
            elif address == "/jarvis/device/params_by_path":
                self._handle_device_params_by_path(args, addr)
            elif address == "/jarvis/debug/browser":
                self._handle_debug_browser(args, addr)
            elif address == "/jarvis/clip/create_audio":
                self._handle_create_audio_clip(args, addr)
            elif address == "/jarvis/clip/get_audio_path":
                self._handle_get_clip_audio_path(args, addr)
            elif address == "/jarvis/clip/set_detune":
                self._handle_set_clip_detune(args, addr)
            elif address == "/jarvis/song/play":
                self._handle_j_play(args, addr)
            elif address == "/jarvis/song/stop":
                self._handle_j_stop(args, addr)
            elif address == "/jarvis/song/set_position":
                self._handle_j_set_position(args, addr)
            elif address == "/jarvis/track/arm":
                self._handle_j_arm(args, addr)
            elif address == "/jarvis/track/create_audio":
                self._handle_j_create_audio_track(args, addr)
            elif address == "/jarvis/track/delete":
                self._handle_j_delete_track(args, addr)
            elif address == "/jarvis/song/track_names":
                self._handle_j_track_names(args, addr)
            elif address == "/jarvis/track/routing":
                self._handle_track_routing(args, addr)
            elif address == "/jarvis/track/set_input_routing":
                self._handle_set_input_routing(args, addr)
            elif address == "/jarvis/track/set_output_routing":
                self._handle_set_output_routing(args, addr)
            elif address == "/jarvis/track/set_monitoring":
                self._handle_set_monitoring(args, addr)
            elif address == "/jarvis/song/status":
                self._handle_song_status(args, addr)
            elif address == "/jarvis/song/set_record_mode":
                self._handle_set_record_mode(args, addr)
            elif address == "/jarvis/song/set_session_record":
                self._handle_set_session_record(args, addr)
            elif address == "/jarvis/song/back_to_arranger":
                self._handle_back_to_arranger(args, addr)
            elif address == "/jarvis/song/cue_points":
                self._handle_cue_points(args, addr)
            elif address == "/jarvis/track/arrangement_clips":
                self._handle_arrangement_clips(args, addr)
            elif address == "/jarvis/track/place_in_arrangement":
                self._handle_place_in_arrangement(args, addr)
            elif address == "/jarvis/test":
                # Extra items advertise capabilities; the bridge probes before relying on them.
                self._send_response(addr, "/jarvis/test/response", ["ok", "track_kind", "load_position"])
            else:
                self.log_message("Unknown OSC address: {}".format(address))
                
        except Exception as e:
            self.log_message("Error handling OSC: {}".format(str(e)))
    
    # ==================== LIVEPILOT EXTENDED API (routing/transport/arrangement) ====================

    def _run_main(self, addr, resp_addr, fn):
        """Schedule fn on the Live main thread and send its dict result as JSON."""
        def _do():
            try:
                self._send_json_response(addr, resp_addr, fn())
            except Exception as e:
                self.log_message("LivePilot ext error: {}".format(str(e)))
                self._send_response(addr, resp_addr, [0, "error", str(e)])
        if hasattr(self, 'schedule_message'):
            self.schedule_message(1, _do)
        else:
            _do()

    def _ext_track(self, track_index):
        song = self._get_song()
        if song is None:
            raise RuntimeError("Cannot access song")
        tracks = list(song.tracks)
        if track_index < 0 or track_index >= len(tracks):
            raise RuntimeError("Track index {} out of range (0-{})".format(track_index, len(tracks) - 1))
        return song, tracks[track_index]

    def _handle_track_routing(self, args, addr):
        track_index = int(args[0]) if args else 0
        def work():
            _song, tr = self._ext_track(track_index)
            def names(items):
                out = []
                try:
                    for it in items:
                        out.append(str(it.display_name))
                except Exception:
                    pass
                return out
            data = {"success": True, "track_index": track_index, "name": str(tr.name)}
            data["available_input_types"] = names(getattr(tr, "available_input_routing_types", []))
            data["available_output_types"] = names(getattr(tr, "available_output_routing_types", []))
            data["available_input_channels"] = names(getattr(tr, "available_input_routing_channels", []))
            irt = getattr(tr, "input_routing_type", None)
            ort = getattr(tr, "output_routing_type", None)
            data["input_type"] = str(irt.display_name) if irt is not None else None
            data["output_type"] = str(ort.display_name) if ort is not None else None
            data["monitoring"] = int(tr.current_monitoring_state) if hasattr(tr, "current_monitoring_state") else None
            data["can_be_armed"] = bool(getattr(tr, "can_be_armed", False))
            return data
        self._run_main(addr, "/jarvis/track/routing/response", work)

    def _set_routing(self, track_index, name, direction):
        _song, tr = self._ext_track(track_index)
        attr_avail = "available_{}_routing_types".format(direction)
        attr_cur = "{}_routing_type".format(direction)
        target = None
        options = []
        for rt in getattr(tr, attr_avail, []):
            dn = str(rt.display_name)
            options.append(dn)
            if dn.lower() == str(name).lower():
                target = rt
        if target is None:
            return {"success": False, "message": "No {} routing named '{}'".format(direction, name), "options": options}
        setattr(tr, attr_cur, target)
        return {"success": True, "track_index": track_index, "direction": direction,
                "routing": str(getattr(tr, attr_cur).display_name)}

    def _handle_set_input_routing(self, args, addr):
        track_index = int(args[0]) if args else 0
        name = str(args[1]) if len(args) > 1 else "Resampling"
        self._run_main(addr, "/jarvis/track/set_input_routing/response",
                       lambda: self._set_routing(track_index, name, "input"))

    def _handle_set_output_routing(self, args, addr):
        track_index = int(args[0]) if args else 0
        name = str(args[1]) if len(args) > 1 else ""
        self._run_main(addr, "/jarvis/track/set_output_routing/response",
                       lambda: self._set_routing(track_index, name, "output"))

    def _handle_set_monitoring(self, args, addr):
        track_index = int(args[0]) if args else 0
        state = int(args[1]) if len(args) > 1 else 1
        def work():
            _song, tr = self._ext_track(track_index)
            tr.current_monitoring_state = state
            return {"success": True, "track_index": track_index, "monitoring": int(tr.current_monitoring_state)}
        self._run_main(addr, "/jarvis/track/set_monitoring/response", work)

    def _handle_song_status(self, args, addr):
        def work():
            song = self._get_song()
            if song is None:
                raise RuntimeError("Cannot access song")
            data = {"success": True}
            for attr in ("is_playing", "record_mode", "session_record", "tempo",
                         "current_song_time", "last_event_time", "loop",
                         "loop_start", "loop_length", "back_to_arranger",
                         "signature_numerator", "signature_denominator"):
                try:
                    v = getattr(song, attr)
                    if isinstance(v, bool):
                        data[attr] = bool(v)
                    elif isinstance(v, int):
                        data[attr] = int(v)
                    else:
                        data[attr] = float(v)
                except Exception:
                    data[attr] = None
            try:
                data["seconds_per_beat"] = 60.0 / float(song.tempo)
                data["last_event_time_seconds"] = float(song.last_event_time) * 60.0 / float(song.tempo)
            except Exception:
                pass
            return data
        self._run_main(addr, "/jarvis/song/status/response", work)

    def _handle_set_record_mode(self, args, addr):
        state = int(args[0]) if args else 0
        def work():
            song = self._get_song()
            song.record_mode = state
            return {"success": True, "record_mode": int(song.record_mode)}
        self._run_main(addr, "/jarvis/song/set_record_mode/response", work)

    def _handle_set_session_record(self, args, addr):
        state = int(args[0]) if args else 0
        def work():
            song = self._get_song()
            song.session_record = state
            return {"success": True, "session_record": int(bool(song.session_record))}
        self._run_main(addr, "/jarvis/song/set_session_record/response", work)

    def _handle_back_to_arranger(self, args, addr):
        def work():
            song = self._get_song()
            song.back_to_arranger = 0
            return {"success": True, "back_to_arranger": int(bool(song.back_to_arranger))}
        self._run_main(addr, "/jarvis/song/back_to_arranger/response", work)

    def _handle_cue_points(self, args, addr):
        def work():
            song = self._get_song()
            cps = []
            for cp in getattr(song, "cue_points", []):
                try:
                    cps.append({"name": str(cp.name), "time": float(cp.time)})
                except Exception:
                    pass
            cps.sort(key=lambda c: c["time"])
            return {"success": True, "cue_points": cps, "count": len(cps)}
        self._run_main(addr, "/jarvis/song/cue_points/response", work)

    def _handle_arrangement_clips(self, args, addr):
        track_index = int(args[0]) if args else 0
        def work():
            _song, tr = self._ext_track(track_index)
            clips = []
            for clip in getattr(tr, "arrangement_clips", []):
                try:
                    item = {"name": str(clip.name),
                            "start_time": float(clip.start_time),
                            "end_time": float(clip.end_time),
                            "is_audio": bool(getattr(clip, "is_audio_clip", False))}
                    if item["is_audio"]:
                        try:
                            item["file_path"] = str(clip.file_path)
                        except Exception:
                            item["file_path"] = None
                    clips.append(item)
                except Exception:
                    pass
            clips.sort(key=lambda c: c["start_time"])
            return {"success": True, "track_index": track_index, "clips": clips, "count": len(clips)}
        self._run_main(addr, "/jarvis/track/arrangement_clips/response", work)

    def _handle_place_in_arrangement(self, args, addr):
        """Copy a Session clip onto the arrangement at an exact beat.

        args: track_index, clip_index, beat, warping (1/0, -1 = leave), clear_existing (1/0),
              end_beat (warped clips only: full clip length in beats)

        Unwarped clips are placed whole: their markers are in SECONDS, and Live leaves an
        auto start marker (~2 s) and a stale end on long files (a 40-bar stem started late and
        stopped at bar 25, 2026-10-20). So start goes to 0, end to the file length, and the
        arrangement end is checked against the file; a mismatch is removed and refused.
        """
        track_index = int(args[0])
        clip_index = int(args[1]) if len(args) > 1 else 0
        beat = float(args[2]) if len(args) > 2 else 0.0
        warping = int(args[3]) if len(args) > 3 else -1
        clear_existing = bool(int(args[4])) if len(args) > 4 else True
        end_beat = float(args[5]) if len(args) > 5 else 0.0
        def work():
            song, tr = self._ext_track(track_index)
            if not hasattr(tr, "duplicate_clip_to_arrangement"):
                raise RuntimeError("Live API has no Track.duplicate_clip_to_arrangement")
            slot = list(tr.clip_slots)[clip_index]
            if not slot.has_clip:
                raise RuntimeError("No clip in track {} slot {}".format(track_index, clip_index))
            clip = slot.clip
            # MIDI clips raise on any .warping access, so every warping touch is audio-only.
            is_audio = bool(getattr(clip, "is_audio_clip", False))
            if warping in (0, 1) and is_audio:
                clip.warping = bool(warping)
            unwarped = is_audio and not clip.warping
            seconds = expected_end = None
            if unwarped:
                clip.looping = False
                seconds = _file_seconds(clip)
                _whole_file_markers(clip, seconds)
                expected_end = beat + seconds * float(song.tempo) / 60.0
            elif end_beat > 0:
                clip.loop_end = end_beat
                clip.end_marker = end_beat
            removed = 0
            if clear_existing:
                for old in list(tr.arrangement_clips):
                    tr.delete_clip(old)
                    removed += 1
            tr.duplicate_clip_to_arrangement(clip, beat)
            placed = [c for c in tr.arrangement_clips if abs(float(c.start_time) - beat) < 1e-6]
            if not placed:
                raise RuntimeError("Clip was not placed at beat {}".format(beat))
            c = placed[0]
            if unwarped and abs(float(c.end_time) - expected_end) > 0.05:
                _whole_file_markers(c, seconds)  # the arrangement copy can keep its own markers
            if unwarped and abs(float(c.end_time) - expected_end) > 0.05:
                got = float(c.end_time)
                tr.delete_clip(c)
                raise RuntimeError(
                    "Unwarped clip would end at beat {:.2f} but the file ({:.2f} s) ends at beat {:.2f}; "
                    "removed it. Place it warped (warping=1) instead.".format(got, seconds, expected_end))
            return {"success": True, "track_index": track_index, "removed": removed,
                    "start_time": float(c.start_time), "end_time": float(c.end_time),
                    "expected_end": expected_end, "file_seconds": seconds,
                    "start_marker": float(c.start_marker) if is_audio else None,
                    "warping": bool(c.warping) if is_audio else None,
                    "file_path": str(c.file_path) if is_audio else ""}
        self._run_main(addr, "/jarvis/track/place_in_arrangement/response", work)

    # -- Jarvis-port transport/track primitives (batch-safe, no AbletonOSC port needed) --

    def _handle_j_play(self, args, addr):
        def work():
            song = self._get_song()
            song.is_playing = True
            return {"success": True, "is_playing": bool(song.is_playing)}
        self._run_main(addr, "/jarvis/song/play/response", work)

    def _handle_j_stop(self, args, addr):
        def work():
            song = self._get_song()
            song.is_playing = False
            return {"success": True, "is_playing": bool(song.is_playing)}
        self._run_main(addr, "/jarvis/song/stop/response", work)

    def _handle_j_set_position(self, args, addr):
        beat = float(args[0]) if args else 0.0
        def work():
            song = self._get_song()
            song.current_song_time = beat
            return {"success": True, "current_song_time": float(song.current_song_time)}
        self._run_main(addr, "/jarvis/song/set_position/response", work)

    def _handle_j_arm(self, args, addr):
        track_index = int(args[0]) if args else 0
        armed = int(args[1]) if len(args) > 1 else 1
        def work():
            _song, tr = self._ext_track(track_index)
            tr.arm = armed
            return {"success": True, "track_index": track_index, "arm": int(bool(tr.arm))}
        self._run_main(addr, "/jarvis/track/arm/response", work)

    def _handle_j_create_audio_track(self, args, addr):
        def work():
            song = self._get_song()
            song.create_audio_track(-1)
            n = len(list(song.tracks))
            return {"success": True, "track_index": n - 1, "track_count": n}
        self._run_main(addr, "/jarvis/track/create_audio/response", work)

    def _handle_j_delete_track(self, args, addr):
        track_index = int(args[0]) if args else 0
        def work():
            song = self._get_song()
            song.delete_track(track_index)
            return {"success": True, "deleted": track_index, "track_count": len(list(song.tracks))}
        self._run_main(addr, "/jarvis/track/delete/response", work)

    def _handle_j_track_names(self, args, addr):
        def work():
            song = self._get_song()
            names = [str(t.name) for t in song.tracks]
            return {"success": True, "names": names, "count": len(names)}
        self._run_main(addr, "/jarvis/song/track_names/response", work)

    def _parse_osc(self, data):
        """Parse OSC message into address and arguments"""
        # OSC address is null-terminated, padded to 4-byte boundary
        null_idx = data.index(b'\x00')
        address = data[:null_idx].decode('utf-8')
        
        # Calculate padding
        addr_size = (null_idx + 4) & ~3
        
        # Type tag starts after address
        if len(data) <= addr_size:
            return address, []
        
        # Find type tag string
        type_start = addr_size
        if data[type_start:type_start+1] != b',':
            return address, []
        
        type_null = data.index(b'\x00', type_start)
        type_tag = data[type_start+1:type_null].decode('utf-8')
        type_size = ((type_null - type_start) + 4) & ~3
        
        # Parse arguments based on type tags
        args = []
        offset = type_start + type_size
        
        for tag in type_tag:
            if tag == 'i':
                val = struct.unpack('>i', data[offset:offset+4])[0]
                args.append(val)
                offset += 4
            elif tag == 'f':
                val = struct.unpack('>f', data[offset:offset+4])[0]
                args.append(val)
                offset += 4
            elif tag == 's':
                str_null = data.index(b'\x00', offset)
                val = data[offset:str_null].decode('utf-8')
                args.append(val)
                offset = ((str_null + 1) + 3) & ~3
        
        return address, args
    
    def _build_osc_message(self, address, args):
        """Build an OSC message from address and arguments"""
        # Address (null-terminated, padded)
        addr_bytes = address.encode('utf-8') + b'\x00'
        addr_padded = addr_bytes + b'\x00' * ((4 - len(addr_bytes) % 4) % 4)
        
        # Type tag
        type_tag = ','
        arg_data = b''
        
        for arg in args:
            if isinstance(arg, int):
                type_tag += 'i'
                arg_data += struct.pack('>i', arg)
            elif isinstance(arg, float):
                type_tag += 'f'
                arg_data += struct.pack('>f', arg)
            elif isinstance(arg, str):
                type_tag += 's'
                str_bytes = arg.encode('utf-8') + b'\x00'
                str_padded = str_bytes + b'\x00' * ((4 - len(str_bytes) % 4) % 4)
                arg_data += str_padded
        
        type_bytes = type_tag.encode('utf-8') + b'\x00'
        type_padded = type_bytes + b'\x00' * ((4 - len(type_bytes) % 4) % 4)
        
        return addr_padded + type_padded + arg_data
    
    def _send_response(self, addr, response_address, args):
        """Send OSC response back to client"""
        try:
            response = self._build_osc_message(response_address, args)
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # Send to response port on localhost
            sock.sendto(response, ('127.0.0.1', self._response_port))
            sock.close()
        except Exception as e:
            self.log_message("Error sending response: {}".format(str(e)))

    def _send_json_response(self, addr, response_address, payload):
        """Send a JSON payload, falling back to a temp file if UDP is too small."""
        try:
            json_text = json.dumps(payload, separators=(',', ':'), sort_keys=True)
            if len(json_text.encode('utf-8')) > 55000:
                filename = "livepilot_{}_{}.json".format(
                    response_address.strip('/').replace('/', '_'),
                    int(time.time() * 1000)
                )
                path = os.path.join(tempfile.gettempdir(), filename)
                with open(path, 'w') as f:
                    f.write(json_text)
                json_text = json.dumps({
                    "schema_version": payload.get("schema_version"),
                    "payload_format": "json_file",
                    "path": path,
                    "bytes": os.path.getsize(path)
                }, separators=(',', ':'), sort_keys=True)
            self._send_response(addr, response_address, [1, "success", json_text])
        except Exception as e:
            self.log_message("JSON response error: {}".format(str(e)))
            self._send_response(addr, response_address, [0, "error", str(e)])

    # ==================== RECURSIVE DEVICE INSPECTION ====================

    def _handle_device_tree(self, args, addr):
        """Return a recursive JSON device tree for a track."""
        if len(args) < 1:
            self._send_response(addr, "/jarvis/device/tree/response",
                              [0, "error", "Missing argument: track_index"])
            return

        track_index = int(args[0])

        def do_tree_on_main_thread():
            try:
                payload = self._get_device_tree(track_index)
                self._send_json_response(addr, "/jarvis/device/tree/response", payload)
            except Exception as e:
                self.log_message("Device tree error: {}".format(str(e)))
                self._send_response(addr, "/jarvis/device/tree/response",
                                  [0, "error", str(e)])

        if hasattr(self, 'schedule_message'):
            self.schedule_message(1, do_tree_on_main_thread)
        else:
            do_tree_on_main_thread()

    def _handle_device_params_by_path(self, args, addr):
        """Return parameter details for a nested device path."""
        if len(args) < 2:
            self._send_response(addr, "/jarvis/device/params_by_path/response",
                              [0, "error", "Missing arguments: track_index, device_path_json"])
            return

        track_index = int(args[0])
        device_path_json = str(args[1])

        def do_params_on_main_thread():
            try:
                device_path = json.loads(device_path_json)
                payload = self._get_device_params_by_path(track_index, device_path)
                self._send_json_response(addr, "/jarvis/device/params_by_path/response", payload)
            except Exception as e:
                self.log_message("Device params by path error: {}".format(str(e)))
                self._send_response(addr, "/jarvis/device/params_by_path/response",
                                  [0, "error", str(e)])

        if hasattr(self, 'schedule_message'):
            self.schedule_message(1, do_params_on_main_thread)
        else:
            do_params_on_main_thread()

    def _get_device_tree(self, track_index, max_depth=5):
        song = self._get_song()
        if not song:
            return {
                "schema_version": "livepilot.device_tree.v1",
                "success": False,
                "track_index": track_index,
                "error": "Cannot access song",
                "devices": []
            }

        tracks = list(song.tracks)
        if track_index < 0 or track_index >= len(tracks):
            return {
                "schema_version": "livepilot.device_tree.v1",
                "success": False,
                "track_index": track_index,
                "error": "Invalid track index",
                "available_tracks": len(tracks),
                "devices": []
            }

        track = tracks[track_index]
        payload = {
            "schema_version": "livepilot.device_tree.v1",
            "success": True,
            "track_index": track_index,
            "track_name": self._safe_attr(track, "name", ""),
            "devices": [],
            "warnings": [],
            "errors": []
        }

        try:
            devices = list(track.devices)
        except Exception as e:
            payload["success"] = False
            payload["errors"].append("Could not read track devices: {}".format(str(e)))
            return payload

        for index, device in enumerate(devices):
            name = self._safe_attr(device, "name", "")
            path = [{"kind": "track_device", "index": index, "name": name}]
            payload["devices"].append(self._capture_device_node(device, path, 0, max_depth))

        return payload

    def _get_device_params_by_path(self, track_index, device_path):
        payload = {
            "schema_version": "livepilot.device_params_by_path.v1",
            "success": False,
            "track_index": track_index,
            "device_path": device_path,
            "parameters": [],
            "errors": []
        }
        device, error = self._resolve_device_path(track_index, device_path)
        if error:
            payload["errors"].append(error)
            return payload

        payload["success"] = True
        payload["device_name"] = self._safe_attr(device, "name", "")
        payload["class_name"] = self._safe_attr(device, "class_name", "")
        payload["parameters"] = self._capture_parameters(device)
        return payload

    def _resolve_device_path(self, track_index, device_path):
        song = self._get_song()
        if not song:
            return None, "Cannot access song"

        tracks = list(song.tracks)
        if track_index < 0 or track_index >= len(tracks):
            return None, "Invalid track index"
        if not device_path:
            return None, "Device path is empty"

        current_device = None
        current_chain = None
        for element in device_path:
            kind = element.get("kind")
            index = int(element.get("index", -1))

            if kind == "track_device":
                devices = list(tracks[track_index].devices)
                if index < 0 or index >= len(devices):
                    return None, "Invalid track device index: {}".format(index)
                current_device = devices[index]
                current_chain = None
            elif kind in ("chain", "return_chain"):
                if current_device is None:
                    return None, "{} appears before a device".format(kind)
                attr = "return_chains" if kind == "return_chain" else "chains"
                chains = list(self._safe_attr(current_device, attr, []))
                if index < 0 or index >= len(chains):
                    return None, "Invalid {} index: {}".format(kind, index)
                current_chain = chains[index]
            elif kind == "chain_device":
                if current_chain is None:
                    return None, "chain_device appears before a chain"
                devices = list(self._safe_attr(current_chain, "devices", []))
                if index < 0 or index >= len(devices):
                    return None, "Invalid chain device index: {}".format(index)
                current_device = devices[index]
            else:
                return None, "Unsupported path element kind: {}".format(kind)

        if current_device is None:
            return None, "Path did not resolve to a device"
        return current_device, None

    def _capture_device_node(self, device, path, depth, max_depth):
        node = {
            "kind": "device",
            "path": path,
            "name": self._safe_attr(device, "name", ""),
            "class_name": self._safe_attr(device, "class_name", ""),
            "class_display_name": self._safe_attr(device, "class_display_name", ""),
            "type": self._json_safe(self._safe_attr(device, "type", None)),
            "is_enabled": self._json_safe(self._safe_attr(device, "is_enabled", None)),
            "is_active": self._json_safe(self._safe_attr(device, "is_active", None)),
            "can_have_chains": bool(self._safe_attr(device, "can_have_chains", False)),
            "can_show_chains": bool(self._safe_attr(device, "can_show_chains", False)),
            "parameters": [],
            "chains": [],
            "return_chains": [],
            "errors": []
        }

        try:
            node["parameters"] = self._capture_parameters(device)
        except Exception as e:
            node["errors"].append("Could not read parameters: {}".format(str(e)))

        if depth >= max_depth:
            if node["can_have_chains"]:
                node["errors"].append("Max recursion depth reached")
            return node

        if node["can_have_chains"]:
            node["chains"] = self._capture_chain_collection(
                device, "chains", "chain", path, depth, max_depth)
            node["return_chains"] = self._capture_chain_collection(
                device, "return_chains", "return_chain", path, depth, max_depth)

        return node

    def _capture_chain_collection(self, device, attr_name, path_kind, parent_path, depth, max_depth):
        chains_payload = []
        try:
            chains = list(self._safe_attr(device, attr_name, []))
        except Exception as e:
            return [{
                "kind": path_kind,
                "index": -1,
                "name": "",
                "path": parent_path,
                "devices": [],
                "errors": ["Could not read {}: {}".format(attr_name, str(e))]
            }]

        for chain_index, chain in enumerate(chains):
            chain_name = self._safe_attr(chain, "name", "")
            chain_path = parent_path + [{"kind": path_kind, "index": chain_index, "name": chain_name}]
            chain_payload = {
                "kind": path_kind,
                "index": chain_index,
                "name": chain_name,
                "path": chain_path,
                "mixer": self._capture_chain_mixer(chain),
                "devices": [],
                "errors": []
            }
            try:
                devices = list(self._safe_attr(chain, "devices", []))
                for device_index, child in enumerate(devices):
                    child_name = self._safe_attr(child, "name", "")
                    child_path = chain_path + [{
                        "kind": "chain_device",
                        "index": device_index,
                        "name": child_name
                    }]
                    chain_payload["devices"].append(
                        self._capture_device_node(child, child_path, depth + 1, max_depth)
                    )
            except Exception as e:
                chain_payload["errors"].append("Could not read chain devices: {}".format(str(e)))
            chains_payload.append(chain_payload)

        return chains_payload

    def _capture_chain_mixer(self, chain):
        mixer = self._safe_attr(chain, "mixer_device", None)
        if mixer is None:
            return {}

        data = {}
        for attr in ("volume", "panning", "chain_activator"):
            param = self._safe_attr(mixer, attr, None)
            if param is not None:
                data[attr] = self._capture_parameter(param, -1)

        try:
            sends = list(self._safe_attr(mixer, "sends", []))
            data["sends"] = [self._capture_parameter(param, index)
                             for index, param in enumerate(sends)]
        except Exception:
            data["sends"] = []

        return data

    def _capture_parameters(self, device):
        try:
            params = list(self._safe_attr(device, "parameters", []))
        except Exception:
            return []
        return [self._capture_parameter(param, index) for index, param in enumerate(params)]

    def _capture_parameter(self, param, index):
        data = {
            "index": index,
            "name": self._safe_attr(param, "name", ""),
            "value": self._json_safe(self._safe_attr(param, "value", None)),
            "min": self._json_safe(self._safe_attr(param, "min", None)),
            "max": self._json_safe(self._safe_attr(param, "max", None)),
            "default_value": self._json_safe(self._safe_attr(param, "default_value", None)),
            "is_enabled": self._json_safe(self._safe_attr(param, "is_enabled", None))
        }

        display = None
        value = self._safe_attr(param, "value", None)
        try:
            if hasattr(param, "str_for_value") and value is not None:
                display = param.str_for_value(value)
        except Exception as e:
            data["display_error"] = str(e)
        if display is not None:
            data["display_value"] = self._json_safe(display)

        return data

    def _safe_attr(self, obj, name, default=None):
        try:
            if hasattr(obj, name):
                return getattr(obj, name)
        except Exception:
            return default
        return default

    def _json_safe(self, value):
        if value is None or isinstance(value, (bool, int, float, str)):
            return value
        try:
            return str(value)
        except Exception:
            return "<unserializable>"
    
    # ==================== DEVICE LOADING ====================
    
    def _handle_load_device(self, args, addr):
        """Handle device loading request.

        IMPORTANT: Must run on Ableton's main thread via schedule_message.
        Running browser.load_item() from the OSC listener thread causes
        'Audio queue timeout' crashes (corrupts internal state).
        """
        if len(args) < 2:
            self._send_response(addr, "/jarvis/device/load/response",
                              [0, "error", "Missing arguments: track_index, device_name"])
            return

        track_index = int(args[0])
        device_name = str(args[1])
        position = int(args[2]) if len(args) > 2 else -1
        track_kind = str(args[3]) if len(args) > 3 else "track"

        def do_load_on_main_thread():
            try:
                result = self._load_device_on_track(track_index, device_name, position, track_kind)
                self._send_response(addr, "/jarvis/device/load/response", result)
            except Exception as e:
                self.log_message("Load device error: {}".format(str(e)))
                self._send_response(addr, "/jarvis/device/load/response",
                                  [0, "error", str(e)])

        if hasattr(self, 'schedule_message'):
            self.schedule_message(1, do_load_on_main_thread)
        else:
            do_load_on_main_thread()
    
    def _handle_load_device_by_uri(self, args, addr):
        """Handle device loading by browser URI.

        IMPORTANT: Must run on main thread — same reason as _handle_load_device.
        """
        if len(args) < 2:
            self._send_response(addr, "/jarvis/device/load_by_uri/response",
                              [0, "error", "Missing arguments"])
            return

        track_index = int(args[0])
        browser_uri = str(args[1])
        position = int(args[2]) if len(args) > 2 else -1

        def do_load_uri_on_main_thread():
            try:
                result = self._load_device_by_uri(track_index, browser_uri, position)
                self._send_response(addr, "/jarvis/device/load_by_uri/response", result)
            except Exception as e:
                self.log_message("Load device by URI error: {}".format(str(e)))
                self._send_response(addr, "/jarvis/device/load_by_uri/response",
                                  [0, "error", str(e)])

        if hasattr(self, 'schedule_message'):
            self.schedule_message(1, do_load_uri_on_main_thread)
        else:
            do_load_uri_on_main_thread()
    
    def _resolve_track(self, song, track_index, track_kind="track"):
        """Return (track, label) for track_kind 'track' | 'return' | 'master'.

        For 'return', track_index is the return index (0 = A). For 'master' it is ignored.
        """
        if track_kind == "master":
            return song.master_track, "master"
        if track_kind == "return":
            pool = list(song.return_tracks)
        elif track_kind == "track":
            pool = list(song.tracks)
        else:
            raise ValueError("Unknown track_kind: {} (use track, return or master)".format(track_kind))
        if track_index < 0 or track_index >= len(pool):
            raise ValueError("Invalid {} index: {} (only {} available)".format(track_kind, track_index, len(pool)))
        return pool[track_index], "{} {}".format(track_kind, track_index)

    def _load_device_on_track(self, track_index, device_name, position=-1, track_kind="track"):
        """Load a device onto a track by name, then place it at `position` (-1 = end).

        Returns [ok, status, message, final_device_index].
        """
        self.log_message("Loading device '{}' on {} {} at position {}".format(device_name, track_kind, track_index, position))

        song = self._get_song()
        if not song:
            self.log_message("ERROR: Cannot access song")
            return [0, "error", "Cannot access song"]

        try:
            track, label = self._resolve_track(song, track_index, track_kind)
        except ValueError as e:
            self.log_message("ERROR: " + str(e))
            return [0, "error", str(e)]

        # Select the track first (required for browser.load_item to work)
        song.view.selected_track = track

        browser = self._get_browser()
        if not browser:
            self.log_message("ERROR: Cannot access browser")
            return [0, "error", "Cannot access browser"]

        device_uri = self._find_device_uri(browser, device_name)
        if not device_uri:
            error_msg = "Device not found: {}".format(device_name)
            self.log_message("ERROR: " + error_msg)
            return [0, "error", error_msg]

        devices_before = list(track.devices)
        before_ptrs = set(self._device_ptr(d) for d in devices_before)

        # load_item inserts after the selected device, so select the device the
        # new one should follow. Position 0 has no predecessor; move_device fixes it.
        if devices_before:
            anchor = len(devices_before) - 1 if position < 0 or position > len(devices_before) else position - 1
            if anchor >= 0:
                try:
                    song.view.select_device(devices_before[anchor])
                except Exception as e:
                    self.log_message("select_device failed: {}".format(e))

        try:
            browser.load_item(device_uri)
        except Exception as e:
            error_msg = "Failed to load device: {}".format(str(e))
            self.log_message("ERROR: " + error_msg)
            return [0, "error", error_msg]

        import time
        new_device = None
        for attempt in range(6):
            if attempt:  # the load is usually already in the chain; only wait when it is not
                time.sleep(0.2)
            try:
                devices_after = list(track.devices)
            except Exception:
                continue
            if len(devices_after) > len(devices_before):
                new_device = self._find_new_device(track, devices_after, before_ptrs)
                break

        if new_device is None:
            self.log_message("WARNING: Device count did not increase after load_item(). May have failed silently.")
            return [0, "error", "Device load may have failed - device count unchanged"]

        devices_after = list(track.devices)
        target = len(devices_after) - 1 if position < 0 or position >= len(devices_after) else position
        index = self._device_index(devices_after, new_device)
        if index != target and hasattr(song, "move_device"):
            try:
                song.move_device(new_device, track, target)
                index = self._device_index(list(track.devices), new_device)
                if index < target:
                    # Moving forward in the same chain can land one short.
                    song.move_device(new_device, track, target + 1)
                    index = self._device_index(list(track.devices), new_device)
            except Exception as e:
                self.log_message("move_device failed: {}".format(e))

        name = getattr(new_device, "name", device_name)
        msg = "Device loaded: {} on {} at index {}".format(name, label, index)
        if index != target:
            msg += " (requested {}, could not place)".format(target)
        self.log_message(msg)
        return [1, "success", msg, index]

    def _device_ptr(self, device):
        # Stable identity across Python wrappers; id() is not.
        return getattr(device, "_live_ptr", None)

    def _find_new_device(self, track, devices_after, before_ptrs):
        if None not in before_ptrs:
            for d in devices_after:
                ptr = self._device_ptr(d)
                if ptr is not None and ptr not in before_ptrs:
                    return d
        # Pointer unavailable: Live selects the device it just loaded.
        try:
            selected = track.view.selected_device
            if selected is not None:
                return selected
        except Exception:
            pass
        return devices_after[-1]

    def _device_index(self, devices, device):
        ptr = self._device_ptr(device)
        for i, d in enumerate(devices):
            if (ptr is not None and self._device_ptr(d) == ptr) or (ptr is None and d == device):
                return i
        return -1

    def _load_device_by_uri(self, track_index, uri, position=-1):
        """Load a device by its browser URI"""
        song = self._get_song()
        browser = self._get_browser()
        
        if not song or not browser:
            return [0, "error", "Cannot access song or browser"]
        
        # Select the target track first
        tracks = list(song.tracks)
        if track_index < 0 or track_index >= len(tracks):
            return [0, "error", "Invalid track index"]
        
        track = tracks[track_index]
        song.view.selected_track = track
        
        try:
            # Find and load the item
            item = self._find_browser_item_by_uri(browser, uri)
            if item:
                browser.load_item(item)
                return [1, "success", "Device loaded from URI"]
            else:
                return [0, "error", "URI not found in browser"]
        except Exception as e:
            return [0, "error", str(e)]
    
    def _find_device_uri(self, browser, device_name):
        """
        Find a device in the browser by name using robust strategies.
        Handles ghost folders, iterator consumption, and native device quirks.
        """
        device_name_lower = device_name.lower().strip()
        self.log_message("Searching for device: '{}' (robust mode)".format(device_name))
        
        # Strategy 1: Known Category Fallback (Most reliable for native devices)
        # Map common devices to their categories in Audio Effects
        known_locations = {
            "eq eight": "EQ & Filters",
            "eq three": "EQ & Filters",
            "auto filter": "EQ & Filters",
            "channel eq": "EQ & Filters",
            "compressor": "Dynamics",
            "glue compressor": "Dynamics",
            "limiter": "Dynamics",
            "gate": "Dynamics",
            "multiband dynamics": "Dynamics",
            "reverb": "Reverb & Resonance",
            "hybrid reverb": "Reverb & Resonance",
            "delay": "Delay & Loop",
            "echo": "Delay & Loop",
            "utility": "Utilities",
            "tuner": "Utilities",
            "spectrum": "Utilities",
            "autopan": "Modulators",
            "chorus-ensemble": "Modulators",
            "phaser-flanger": "Modulators",
            "shifter": "Pitch & Modulation"
        }
        
        target_category = known_locations.get(device_name_lower)
        
        if target_category:
            self.log_message("Strategy 1: Checking known category '{}' for '{}'".format(target_category, device_name))
            try:
                # Iterate Audio Effects to find the category
                audio_effects = browser.audio_effects
                for item in self._get_children_safe(audio_effects):
                    item_name = item.name if hasattr(item, 'name') else ''
                    if item_name == target_category:
                        # Found category, search inside
                        self.log_message("  Found category '{}', searching inside...".format(target_category))
                        for child in self._get_children_safe(item):
                            if self._is_match(child, device_name_lower):
                                self.log_message("  FOUND in known category: {}".format(child.name))
                                return child
            except Exception as e:
                self.log_message("Strategy 1 failed: {}".format(str(e)))

        # Strategy 2: Deep Recursive Search (Fallback)
        self.log_message("Strategy 2: Deep recursive search")
        
        categories_to_search = [
            browser.audio_effects,
            browser.midi_effects, 
            browser.instruments,
            browser.plugins,
            browser.drums,
            browser.max_for_live
        ]
        
        for category in categories_to_search:
            if not category: continue
            try:
                cat_name = getattr(category, 'name', '?')
                # self.log_message(f"Scanning {cat_name}...")
                result = self._deep_search(category, device_name_lower)
                if result:
                    return result
            except Exception as e:
                self.log_message("Error searching category: {}".format(str(e)))
        
        self.log_message("Device not found: {}".format(device_name))
        return None

    def _get_children_safe(self, item):
        """Safely get children as a list, handling iterators and errors"""
        try:
            return list(item.iter_children)
        except:
            try:
                return list(item.children)
            except:
                return []

    def _is_match(self, item, target_lower):
        """Check if item matches target name"""
        if not item: return False
        name_lower = item.name.lower() if hasattr(item, 'name') else ''
        
        # Exact match
        if name_lower == target_lower: return True
        # Exact match ignoring spaces
        if name_lower.replace(' ', '') == target_lower.replace(' ', ''): return True
        
        return False

    def _deep_search(self, parent, target_name, depth=0):
        """Recursive search with forced list conversion"""
        if depth > 5: return None
        
        children = self._get_children_safe(parent)
        
        for child in children:
            # Check match
            if self._is_match(child, target_name):
                # If it's a device (or looks like one), return it
                return child
            
            # Recurse (always try to recurse if it has children)
            # Use get_children_safe length check to decide recursion
            child_children = self._get_children_safe(child)
            if len(child_children) > 0:
                 result = self._deep_search(child, target_name, depth + 1)
                 if result: return result
        
        return None
    
    def _find_browser_item_by_uri(self, browser, uri):
        """Find a browser item by its URI"""
        return None
    
    # ==================== PLUGIN DISCOVERY ====================
    
    def _handle_get_plugins(self, args, addr):
        """Handle request for available plugins list"""
        # Backwards-compatible args:
        # - [] -> return first page
        # - [category] -> return first page filtered
        # - [category, offset, limit] -> return page
        category_filter = str(args[0]) if len(args) >= 1 and args[0] not in (None, "") else None
        offset = int(args[1]) if len(args) >= 2 else 0
        limit = int(args[2]) if len(args) >= 3 else 200
        if limit <= 0:
            limit = 200

        def do_get_plugins_on_main_thread():
            try:
                plugins = self._get_available_plugins(category_filter)
                total = len(plugins)
                # Page the response to avoid oversized UDP datagrams (WinError 10040)
                page = plugins[offset:offset + limit]

                # Send response with total count + paging info + JSON chunk
                response = [1, "success", total, offset, limit]
                import json
                plugins_json = json.dumps(page)
                response.append(plugins_json)
                self._send_response(addr, "/jarvis/plugins/get/response", response)
            except Exception as e:
                self._send_response(addr, "/jarvis/plugins/get/response",
                                  [0, "error", str(e)])

        # Browser iteration must run on Ableton's main thread (same as device load)
        if hasattr(self, 'schedule_message'):
            self.schedule_message(1, do_get_plugins_on_main_thread)
        else:
            do_get_plugins_on_main_thread()

    def _handle_refresh_plugins(self, args, addr):
        """Force refresh the plugin cache"""
        self._plugin_cache = None
        self._plugin_cache_time = 0

        def do_refresh_on_main_thread():
            try:
                plugins = self._get_available_plugins()
                self._send_response(addr, "/jarvis/plugins/refresh/response",
                                  [1, "success", len(plugins)])
            except Exception as e:
                self._send_response(addr, "/jarvis/plugins/refresh/response",
                                  [0, "error", str(e)])

        if hasattr(self, 'schedule_message'):
            self.schedule_message(1, do_refresh_on_main_thread)
        else:
            do_refresh_on_main_thread()

    def _get_available_plugins(self, category_filter=None):
        """Get list of all available plugins from Ableton's browser"""
        current_time = time.time()

        if (self._plugin_cache is not None and
            current_time - self._plugin_cache_time < self._cache_ttl):
            plugins = self._plugin_cache
        else:
            plugins = self._scan_browser_for_plugins()
            self._plugin_cache = plugins
            self._plugin_cache_time = current_time

        if category_filter:
            wanted = str(category_filter).lower()
            return [p for p in plugins
                    if p.get('category', '') == wanted or p.get('type', '') == wanted]
        return plugins

    def _scan_browser_for_plugins(self):
        """Walk the Live browser and collect every loadable device/plugin/sample."""
        browser = self._get_browser()
        if not browser:
            self.log_message("Plugin scan: cannot access browser")
            return []

        sections = [
            ('plugins', 'plugin'),
            ('audio_effects', 'audio_effect'),
            ('midi_effects', 'midi_effect'),
            ('instruments', 'instrument'),
            ('drums', 'drums'),
        ]

        plugins = []
        for attr, plugin_type in sections:
            section = getattr(browser, attr, None)
            if section is None:
                continue
            try:
                self._collect_loadable_items(section, plugin_type, [], plugins)
            except Exception as e:
                self.log_message("Plugin scan: error in section '{}': {}".format(attr, str(e)))

        self.log_message("Plugin scan: found {} items".format(len(plugins)))
        return plugins

    def _collect_loadable_items(self, parent, plugin_type, path_parts, out, depth=0):
        """Recurse into folders; record loadable items without descending into their presets."""
        if depth > 8:
            return
        for child in self._get_children_safe(parent):
            name = getattr(child, 'name', '') or ''
            if not name:
                continue
            if getattr(child, 'is_loadable', False):
                out.append({
                    'name': name,
                    'type': plugin_type,
                    'category': self._categorize_plugin(name, plugin_type),
                    'path': '/'.join(path_parts + [name]),
                    'aliases': [],
                })
            else:
                self._collect_loadable_items(child, plugin_type, path_parts + [name], out, depth + 1)

    def _categorize_plugin(self, name, plugin_type):
        """Best-effort category from the item name; falls back to the section type."""
        if plugin_type not in ('plugin', 'audio_effect'):
            return plugin_type
        name_lower = name.lower()
        keyword_categories = [
            ('eq', ('eq', 'equaliz', 'filter', 'pro-q')),
            ('compressor', ('comp', 'limiter', '1176', 'la-2a', 'la2a', 'pro-c', 'pro-l')),
            ('dynamics', ('gate', 'expander', 'transient', 'dynamic', 'de-ess', 'deess')),
            ('reverb', ('reverb', 'verb', 'plate', 'spring', 'pro-r')),
            ('delay', ('delay', 'echo')),
            ('distortion', ('distort', 'saturat', 'overdrive', 'fuzz', 'crush', 'clip')),
            ('modulation', ('chorus', 'flanger', 'phaser', 'tremolo', 'vibrato')),
            ('utility', ('utility', 'gain', 'tuner', 'meter', 'analyz', 'spectrum')),
        ]
        for category, keywords in keyword_categories:
            for kw in keywords:
                if kw in name_lower:
                    return category
        return plugin_type

    def _handle_delete_device(self, args, addr):
        """Delete a device from a track"""
        if len(args) < 2:
            self._send_response(addr, "/jarvis/device/delete/response",
                              [0, "error", "Missing arguments"])
            return
        
        track_index = int(args[0])
        device_index = int(args[1])
        
        def do_delete_on_main_thread():
            try:
                result = self._delete_device(track_index, device_index)
                self._send_response(addr, "/jarvis/device/delete/response", result)
            except Exception as e:
                self.log_message("Delete device error: {}".format(str(e)))
                self._send_response(addr, "/jarvis/device/delete/response",
                                  [0, "error", str(e)])
        
        if hasattr(self, 'schedule_message'):
            self.schedule_message(1, do_delete_on_main_thread)
        else:
            do_delete_on_main_thread()
    
    def _delete_device(self, track_index, device_index):
        """Delete a device from a track"""
        song = self._get_song()
        if not song:
            return [0, "error", "Cannot access song"]
        
        tracks = list(song.tracks)
        if track_index < 0 or track_index >= len(tracks):
            return [0, "error", "Invalid track index"]
        
        track = tracks[track_index]
        devices = list(track.devices)
        
        if device_index < 0 or device_index >= len(devices):
            return [0, "error", "Invalid device index"]
        
        try:
            track.delete_device(device_index)
            return [1, "success", "Device deleted"]
        except Exception as e:
            return [0, "error", str(e)]

    def _handle_select_device(self, args, addr):
        """Select a device so it appears in Ableton's Detail View"""
        if len(args) < 2:
            self._send_response(addr, "/jarvis/device/select/response",
                              [0, "error", "Missing arguments: track_index, device_index"])
            return

        track_index = int(args[0])
        device_index = int(args[1])

        def do_select_on_main_thread():
            try:
                result = self._select_device(track_index, device_index)
                self._send_response(addr, "/jarvis/device/select/response", result)
            except Exception as e:
                self.log_message("Select device error: {}".format(str(e)))
                self._send_response(addr, "/jarvis/device/select/response",
                                  [0, "error", str(e)])

        if hasattr(self, 'schedule_message'):
            self.schedule_message(1, do_select_on_main_thread)
        else:
            do_select_on_main_thread()

    def _select_device(self, track_index, device_index):
        """Select a device to show it in Detail View"""
        song = self._get_song()
        if not song:
            return [0, "error", "Cannot access song"]

        tracks = list(song.tracks)
        if track_index < 0 or track_index >= len(tracks):
            return [0, "error", "Invalid track index"]

        track = tracks[track_index]
        devices = list(track.devices)

        if device_index < 0 or device_index >= len(devices):
            return [0, "error", "Invalid device index"]

        try:
            song.view.selected_track = track
            song.view.select_device(devices[device_index])
            return [1, "success", "Device selected in Detail View"]
        except Exception as e:
            return [0, "error", str(e)]

    def _handle_get_track_type(self, args, addr):
        """Get track type information"""
        if len(args) < 1:
            self._send_response(addr, "/jarvis/track/type/response",
                              [0, "error", "Missing track_index", False, False, False, False])
            return

        track_index = int(args[0])

        try:
            result = self._get_track_type(track_index)
            self._send_response(addr, "/jarvis/track/type/response", result)
        except Exception as e:
            self.log_message("Get track type error: {}".format(str(e)))
            self._send_response(addr, "/jarvis/track/type/response",
                              [0, "error", str(e), False, False, False, False])

    def _get_track_type(self, track_index):
        """Determine track type using Live API properties."""
        song = self._get_song()
        if not song:
            return [0, "error", "Cannot access song", False, False, False, False]

        tracks = list(song.tracks)
        if track_index < 0 or track_index >= len(tracks):
            return [0, "error", "Invalid track index", False, False, False, False]

        track = tracks[track_index]

        try:
            has_audio_input = track.has_audio_input
            has_midi_input = track.has_midi_input

            if has_audio_input and not has_midi_input:
                track_type = "audio"
            elif has_midi_input and not has_audio_input:
                track_type = "midi"
            elif has_audio_input and has_midi_input:
                track_type = "hybrid"
            else:
                track_type = "unknown"

            can_audio_fx = has_audio_input
            can_midi_fx = has_midi_input

            return [1, track_type, has_audio_input, has_midi_input, can_audio_fx, can_midi_fx]

        except Exception as e:
            return [0, "error", str(e), False, False, False, False]

    def _handle_debug_browser(self, args, addr):
        """Dump browser structure to log for debugging"""
        self.log_message("=== START BROWSER DEBUG DUMP ===")
        browser = self._get_browser()
        if not browser:
            self.log_message("No browser found")
            return

        try:
            ae = browser.audio_effects
            self.log_message("Audio Effects Children: {}".format(len(list(ae.iter_children))))
            for item in ae.iter_children:
                name = item.name if hasattr(item, 'name') else '?'
                is_folder = item.is_folder if hasattr(item, 'is_folder') else False
                is_loadable = item.is_loadable if hasattr(item, 'is_loadable') else False
                
                child_count = 0
                try:
                    child_count = len(list(item.iter_children))
                except:
                    pass
                    
                self.log_message(" - {} [folder={}, loadable={}, children={}]".format(
                    name, is_folder, is_loadable, child_count))
                
                if "EQ" in name:
                    self.log_message("   >>> Diving into {}...".format(name))
                    try:
                        for child in item.iter_children:
                            c_name = child.name
                            c_folder = child.is_folder
                            c_loadable = child.is_loadable
                            self.log_message("     - {} [folder={}, loadable={}]".format(
                                c_name, c_folder, c_loadable))
                    except Exception as e:
                        self.log_message("     ERROR reading children: {}".format(str(e)))

        except Exception as e:
            self.log_message("Debug error: {}".format(str(e)))
            
        self.log_message("=== END BROWSER DEBUG DUMP ===")
        self._send_response(addr, "/jarvis/debug/response", ["dump_complete"])

    # ==================== AUDIO CLIP CONTROL ====================

    def _handle_create_audio_clip(self, args, addr):
        """Create or replace an audio clip from a local file path."""
        if len(args) < 3:
            self._send_response(addr, "/jarvis/clip/create_audio/response",
                              [0, "error", "Missing arguments: track_index, clip_index, audio_path"])
            return

        track_index = int(args[0])
        clip_index = int(args[1])
        audio_path = os.path.abspath(os.path.expanduser(str(args[2])))

        def do_create_on_main_thread():
            try:
                result = self._create_audio_clip(track_index, clip_index, audio_path)
                self._send_response(addr, "/jarvis/clip/create_audio/response", result)
            except Exception as e:
                self.log_message("Create audio clip error: {}".format(str(e)))
                self._send_response(addr, "/jarvis/clip/create_audio/response",
                                  [0, "error", str(e)])

        if hasattr(self, 'schedule_message'):
            self.schedule_message(1, do_create_on_main_thread)
        else:
            do_create_on_main_thread()

    def _handle_get_clip_audio_path(self, args, addr):
        """Return the source file path for an audio clip."""
        if len(args) < 2:
            self._send_response(addr, "/jarvis/clip/get_audio_path/response",
                              [0, "error", "Missing arguments: track_index, clip_index"])
            return

        track_index = int(args[0])
        clip_index = int(args[1])

        def do_get_on_main_thread():
            try:
                result = self._get_clip_audio_path(track_index, clip_index)
                self._send_response(addr, "/jarvis/clip/get_audio_path/response", result)
            except Exception as e:
                self.log_message("Get clip audio path error: {}".format(str(e)))
                self._send_response(addr, "/jarvis/clip/get_audio_path/response",
                                  [0, "error", str(e)])

        if hasattr(self, 'schedule_message'):
            self.schedule_message(1, do_get_on_main_thread)
        else:
            do_get_on_main_thread()

    def _handle_set_clip_detune(self, args, addr):
        """Set an audio clip's fine pitch in cents."""
        if len(args) < 3:
            self._send_response(addr, "/jarvis/clip/set_detune/response",
                              [0, "error", "Missing arguments: track_index, clip_index, cents"])
            return

        track_index = int(args[0])
        clip_index = int(args[1])
        cents = float(args[2])

        def do_set_on_main_thread():
            try:
                result = self._set_clip_detune(track_index, clip_index, cents)
                self._send_response(addr, "/jarvis/clip/set_detune/response", result)
            except Exception as e:
                self.log_message("Set clip detune error: {}".format(str(e)))
                self._send_response(addr, "/jarvis/clip/set_detune/response",
                                  [0, "error", str(e)])

        if hasattr(self, 'schedule_message'):
            self.schedule_message(1, do_set_on_main_thread)
        else:
            do_set_on_main_thread()

    def _get_clip_slot(self, track_index, clip_index):
        song = self._get_song()
        if not song:
            return None, [0, "error", "Cannot access song"]

        tracks = list(song.tracks)
        if track_index < 0 or track_index >= len(tracks):
            return None, [0, "error", "Invalid track index: {}".format(track_index)]

        clip_slots = list(tracks[track_index].clip_slots)
        if clip_index < 0 or clip_index >= len(clip_slots):
            return None, [0, "error", "Invalid clip index: {}".format(clip_index)]

        return clip_slots[clip_index], None

    def _create_audio_clip(self, track_index, clip_index, audio_path):
        if not os.path.exists(audio_path):
            return [0, "error", "Audio file does not exist: {}".format(audio_path)]

        clip_slot, error = self._get_clip_slot(track_index, clip_index)
        if error:
            return error

        if not hasattr(clip_slot, "create_audio_clip"):
            return [0, "error", "Live API does not expose ClipSlot.create_audio_clip"]

        try:
            if getattr(clip_slot, "has_clip", False):
                clip_slot.delete_clip()
            clip_slot.create_audio_clip(audio_path)
            clip = clip_slot.clip
            clip_name = clip.name if hasattr(clip, "name") else os.path.basename(audio_path)
            return [1, "success", audio_path, clip_name]
        except Exception as e:
            return [0, "error", str(e)]

    def _get_clip_audio_path(self, track_index, clip_index):
        clip_slot, error = self._get_clip_slot(track_index, clip_index)
        if error:
            return error

        if not getattr(clip_slot, "has_clip", False):
            return [0, "error", "Clip slot is empty"]

        clip = clip_slot.clip
        if not getattr(clip, "is_audio_clip", False):
            return [0, "error", "Clip is not an audio clip"]

        audio_path = getattr(clip, "file_path", "")
        if not audio_path:
            return [0, "error", "Clip has no readable file_path"]

        return [1, "success", str(audio_path)]

    def _set_clip_detune(self, track_index, clip_index, cents):
        if cents < -50.0 or cents > 49.0:
            return [0, "error", "Detune cents must be between -50 and 49"]

        clip_slot, error = self._get_clip_slot(track_index, clip_index)
        if error:
            return error

        if not getattr(clip_slot, "has_clip", False):
            return [0, "error", "Clip slot is empty"]

        clip = clip_slot.clip
        if not getattr(clip, "is_audio_clip", False):
            return [0, "error", "Clip is not an audio clip"]

        if not hasattr(clip, "pitch_fine"):
            return [0, "error", "Clip does not expose pitch_fine"]

        try:
            clip.pitch_fine = float(cents)
            return [1, "success", "Detune applied", float(cents)]
        except Exception as e:
            return [0, "error", str(e)]

    def _get_song(self):
        """Get the current Live song object"""
        try:
            if hasattr(self, '_c_instance') and self._c_instance:
                return self._c_instance.song()
            return None
        except:
            return None
    
    def _get_browser(self):
        """Get the Live browser object"""
        try:
            app = Live.Application.get_application()
            return app.browser if hasattr(app, 'browser') else None
        except:
            return None


# The running instance, so LivePilot's lp_chain_add can run the same load on its own
# main-thread tick instead of a round trip through this script's OSC thread.
INSTANCE = None


def create_instance(c_instance):
    """Entry point for Ableton to create the control surface"""
    global INSTANCE
    INSTANCE = JarvisDeviceLoader(c_instance)
    return INSTANCE
