"""
VST Discovery Service

Queries Ableton via the JarvisDeviceLoader Remote Script to discover
available plugins, categorizes them, and provides fuzzy name matching.

Enhanced with tiered plugin name resolution for better matching of
user queries to exact Ableton device names.
"""

import json
import os
import socket
import struct
import time
from typing import Dict, List, Optional, Tuple, Any
from difflib import SequenceMatcher
from dataclasses import dataclass, field

# Import the tiered resolver (lazy import to avoid circular deps)
_resolver = None
def _get_resolver():
    global _resolver
    if _resolver is None:
        try:
            from discovery.plugin_name_resolver import get_plugin_resolver
            _resolver = get_plugin_resolver()
        except ImportError:
            _resolver = None
    return _resolver


@dataclass
class PluginInfo:
    """Information about an available plugin"""
    name: str
    plugin_type: str  # audio_effect, midi_effect, instrument, plugin
    category: str     # eq, compressor, reverb, delay, etc.
    path: str = ""
    aliases: List[str] = field(default_factory=list)
    
    def matches_query(self, query: str) -> float:
        """
        Calculate match score for a search query
        
        Returns:
            Float 0.0-1.0 indicating match quality
        """
        query_lower = query.lower()
        name_lower = self.name.lower()
        
        # Exact match
        if query_lower == name_lower:
            return 1.0
        
        # Name contains query
        if query_lower in name_lower:
            return 0.9
        
        # Query contains name
        if name_lower in query_lower:
            return 0.85
        
        # Check aliases
        for alias in self.aliases:
            alias_lower = alias.lower()
            if query_lower == alias_lower:
                return 0.95
            if query_lower in alias_lower or alias_lower in query_lower:
                return 0.8
        
        # Fuzzy match using SequenceMatcher
        ratio = SequenceMatcher(None, query_lower, name_lower).ratio()
        return ratio * 0.7  # Scale down fuzzy matches
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'name': self.name,
            'type': self.plugin_type,
            'category': self.category,
            'path': self.path,
            'aliases': self.aliases
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'PluginInfo':
        """Create from dictionary"""
        return cls(
            name=data.get('name', ''),
            plugin_type=data.get('type', 'plugin'),
            category=data.get('category', 'unknown'),
            path=data.get('path', ''),
            aliases=data.get('aliases', [])
        )


