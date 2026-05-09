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
import os
import threading
import socket
import struct
import time

# Import Ableton Framework components
try:
    from _Framework.ControlSurface import ControlSurface
    from _Framework.Task import Task
except ImportError:
    # Fallback for standalone testing
    ControlSurface = object
    Task = None


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
            elif address == "/jarvis/debug/browser":
                self._handle_debug_browser(args, addr)
            elif address == "/jarvis/clip/create_audio":
                self._handle_create_audio_clip(args, addr)
            elif address == "/jarvis/clip/get_audio_path":
                self._handle_get_clip_audio_path(args, addr)
            elif address == "/jarvis/clip/set_detune":
                self._handle_set_clip_detune(args, addr)
            elif address == "/jarvis/test":
                self._send_response(addr, "/jarvis/test/response", ["ok"])
            else:
                self.log_message("Unknown OSC address: {}".format(address))
                
        except Exception as e:
            self.log_message("Error handling OSC: {}".format(str(e)))
    
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

        def do_load_on_main_thread():
            try:
                result = self._load_device_on_track(track_index, device_name, position)
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
    
    def _load_device_on_track(self, track_index, device_name, position=-1):
        """Load a device onto a track by name"""
        self.log_message("Loading device '{}' on track {} at position {}".format(device_name, track_index, position))

        song = self._get_song()
        if not song:
            self.log_message("ERROR: Cannot access song")
            return [0, "error", "Cannot access song"]

        # Get the track
        tracks = list(song.tracks)
        self.log_message("Found {} tracks total".format(len(tracks)))

        if track_index < 0 or track_index >= len(tracks):
            error_msg = "Invalid track index: {} (only {} tracks available)".format(track_index, len(tracks))
            self.log_message("ERROR: " + error_msg)
            return [0, "error", error_msg]

        track = tracks[track_index]

        # Select the track first (required for browser.load_item to work)
        song.view.selected_track = track
        self.log_message("Selected track {} ({})".format(track_index + 1, track.name if hasattr(track, 'name') else 'unnamed'))

        # Find the device in the browser
        browser = self._get_browser()
        if not browser:
            self.log_message("ERROR: Cannot access browser")
            return [0, "error", "Cannot access browser"]

        # Search for the device
        self.log_message("Searching for device: '{}'".format(device_name))
        device_uri = self._find_device_uri(browser, device_name)
        if not device_uri:
            error_msg = "Device not found: {}".format(device_name)
            self.log_message("ERROR: " + error_msg)
            return [0, "error", error_msg]

        self.log_message("Found device, loading...")

        # Count devices before loading
        devices_before = len(list(track.devices))
        self.log_message("Devices on track before load: {}".format(devices_before))

        # Load the device — we are now on the main thread (via schedule_message)
        # so this is safe and won't cause Audio queue timeout
        try:
            browser.load_item(device_uri)
        except Exception as e:
            error_msg = "Failed to load device: {}".format(str(e))
            self.log_message("ERROR: " + error_msg)
            return [0, "error", error_msg]

        # Verify the device was actually loaded.
        # We're on the main thread already (via schedule_message), so we avoid
        # blocking with time.sleep. Instead, check a few times with short waits.
        # Ableton typically loads stock devices within 200-500ms.
        max_retries = 5
        for attempt in range(max_retries):
            # Yield to Ableton briefly — 200ms per check, 1s total max
            # This is acceptable on the main thread for a device load operation
            import time
            time.sleep(0.2)

            try:
                devices_after = len(list(track.devices))
            except Exception:
                continue

            if devices_after > devices_before:
                # Success! Device was added
                try:
                    new_device = list(track.devices)[-1]
                    new_device_name = new_device.name if hasattr(new_device, 'name') else 'Unknown'
                except Exception:
                    new_device_name = device_name
                success_msg = "Loaded '{}' on track {} (verified: {} -> {} devices, attempt {})".format(
                    new_device_name, track_index + 1, devices_before, devices_after, attempt + 1)
                self.log_message(success_msg)
                return [1, "success", "Device loaded: {}".format(new_device_name)]

        # If we get here, device count didn't increase
        self.log_message("WARNING: Device count did not increase after load_item(). May have failed silently.")
        return [0, "error", "Device load may have failed - device count unchanged"]
    
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
    
    def _handle_refresh_plugins(self, args, addr):
        """Force refresh the plugin cache"""
        self._plugin_cache = None
        self._plugin_cache_time = 0
        
        try:
            plugins = self._get_available_plugins()
            self._send_response(addr, "/jarvis/plugins/refresh/response",
                              [1, "success", len(plugins)])
        except Exception as e:
            self._send_response(addr, "/jarvis/plugins/refresh/response",
                              [0, "error", str(e)])
    
    def _get_available_plugins(self, category_filter=None):
        """Get list of all available plugins from Ableton's browser"""
        current_time = time.time()
        
        if (self._plugin_cache is not None and 
            current_time - self._plugin_cache_time < self._cache_ttl):
            plugins = self._plugin_cache
        else:
            # We use the deep search logic to populate this
            plugins = [] 
            # (Simplified for now - can re-implement full scan if needed)
            self._plugin_cache = plugins
            self._plugin_cache_time = current_time
        
        return plugins

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


def create_instance(c_instance):
    """Entry point for Ableton to create the control surface"""
    return JarvisDeviceLoader(c_instance)