class VSTDiscoveryService:
    """
    Service for discovering and managing available VST/AU/Native plugins
    
    Communicates with the JarvisDeviceLoader Remote Script to query
    Ableton's browser for available plugins.
    """
    
    def __init__(self, 
                 osc_host: str = "127.0.0.1",
                 osc_send_port: int = 11002,
                 osc_recv_port: int = 11003,
                 cache_file: str = "config/vst_cache.json"):
        """
        Initialize the VST Discovery Service
        
        Args:
            osc_host: Host for OSC communication
            osc_send_port: Port to send OSC messages to Remote Script
            osc_recv_port: Port to receive OSC responses
            cache_file: Path to plugin cache file
        """
        self.osc_host = osc_host
        self.osc_send_port = osc_send_port
        self.osc_recv_port = osc_recv_port
        self.cache_file = cache_file
        
        # Plugin cache
        self._plugins: List[PluginInfo] = []
        self._plugins_by_category: Dict[str, List[PluginInfo]] = {}
        self._cache_loaded = False
        self._last_refresh = 0
        
        # Known plugin aliases for fuzzy matching
        self._aliases = self._load_plugin_aliases()
        
        # Load cache on init
        self._load_cache()

    def _check_connection_health(self, timeout: float = 2.0) -> Dict[str, Any]:
        """
        Verify JarvisDeviceLoader is responding before attempting operations.

        Args:
            timeout: Response timeout in seconds

        Returns:
            Dict with:
            - healthy: bool - Whether connection is healthy
            - response_time_ms: float - Response time in milliseconds
            - error: Optional[str] - Error message if unhealthy
        """
        import time
        start = time.time()

        try:
            # Send test ping to /jarvis/test endpoint
            response = self._send_osc_request("/jarvis/test", [], timeout=timeout)
            elapsed_ms = (time.time() - start) * 1000

            if response:
                return {
                    "healthy": True,
                    "response_time_ms": elapsed_ms,
                    "error": None
                }
            else:
                return {
                    "healthy": False,
                    "response_time_ms": elapsed_ms,
                    "error": f"No response after {elapsed_ms:.0f}ms"
                }
        except Exception as e:
            elapsed_ms = (time.time() - start) * 1000
            return {
                "healthy": False,
                "response_time_ms": elapsed_ms,
                "error": str(e)
            }

    def _load_plugin_aliases(self) -> Dict[str, List[str]]:
        """Load known plugin aliases for better matching"""
        return {
            # FabFilter
            "FabFilter Pro-Q 3": ["Pro-Q", "Pro Q", "ProQ", "Pro-Q 3", "FabFilter EQ"],
            "FabFilter Pro-C 2": ["Pro-C", "Pro C", "ProC", "Pro-C 2", "FabFilter Compressor"],
            "FabFilter Pro-R": ["Pro-R", "FabFilter Reverb"],
            "FabFilter Pro-L 2": ["Pro-L", "FabFilter Limiter"],
            "FabFilter Saturn 2": ["Saturn", "FabFilter Saturation"],
            
            # Waves
            "SSL E-Channel": ["SSL Channel", "Waves SSL"],
            "SSL G-Master Buss Compressor": ["SSL Bus Comp", "SSL Buss"],
            "CLA-2A": ["LA-2A", "CLA2A"],
            "CLA-76": ["1176", "CLA76"],
            "API 2500": ["API Compressor"],
            "PuigTec EQP-1A": ["Pultec", "PuigTec"],
            "H-Reverb": ["Waves Reverb"],
            "R-Verb": ["Waves Reverb"],
            
            # Soundtoys
            "Decapitator": ["Soundtoys Saturation"],
            "EchoBoy": ["Soundtoys Delay", "Echo Boy"],
            "Little Plate": ["Soundtoys Reverb"],
            "Radiator": ["Soundtoys Warming"],
            "Devil-Loc": ["Soundtoys Crusher"],
            
            # iZotope
            "Ozone": ["iZotope Mastering"],
            "Neutron": ["iZotope Mixing"],
            "RX": ["iZotope Repair"],
            "Nectar": ["iZotope Vocal"],
            
            # UAD / Universal Audio
            "Neve 1073": ["1073", "UAD Neve"],
            "Neve 88RS": ["UAD Channel Strip"],
            "LA-2A": ["Teletronix", "UAD LA-2A"],
            "1176": ["UAD 1176"],
            "Pultec EQP-1A": ["UAD Pultec"],
            
            # Ableton Native
            "EQ Eight": ["Ableton EQ", "EQ8", "Eight Band EQ"],
            "EQ Three": ["Ableton 3-Band EQ", "EQ3"],
            "Compressor": ["Ableton Compressor"],
            "Glue Compressor": ["Glue", "Bus Compressor", "SSL Style"],
            "Multiband Dynamics": ["Multiband Compressor", "MB Dynamics"],
            "Limiter": ["Ableton Limiter"],
            "Saturator": ["Ableton Saturation"],
            "Pedal": ["Ableton Distortion"],
            "Reverb": ["Ableton Reverb"],
            "Delay": ["Ableton Delay", "Simple Delay"],
            "Echo": ["Ableton Echo", "Ping Pong"],
            "Chorus-Ensemble": ["Ableton Chorus"],
            "Phaser": ["Ableton Phaser"],
            "Flanger": ["Ableton Flanger"],
            "Auto Filter": ["Filter", "Ableton Filter"],
            "Auto Pan": ["Tremolo", "Panner"],
            "Utility": ["Gain", "Phase", "Width"],
            "Spectrum": ["Analyzer"],
            "Tuner": ["Ableton Tuner"],
            
            # De-essers
            "De-Esser": ["DeEsser", "Sibilance Control"],
            "Soothe2": ["Soothe", "Resonance Suppressor"],
            "Spiff": ["Transient Designer"],
            
            # Vocal specific
            "Vocal Rider": ["Auto Gain", "Volume Rider"],
            "Waves Tune": ["Pitch Correction", "Auto-Tune"],
            "Auto-Tune": ["Antares", "Pitch Correction"],
            "Melodyne": ["Pitch Editing"],
        }
    
    def _load_cache(self) -> bool:
        """Load plugin cache from file"""
        if not os.path.exists(self.cache_file):
            return False
        
        try:
            with open(self.cache_file, 'r') as f:
                data = json.load(f)
            
            self._plugins = [PluginInfo.from_dict(p) for p in data.get('plugins', [])]
            self._last_refresh = data.get('last_refresh', 0)
            self._build_category_index()
            self._cache_loaded = True
            
            return True
        except Exception as e:
            print(f"[VSTDiscovery] Error loading cache: {e}")
            return False
    
    def _save_cache(self):
        """Save plugin cache to file"""
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            
            data = {
                'plugins': [p.to_dict() for p in self._plugins],
                'last_refresh': self._last_refresh,
                'plugin_count': len(self._plugins)
            }
            
            with open(self.cache_file, 'w') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            print(f"[VSTDiscovery] Error saving cache: {e}")
    
    def _build_category_index(self):
        """Build index of plugins by category"""
        self._plugins_by_category = {}
        
        for plugin in self._plugins:
            category = plugin.category.lower()
            if category not in self._plugins_by_category:
                self._plugins_by_category[category] = []
            self._plugins_by_category[category].append(plugin)
    
    def _apply_aliases(self):
        """Apply known aliases to plugins"""
        for plugin in self._plugins:
            if plugin.name in self._aliases:
                plugin.aliases = self._aliases[plugin.name]
    
    # ==================== OSC COMMUNICATION ====================
    
    def _build_osc_message(self, address: str, args: List) -> bytes:
        """Build an OSC message"""
        # Address (null-terminated, padded to 4 bytes)
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
    
    def _parse_osc_response(self, data: bytes) -> Tuple[str, List]:
        """Parse an OSC response message"""
        # Address
        null_idx = data.index(b'\x00')
        address = data[:null_idx].decode('utf-8')
        addr_size = (null_idx + 4) & ~3
        
        if len(data) <= addr_size:
            return address, []
        
        # Type tag
        type_start = addr_size
        if data[type_start:type_start+1] != b',':
            return address, []
        
        type_null = data.index(b'\x00', type_start)
        type_tag = data[type_start+1:type_null].decode('utf-8')
        type_size = ((type_null - type_start) + 4) & ~3
        
        # Arguments
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
    
    def _send_osc_request(self, address: str, args: List = None, timeout: float = 5.0, max_retries: int = 3) -> Optional[Tuple[str, List]]:
        """
        Send an OSC request and wait for response with retry logic and exponential backoff.

        Args:
            address: OSC address pattern
            args: Arguments to send
            timeout: Response timeout in seconds
            max_retries: Number of retry attempts (default: 3)

        Returns:
            Tuple of (response_address, response_args) or None

        Raises:
            ConnectionError: If all retries fail with connection issues
            TimeoutError: If all retries timeout
        """
        import time
        args = args or []
        last_error = None
        base_delay = 0.3  # Initial retry delay in seconds

        for attempt in range(max_retries + 1):
            sock = None
            try:
                # Create UDP socket with reuse option
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.settimeout(timeout)

                # Bind to receive port
                try:
                    sock.bind((self.osc_host, self.osc_recv_port))
                except OSError as e:
                    if e.errno == 10048:  # Address already in use (Windows)
                        # CRITICAL: JarvisDeviceLoader responds to fixed port 11003.
                        # If we are not bound to that port, we will never receive responses.
                        raise OSError(
                            f"Response port {self.osc_recv_port} is already in use. "
                            "Jarvis needs exclusive access to receive JarvisDeviceLoader replies."
                        )
                    raise

                # Build and send message
                message = self._build_osc_message(address, args)
                sock.sendto(message, (self.osc_host, self.osc_send_port))

                # Wait for response
                data, addr = sock.recvfrom(65535)
                sock.close()

                # Parse and return response
                response = self._parse_osc_response(data)
                return response

            except socket.timeout:
                last_error = TimeoutError(f"Timeout waiting for response to {address} (attempt {attempt + 1}/{max_retries + 1})")
                print(f"[VSTDiscovery] {last_error}")

            except ConnectionResetError as e:
                last_error = ConnectionError(f"Connection reset (WinError 10054) on {address} (attempt {attempt + 1}/{max_retries + 1}): {e}")
                print(f"[VSTDiscovery] {last_error}")
                print(f"[VSTDiscovery] Hint: JarvisDeviceLoader on port {self.osc_send_port} may not be running in Ableton")

            except OSError as e:
                last_error = OSError(f"Socket error on {address} (attempt {attempt + 1}/{max_retries + 1}): {e}")
                print(f"[VSTDiscovery] {last_error}")

            except Exception as e:
                last_error = Exception(f"Unexpected error on {address} (attempt {attempt + 1}/{max_retries + 1}): {e}")
                print(f"[VSTDiscovery] {last_error}")

            finally:
                # Ensure socket is always closed
                if sock:
                    try:
                        sock.close()
                    except:
                        pass

            # Exponential backoff before retry
            if attempt < max_retries:
                delay = min(base_delay * (2 ** attempt), 2.0)
                print(f"[VSTDiscovery] Retrying in {delay:.2f}s...")
                time.sleep(delay)

        # All retries exhausted
        print(f"[VSTDiscovery] All {max_retries + 1} attempts failed for {address}")
        if isinstance(last_error, (ConnectionError, TimeoutError)):
            raise last_error
        return None
    
    # ==================== PUBLIC API ====================
    
    def refresh_plugins(self) -> bool:
        """
        Refresh the plugin list by querying Ableton
        
        Returns:
            True if successful, False otherwise
        """
        print("[VSTDiscovery] Refreshing plugin list from Ableton...")
        
        # JarvisDeviceLoader now paginates /jarvis/plugins/get to avoid UDP size limits.
        # Response format: [1, "success", total, offset, limit, plugins_json]
        all_plugins: List[Dict] = []
        offset = 0
        limit = 200
        total = None

        # Hard cap to prevent infinite loops if something goes wrong
        for _ in range(1000):
            response = self._send_osc_request("/jarvis/plugins/get", ["", offset, limit], timeout=30.0)
            if not response:
                print("[VSTDiscovery] Failed to get response from Ableton")
                return False

            _address, args = response
            if len(args) < 3 or args[0] != 1:
                print(f"[VSTDiscovery] Error response: {args}")
                return False

            # New format has paging info; old format had [1, "success", count, json]
            try:
                if len(args) >= 6 and isinstance(args[2], int):
                    total = int(args[2])
                    page_offset = int(args[3])
                    page_limit = int(args[4])
                    plugins_json = args[5] if len(args) > 5 else "[]"
                else:
                    # Back-compat: treat as single page
                    total = int(args[2])
                    page_offset = 0
                    page_limit = total
                    plugins_json = args[3] if len(args) > 3 else "[]"

                page_data = json.loads(plugins_json)
                if not isinstance(page_data, list):
                    page_data = []

                # If we requested an offset but got something else, trust the data length and continue.
                all_plugins.extend(page_data)

                if total is not None and len(all_plugins) >= total:
                    break

                # Advance
                offset = page_offset + max(1, len(page_data))

                # Stop if the page came back empty (avoid infinite loop)
                if len(page_data) == 0:
                    break

            except Exception as e:
                print(f"[VSTDiscovery] Error parsing plugins page: {e}")
                return False

        if not all_plugins:
            print("[VSTDiscovery] No plugins returned")
            return False

        # Parse plugin data
        try:
            self._plugins = [PluginInfo.from_dict(p) for p in all_plugins]
            self._apply_aliases()
            self._build_category_index()
            self._last_refresh = time.time()
            self._cache_loaded = True
            
            self._save_cache()
            
            print(f"[VSTDiscovery] Loaded {len(self._plugins)} plugins")
            return True
            
        except Exception as e:
            print(f"[VSTDiscovery] Error parsing plugins: {e}")
            return False
    
    def get_all_plugins(self) -> List[PluginInfo]:
        """Get all available plugins"""
        if not self._cache_loaded:
            self._load_cache()
        return self._plugins
    
    def get_plugins_by_category(self, category: str) -> List[PluginInfo]:
        """
        Get plugins filtered by category
        
        Args:
            category: Category name (eq, compressor, reverb, etc.)
            
        Returns:
            List of matching plugins
        """
        if not self._cache_loaded:
            self._load_cache()
        
        category_lower = category.lower()
        return self._plugins_by_category.get(category_lower, [])
    
    def resolve_plugin_name(self, query: str, category: Optional[str] = None) -> Tuple[Optional[str], float, str]:
        """
        Resolve a plugin name query using tiered resolution strategy.

        This method uses the PluginNameResolver for more accurate matching:
        1. Exact match against installed plugins
        2. Alias lookup from plugin_aliases.json
        3. Fuzzy matching with difflib

        Args:
            query: Plugin name or colloquial name (e.g., "EQ8", "Pro-Q")
            category: Optional category filter

        Returns:
            Tuple of (resolved_name, confidence, resolution_tier)
            resolution_tier is one of: "exact", "alias", "fuzzy", "not_found"
        """
        resolver = _get_resolver()

        if resolver:
            # Use tiered resolver
            if category:
                # Prepare plugin data for category filtering
                plugin_data = [
                    {"name": p.name, "category": p.category}
                    for p in self._plugins
                ]
                result = resolver.resolve_with_category(query, category, plugin_data)
            else:
                result = resolver.resolve(query)

            return (result.resolved_name, result.confidence, result.resolution_tier)

        # Fallback to legacy matching if resolver unavailable
        candidates = self.find_plugins(query, category, limit=1, min_score=0.3)
        if candidates:
            plugin = candidates[0]
            score = plugin.matches_query(query)
            return (plugin.name, score, "legacy")

        return (None, 0.0, "not_found")

    def find_plugin(self, query: str, category: Optional[str] = None) -> Optional[PluginInfo]:
        """
        Find the best matching plugin for a query.

        Enhanced with tiered resolution strategy for better matching:
        - Handles colloquial names (e.g., "EQ8" -> "EQ Eight")
        - Handles typos and variations
        - Uses alias mappings from config

        Args:
            query: Plugin name or partial match
            category: Optional category filter

        Returns:
            Best matching PluginInfo or None
        """
        if not self._cache_loaded:
            self._load_cache()

        # Try tiered resolution first
        resolved_name, confidence, tier = self.resolve_plugin_name(query, category)

        if resolved_name and confidence >= 0.5:
            # Find the PluginInfo for resolved name
            for plugin in self._plugins:
                if plugin.name == resolved_name:
                    return plugin

            # If not found in plugins but resolved, it might be a native device
            # Create a synthetic PluginInfo
            return PluginInfo(
                name=resolved_name,
                plugin_type="audio_effect",
                category=category or "unknown",
                path=f"Audio Effects/{resolved_name}"
            )

        # Fallback to legacy find_plugins method
        candidates = self.find_plugins(query, category, limit=1)
        return candidates[0] if candidates else None
    
    def find_plugins(self, 
                     query: str, 
                     category: Optional[str] = None,
                     limit: int = 5,
                     min_score: float = 0.3) -> List[PluginInfo]:
        """
        Find plugins matching a query
        
        Args:
            query: Plugin name or partial match
            category: Optional category filter
            limit: Maximum number of results
            min_score: Minimum match score (0.0-1.0)
            
        Returns:
            List of matching plugins, sorted by match score
        """
        if not self._cache_loaded:
            self._load_cache()
        
        # Get candidate plugins
        if category:
            candidates = self.get_plugins_by_category(category)
        else:
            candidates = self._plugins
        
        # Score each candidate
        scored = []
        for plugin in candidates:
            score = plugin.matches_query(query)
            if score >= min_score:
                scored.append((score, plugin))
        
        # Sort by score descending
        scored.sort(key=lambda x: x[0], reverse=True)
        
        # Return top matches
        return [p for _, p in scored[:limit]]
    
    def find_alternative(self, 
                        desired_plugin: str, 
                        plugin_type: str) -> Optional[PluginInfo]:
        """
        Find an alternative plugin when the desired one isn't available
        
        Args:
            desired_plugin: Name of desired plugin
            plugin_type: Type/category of plugin (eq, compressor, etc.)
            
        Returns:
            Alternative PluginInfo or None
        """
        # First try direct match
        exact = self.find_plugin(desired_plugin, plugin_type)
        if exact and exact.matches_query(desired_plugin) > 0.8:
            return exact
        
        # Get all plugins in category
        category_plugins = self.get_plugins_by_category(plugin_type)
        
        # Prefer Ableton native devices as fallbacks
        native_fallbacks = {
            'eq': 'EQ Eight',
            'compressor': 'Compressor',
            'reverb': 'Reverb',
            'delay': 'Delay',
            'distortion': 'Saturator',
            'limiter': 'Limiter',
            'dynamics': 'Multiband Dynamics',
            'modulation': 'Chorus-Ensemble',
            'utility': 'Utility',
        }
        
        fallback_name = native_fallbacks.get(plugin_type.lower())
        if fallback_name:
            for plugin in category_plugins:
                if plugin.name.lower() == fallback_name.lower():
                    return plugin
        
        # Return first available in category
        return category_plugins[0] if category_plugins else None
    
    def get_categories(self) -> List[str]:
        """Get list of available categories"""
        if not self._cache_loaded:
            self._load_cache()
        return list(self._plugins_by_category.keys())
    
    def load_device_on_track(self, track_index: int, device_name: str,
                             position: int = -1,
                             timeout: Optional[float] = None) -> Dict:
        """
        Load a device onto a track via OSC
        
        Args:
            track_index: 0-based track index
            device_name: Name of device to load
            position: Position in device chain (-1 = end)
            timeout: Optional response timeout in seconds
            
        Returns:
            Result dict with success status and message
        """
        # Try to resolve the plugin name first
        resolved_plugin = self.find_plugin(device_name)
        final_name = device_name
        
        if resolved_plugin:
            if resolved_plugin.name != device_name:
                print(f"[VSTDiscovery] Auto-resolved '{device_name}' to '{resolved_plugin.name}'")
            final_name = resolved_plugin.name
            
        if timeout is None:
            try:
                timeout = float(os.environ.get("LIVE_PILOT_DEVICE_LOAD_TIMEOUT_SEC", "30"))
            except ValueError:
                timeout = 30.0

        response = self._send_osc_request(
            "/jarvis/device/load",
            [track_index, final_name, position],
            timeout=timeout,
            max_retries=1,
        )
        
        if not response:
            return {'success': False, 'message': 'No response from Ableton'}
        
        address, args = response
        
        if len(args) >= 2:
            return {
                'success': args[0] == 1,
                'status': args[1] if len(args) > 1 else 'unknown',
                'message': args[2] if len(args) > 2 else ''
            }
        
        return {'success': False, 'message': 'Invalid response format'}

    def learn_plugin_alias(self, alias: str, correct_name: str) -> bool:
        """
        Teach the resolver a new alias from user correction.

        Call this when a user corrects a plugin name resolution.
        The mapping will be persisted to plugin_aliases.json.

        Args:
            alias: The name the user typed (e.g., "ProQ3")
            correct_name: The correct plugin name (e.g., "FabFilter Pro-Q 3")

        Returns:
            True if the alias was successfully learned
        """
        resolver = _get_resolver()
        if resolver:
            return resolver.learn_alias(alias, correct_name)
        return False

    def get_resolution_suggestions(self, query: str, limit: int = 5) -> List[Tuple[str, float]]:
        """
        Get suggested plugin names for a query (for autocomplete/correction UI).

        Args:
            query: The partial or incorrect plugin name
            limit: Maximum number of suggestions

        Returns:
            List of (plugin_name, confidence) tuples sorted by confidence
        """
        resolver = _get_resolver()
        if resolver:
            return resolver.suggest_corrections(query, limit)

        # Fallback to basic matching
        candidates = self.find_plugins(query, limit=limit, min_score=0.3)
        return [(p.name, p.matches_query(query)) for p in candidates]

    def test_connection(self) -> bool:
        """Test connection to Ableton Remote Script"""
        response = self._send_osc_request("/jarvis/test", [], timeout=2.0)
        return response is not None


# Singleton instance
_vst_discovery = None


def get_vst_discovery() -> VSTDiscoveryService:
    """Get the singleton VSTDiscoveryService instance"""
    global _vst_discovery
    if _vst_discovery is None:
        _vst_discovery = VSTDiscoveryService()
    return _vst_discovery

