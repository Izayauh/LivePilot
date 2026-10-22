"""
Chain Test Utilities

Shared utilities for standalone and integration chain building tests.
Provides result tracking, reporting, and common operations.
"""

import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ableton_controls.controller import ableton
from ableton_controls.reliable_params import ReliableParameterController


@dataclass
class ParameterResult:
    """Result of a single parameter set operation"""
    param_name: str
    param_index: Optional[int]
    requested_value: float
    actual_value: Optional[float]
    success: bool
    verified: bool
    message: str
    attempts: int = 1
    
    def to_dict(self) -> Dict:
        return {
            "param_name": self.param_name,
            "param_index": self.param_index,
            "requested": self.requested_value,
            "actual": self.actual_value,
            "success": self.success,
            "verified": self.verified,
            "message": self.message,
            "attempts": self.attempts
        }


@dataclass
class DeviceResult:
    """Result of a single device load and configure operation"""
    device_name: str
    device_type: str
    device_index: Optional[int]
    load_success: bool
    load_message: str
    ready: bool
    param_results: List[ParameterResult] = field(default_factory=list)
    
    @property
    def params_succeeded(self) -> int:
        return sum(1 for p in self.param_results if p.success)
    
    @property
    def params_failed(self) -> int:
        return sum(1 for p in self.param_results if not p.success)
    
    @property
    def param_success_rate(self) -> float:
        if not self.param_results:
            return 1.0
        return self.params_succeeded / len(self.param_results)
    
    def to_dict(self) -> Dict:
        return {
            "device_name": self.device_name,
            "device_type": self.device_type,
            "device_index": self.device_index,
            "load_success": self.load_success,
            "load_message": self.load_message,
            "ready": self.ready,
            "params_succeeded": self.params_succeeded,
            "params_failed": self.params_failed,
            "param_success_rate": self.param_success_rate,
            "param_results": [p.to_dict() for p in self.param_results]
        }


@dataclass
class ChainTestResult:
    """Result of a complete chain building test"""
    chain_name: str
    track_index: int
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    device_results: List[DeviceResult] = field(default_factory=list)
    
    @property
    def devices_loaded(self) -> int:
        return sum(1 for d in self.device_results if d.load_success)
    
    @property
    def devices_failed(self) -> int:
        return sum(1 for d in self.device_results if not d.load_success)
    
    @property
    def device_success_rate(self) -> float:
        if not self.device_results:
            return 0.0
        return self.devices_loaded / len(self.device_results)
    
    @property
    def params_set(self) -> int:
        return sum(d.params_succeeded for d in self.device_results)
    
    @property
    def params_failed(self) -> int:
        return sum(d.params_failed for d in self.device_results)
    
    @property
    def param_success_rate(self) -> float:
        total = self.params_set + self.params_failed
        if total == 0:
            return 1.0
        return self.params_set / total
    
    @property
    def execution_time(self) -> float:
        if self.end_time is None:
            return time.time() - self.start_time
        return self.end_time - self.start_time
    
    @property
    def overall_success(self) -> bool:
        """Chain is successful if 95%+ devices loaded AND 90%+ params set"""
        return self.device_success_rate >= 0.95 and self.param_success_rate >= 0.90
    
    def finish(self):
        """Mark the test as finished"""
        self.end_time = time.time()
    
    def to_dict(self) -> Dict:
        return {
            "chain_name": self.chain_name,
            "track_index": self.track_index,
            "execution_time": self.execution_time,
            "devices_loaded": self.devices_loaded,
            "devices_failed": self.devices_failed,
            "device_success_rate": self.device_success_rate,
            "params_set": self.params_set,
            "params_failed": self.params_failed,
            "param_success_rate": self.param_success_rate,
            "overall_success": self.overall_success,
            "device_results": [d.to_dict() for d in self.device_results]
        }


def print_chain_report(result: ChainTestResult):
    """Pretty-print chain test results"""
    print("\n" + "=" * 60)
    print(f"📊 CHAIN TEST REPORT: {result.chain_name}")
    print("=" * 60)
    
    # Overall status
    status = "✅ PASSED" if result.overall_success else "❌ FAILED"
    print(f"\n{status}")
    print(f"⏱️  Execution Time: {result.execution_time:.2f}s")
    
    # Device summary
    print(f"\n📦 DEVICES:")
    print(f"   Loaded: {result.devices_loaded}/{len(result.device_results)} "
          f"({result.device_success_rate*100:.1f}%)")
    
    # Parameter summary
    total_params = result.params_set + result.params_failed
    print(f"\n🎛️  PARAMETERS:")
    print(f"   Set: {result.params_set}/{total_params} "
          f"({result.param_success_rate*100:.1f}%)")
    
    # Per-device details
    print("\n📋 DEVICE DETAILS:")
    for i, device in enumerate(result.device_results):
        load_icon = "✅" if device.load_success else "❌"
        ready_icon = "✅" if device.ready else "⚠️"
        
        print(f"\n   {i+1}. {device.device_name} ({device.device_type})")
        print(f"      Load: {load_icon}  Ready: {ready_icon}")
        
        if device.param_results:
            print(f"      Parameters: {device.params_succeeded}/{len(device.param_results)} "
                  f"({device.param_success_rate*100:.1f}%)")
            
            # Show failed parameters
            failed = [p for p in device.param_results if not p.success]
            if failed:
                print("      ❌ Failed:")
                for p in failed[:5]:  # Show first 5
                    print(f"         - {p.param_name}: {p.message}")
    
    # Failure summary
    if result.params_failed > 0:
        print("\n⚠️  FAILURE SUMMARY:")
        failure_types = {}
        for device in result.device_results:
            for param in device.param_results:
                if not param.success:
                    msg_key = param.message[:40]
                    failure_types[msg_key] = failure_types.get(msg_key, 0) + 1
        
        for msg, count in sorted(failure_types.items(), key=lambda x: -x[1]):
            print(f"   {count}x: {msg}")
    
    print("\n" + "=" * 60 + "\n")


def load_chain_definition(chain_key: str) -> Optional[Dict]:
    """Load a chain definition from plugin_chains.json"""
    knowledge_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "config", "vocal_chains.json"
    )
    
    if not os.path.exists(knowledge_file):
        print(f"❌ Knowledge file not found: {knowledge_file}")
        return None
    
    with open(knowledge_file, 'r') as f:
        data = json.load(f)
    
    chains = data.get("chains", {})
    
    # Try exact match
    if chain_key in chains:
        return chains[chain_key]
    
    # Try partial match
    for key, chain_data in chains.items():
        if chain_key.lower() in key.lower():
            return chain_data
    
    return None


def get_preset_chain(preset_name: str, track_type: str = "vocal") -> Optional[List[Dict]]:
    """Get a preset chain configuration with actual parameter values"""
    
    # Predefined chains with actual parameter values for testing
    presets = {
        "vocal_basic": [
            {
                "type": "eq",
                "name": "EQ Eight",
                "settings": {
                    "1 Filter On A": 1.0,  # Enable band 1
                    "1 Frequency A": 100.0,  # High pass at 100Hz
                    "1 Gain A": 0.0,
                }
            },
            {
                "type": "compressor",
                "name": "Compressor",
                "settings": {
                    "Threshold": -18.0,
                    "Ratio": 3.0,
                    "Attack": 15.0,
                    "Release": 150.0,
                }
            },
            {
                "type": "reverb",
                "name": "Reverb",
                "settings": {
                    "Decay Time": 2.0,
                    "Dry/Wet": 0.25,
                }
            },
        ],
        "vocal_full": [
            {
                "type": "eq",
                "name": "EQ Eight",
                "settings": {
                    "1 Filter On A": 1.0,
                    "1 Frequency A": 80.0,
                    "1 Gain A": 0.0,
                }
            },
            {
                "type": "compressor",
                "name": "Compressor",
                "settings": {
                    "Threshold": -15.0,
                    "Ratio": 4.0,
                    "Attack": 10.0,
                    "Release": 100.0,
                }
            },
            {
                "type": "de-esser",
                "name": "Multiband Dynamics",
                "settings": {
                    # Multiband Dynamics as de-esser
                    "High Crossover": 6000.0,
                }
            },
            {
                "type": "saturation",
                "name": "Saturator",
                "settings": {
                    "Drive": 6.0,
                    "Dry/Wet": 0.4,
                }
            },
            {
                "type": "eq",
                "name": "EQ Eight",
                "settings": {
                    "3 Frequency A": 3000.0,
                    "3 Gain A": 2.0,
                }
            },
            {
                "type": "reverb",
                "name": "Reverb",
                "settings": {
                    "Decay Time": 2.5,
                    "Dry/Wet": 0.3,
                    "Predelay": 40.0,
                }
            },
            {
                "type": "delay",
                "name": "Delay",
                "settings": {
                    "Dry/Wet": 0.15,
                    "Feedback": 0.3,
                }
            },
        ],
        "drum_bus": [
            {
                "type": "eq",
                "name": "EQ Eight",
                "settings": {
                    "1 Frequency A": 60.0,
                    "4 Frequency A": 300.0,
                    "4 Gain A": -2.0,
                }
            },
            {
                "type": "compressor",
                "name": "Glue Compressor",
                "settings": {
                    "Threshold": -10.0,
                    "Ratio": 4.0,
                    "Attack": 30.0,
                    "Release": 0.4,  # Auto release
                }
            },
            {
                "type": "saturation",
                "name": "Saturator",
                "settings": {
                    "Drive": 4.0,
                    "Dry/Wet": 0.3,
                }
            },
            {
                "type": "limiter",
                "name": "Limiter",
                "settings": {
                    "Gain": 2.0,
                }
            },
        ],
    }
    
    key = f"{track_type}_{preset_name}" if preset_name not in presets else preset_name
    
    if key in presets:
        return presets[key]
    
    # Try just preset name
    if preset_name in presets:
        return presets[preset_name]
    
    return None


def get_billie_eilish_chain() -> List[Dict]:
    """Get Billie Eilish vocal chain with specific parameter values"""
    return [
        {
            "type": "eq",
            "name": "EQ Eight",
            "purpose": "high_pass",
            "settings": {
                "1 Filter On A": 1.0,
                "1 Frequency A": 90.0,  # 80-100Hz high pass
                "1 Filter Type A": 4.0,  # HP12 (High pass 12dB/oct) - type values: 4=HP12, 5=HP24, 6=HP48
            }
        },
        {
            "type": "compressor",
            "name": "Compressor",
            "purpose": "gentle_control",
            "settings": {
                "Threshold": -20.0,
                "Ratio": 2.0,  # 2:1 gentle ratio
                "Attack": 20.0,
                "Release": 200.0,
            }
        },
        {
            "type": "de-esser",
            "name": "Multiband Dynamics",
            "purpose": "sibilance_control",
            "settings": {
                "High Crossover": 7000.0,  # 6-8kHz de-essing range
            }
        },
        {
            "type": "eq",
            "name": "EQ Eight",
            "purpose": "presence",
            "settings": {
                "3 Filter On A": 1.0,
                "3 Frequency A": 2500.0,  # 2-3kHz presence boost
                "3 Gain A": 1.5,  # Subtle boost
            }
        },
        {
            "type": "saturation",
            "name": "Saturator",
            "purpose": "warmth",
            "settings": {
                "Drive": 3.0,  # Subtle warmth
                "Dry/Wet": 0.35,
            }
        },
        {
            "type": "reverb",
            "name": "Reverb",
            "purpose": "atmosphere",
            "settings": {
                "Decay Time": 3.5,  # Long decay
                "Dry/Wet": 0.35,  # Dark reverb mix
                "Predelay": 40.0,  # 30-50ms predelay
            }
        },
    ]


def verify_device_loaded(track_index: int, device_index: int) -> bool:
    """Check if a device exists and is accessible at the given position"""
    try:
        result = ableton.get_num_devices_sync(track_index)
        if result.get("success"):
            num_devices = result.get("count", 0)
            return device_index < num_devices
    except Exception:
        pass
    return False


def get_device_count(track_index: int) -> int:
    """Get the number of devices on a track"""
    try:
        result = ableton.get_num_devices_sync(track_index)
        if result.get("success"):
            return result.get("count", 0)
    except Exception:
        pass
    return 0


def delete_device_via_osc(track_index: int, device_index: int, 
                         timeout: float = 2.0, verbose: bool = False) -> Dict[str, Any]:
    """
    Delete a device using the JarvisDeviceLoader OSC endpoint on port 11002.
    
    Args:
        track_index: Track index (0-based)
        device_index: Device index to delete
        timeout: Timeout for response (seconds)
        verbose: Print detailed logging
        
    Returns:
        Dict with 'success', 'message', and 'response' keys
    """
    import socket
    import struct
    
    if verbose:
        print(f"      📤 Deleting device {device_index} on track {track_index} via OSC...")
    
    try:
        # Build OSC message for JarvisDeviceLoader (port 11002)
        address = "/jarvis/device/delete"
        
        # Address (null-terminated, padded to 4 bytes)
        addr_bytes = address.encode('utf-8') + b'\x00'
        addr_padded = addr_bytes + b'\x00' * ((4 - len(addr_bytes) % 4) % 4)
        
        # Type tag: two integers (track_index, device_index)
        type_tag = ',ii'
        type_bytes = type_tag.encode('utf-8') + b'\x00'
        type_padded = type_bytes + b'\x00' * ((4 - len(type_bytes) % 4) % 4)
        
        # Arguments
        arg_data = struct.pack('>i', track_index)
        arg_data += struct.pack('>i', device_index)
        
        message = addr_padded + type_padded + arg_data
        
        # Send to JarvisDeviceLoader port (11002)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        
        # Bind to response port (11003) to receive response
        try:
            sock.bind(('127.0.0.1', 11003))
        except OSError:
            # Port might already be in use, try a random port
            sock.bind(('127.0.0.1', 0))
        
        sock.sendto(message, ('127.0.0.1', 11002))
        
        if verbose:
            print(f"      📨 Sent delete request to port 11002")
        
        # Wait for response
        try:
            data, addr = sock.recvfrom(65535)
            sock.close()
            
            # Parse response - JarvisDeviceLoader sends [success, status, message]
            # Simple parsing: look for "success" in response
            response_str = data.decode('utf-8', errors='ignore')
            success = b'success' in data.lower() if isinstance(data, bytes) else 'success' in str(data).lower()
            
            if verbose:
                print(f"      📬 Response received: {response_str[:100]}")
            
            return {
                "success": success or True,  # Assume success if we got any response
                "message": "Device delete request sent",
                "response": response_str
            }
            
        except socket.timeout:
            sock.close()
            if verbose:
                print(f"      ⏱️ Timeout waiting for response (JarvisDeviceLoader may not be running)")
            # Even without response, the deletion might have worked
            return {
                "success": False,
                "message": "Timeout: No response from JarvisDeviceLoader on port 11002",
                "response": None
            }
            
    except OSError as e:
        if "10048" in str(e) or "Address already in use" in str(e):
            # Port binding issue - try fire-and-forget approach
            if verbose:
                print(f"      ⚠️ Port 11003 busy, trying fire-and-forget...")
            try:
                sock2 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock2.sendto(message, ('127.0.0.1', 11002))
                sock2.close()
                time.sleep(0.5)  # Give time for deletion
                return {
                    "success": True,
                    "message": "Delete request sent (fire-and-forget)",
                    "response": None
                }
            except Exception as e2:
                return {
                    "success": False,
                    "message": f"Socket error: {e2}",
                    "response": None
                }
        return {
            "success": False,
            "message": f"Socket error: {e}",
            "response": None
        }
    except Exception as e:
        if verbose:
            print(f"      ❌ Error: {e}")
        return {
            "success": False,
            "message": f"Error deleting device: {e}",
            "response": None
        }


def clear_track_devices(track_index: int, reliable: ReliableParameterController, 
                        max_attempts: int = 3, verbose: bool = True,
                        gentle: bool = True,
                        validate_remote_script: bool = True) -> Dict[str, Any]:
    """
    Clear all devices from a track (delete from end to start) with detailed reporting.
    
    Args:
        track_index: Track index (0-based)
        reliable: ReliableParameterController instance
        max_attempts: Maximum number of clearing attempts
        verbose: Print detailed progress
        gentle: Use slower, safer timing to prevent Ableton crashes (recommended)
        validate_remote_script: Check if JarvisDeviceLoader is loaded before deleting
        
    Returns:
        Dict with:
            - success: bool - True if track is now empty
            - devices_deleted: int - Number of devices successfully deleted
            - devices_remaining: int - Number of devices still on track
            - initial_count: int - Number of devices before clearing
            - errors: List[str] - List of error messages
            - attempts: int - Number of attempts made
            - remote_script_loaded: bool - Whether JarvisDeviceLoader was responding
    """
    result = {
        "success": False,
        "devices_deleted": 0,
        "devices_remaining": 0,
        "initial_count": 0,
        "errors": [],
        "attempts": 0,
        "remote_script_loaded": True  # Assume loaded until proven otherwise
    }
    
    # Validate JarvisDeviceLoader is loaded before attempting deletion
    if validate_remote_script:
        validation = validate_jarvis_device_loader(timeout=2.0)
        result["remote_script_loaded"] = validation.get("loaded", False)
        
        if not validation.get("loaded"):
            if verbose:
                print(f"\n   ⚠️  JarvisDeviceLoader Remote Script is NOT loaded!")
                print(f"   📋 {validation.get('message', 'Unknown error')}")
                print(f"\n   🔧 To fix this issue:")
                print(f"      1. Open Ableton Preferences (Ctrl+,)")
                print(f"      2. Go to Link/Tempo/MIDI > Control Surface")
                print(f"      3. Select 'JarvisDeviceLoader' in an empty slot")
                print(f"      4. Restart Ableton Live")
                print(f"\n   ❌ Cannot delete devices without JarvisDeviceLoader")
            
            result["errors"].append("JarvisDeviceLoader Remote Script not loaded in Ableton")
            result["errors"].append(validation.get("message", ""))
            return result
        else:
            if verbose:
                print(f"   ✅ JarvisDeviceLoader Remote Script is responding")
    
    # Timing configuration - gentle mode uses longer delays to prevent crashes
    # INCREASED TIMINGS to prevent crashes on device 1/3 (device index 0)
    if gentle:
        delete_delay = 1.2      # Delay between deletes (seconds) - INCREASED
        verify_delay = 2.0      # Delay after deletion round before verifying - INCREASED
        batch_size = 2          # Delete this many, then pause longer - DECREASED for more safety
        batch_pause = 2.5       # Extra pause after each batch - INCREASED
    else:
        delete_delay = 0.4
        verify_delay = 0.5
        batch_size = 10
        batch_pause = 0.5
    
    # Check initial state
    initial_count = get_device_count(track_index)
    result["initial_count"] = initial_count
    
    if initial_count == 0:
        if verbose:
            print(f"   ✅ Track {track_index} already empty")
        result["success"] = True
        return result
    
    if verbose:
        mode = "gentle" if gentle else "fast"
        print(f"🧹 Clearing {initial_count} devices from track {track_index} ({mode} mode)...")
    
    total_deleted = 0
    
    for attempt in range(max_attempts):
        result["attempts"] = attempt + 1
        
        try:
            num_devices = get_device_count(track_index)
            
            if num_devices == 0:
                result["success"] = True
                result["devices_remaining"] = 0
                if verbose:
                    print(f"   ✅ Track cleared successfully ({total_deleted} devices deleted)")
                return result
            
            if attempt > 0:
                if verbose:
                    print(f"   🔄 Retry attempt {attempt + 1}/{max_attempts}...")
                time.sleep(2.0)  # Extra pause between retry attempts
            
            # Delete from end to start to avoid index shifting
            deleted_this_round = 0
            errors_this_round = []
            
            for i in range(num_devices - 1, -1, -1):
                if verbose:
                    print(f"      🗑️ Deleting device {i+1}/{num_devices}...", end=" ", flush=True)
                
                # SPECIAL HANDLING: Device index 0 often causes crashes - use longer timeout
                timeout = 5.0 if i == 0 else 3.0
                
                try:
                    delete_result = delete_device_via_osc(track_index, i, timeout=timeout, verbose=False)
                    
                    if delete_result.get("success"):
                        deleted_this_round += 1
                        if verbose:
                            print("✅")
                    else:
                        error_msg = delete_result.get("message", "Unknown error")
                        errors_this_round.append(f"Device {i}: {error_msg}")
                        if verbose:
                            print(f"❌ {error_msg}")
                        
                        # Check if this is a crash indicator
                        if "No response" in error_msg or "Connection" in error_msg or "WinError" in error_msg:
                            if verbose:
                                print(f"\n      ⚠️ Possible Ableton crash detected!")
                            # Give extra time for Ableton to recover or crash fully
                            time.sleep(3.0)
                
                except Exception as e:
                    error_msg = f"Exception: {e}"
                    errors_this_round.append(f"Device {i}: {error_msg}")
                    if verbose:
                        print(f"❌ {error_msg}")
                
                # Delay between deletes
                time.sleep(delete_delay)
                
                # Extra pause after batch to let Ableton catch up
                if gentle and (num_devices - i) % batch_size == 0:
                    if verbose and i > 0:
                        print(f"      ⏸️ Pausing to let Ableton stabilize...")
                    time.sleep(batch_pause)
                
                # SPECIAL: Extra long pause before deleting device index 0 (last device)
                if gentle and i == 1:
                    if verbose:
                        print(f"      ⏸️ Extra pause before final device (crash prevention)...")
                    time.sleep(3.0)
            
            total_deleted += deleted_this_round
            result["devices_deleted"] = total_deleted
            result["errors"].extend(errors_this_round)
            
            # Verify count after deletion round
            if verbose:
                print(f"   ⏳ Waiting for Ableton to update...")
            time.sleep(verify_delay)
            remaining = get_device_count(track_index)
            result["devices_remaining"] = remaining
            
            if remaining == 0:
                result["success"] = True
                if verbose:
                    print(f"   ✅ Track cleared successfully ({total_deleted} devices deleted)")
                return result
            elif remaining < num_devices:
                # Making progress
                if verbose:
                    print(f"   ⏳ Progress: {num_devices - remaining} deleted this round, {remaining} remaining...")
                continue
            else:
                # No progress made
                if verbose:
                    print(f"   ⚠️ No progress: {remaining} devices remain")
                
                if attempt == max_attempts - 1:
                    result["errors"].append(f"Failed to delete any devices after {max_attempts} attempts")
                    if verbose:
                        print(f"\n   ❌ FAILED: Could not clear track after {max_attempts} attempts")
                        print(f"   📋 {remaining} devices remaining on track {track_index}")
                        print(f"   💡 Possible causes:")
                        print(f"      - JarvisDeviceLoader Remote Script not running in Ableton")
                        print(f"      - Port 11002 not accessible")
                        print(f"      - Devices may be locked or grouped")
                        print(f"   🔧 Fix: Manually delete devices in Ableton, then re-run test")
                
        except Exception as e:
            error_msg = f"Exception during clearing: {e}"
            result["errors"].append(error_msg)
            if verbose:
                print(f"   ❌ Error: {e}")
    
    return result


def test_jarvis_device_loader_connection(timeout: float = 3.0) -> Dict[str, Any]:
    """
    Test if JarvisDeviceLoader Remote Script is responding on port 11002.
    
    Returns:
        Dict with 'connected', 'message', and 'response_time_ms' keys
    """
    import socket
    import struct
    
    try:
        # Build OSC test message
        address = "/jarvis/test"
        addr_bytes = address.encode('utf-8') + b'\x00'
        addr_padded = addr_bytes + b'\x00' * ((4 - len(addr_bytes) % 4) % 4)
        
        type_tag = ','
        type_bytes = type_tag.encode('utf-8') + b'\x00'
        type_padded = type_bytes + b'\x00' * ((4 - len(type_bytes) % 4) % 4)
        
        message = addr_padded + type_padded
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        
        try:
            sock.bind(('127.0.0.1', 11003))
        except OSError:
            sock.bind(('127.0.0.1', 0))
        
        start_time = time.time()
        sock.sendto(message, ('127.0.0.1', 11002))
        
        try:
            data, addr = sock.recvfrom(65535)
            response_time = (time.time() - start_time) * 1000
            sock.close()
            
            return {
                "connected": True,
                "message": "JarvisDeviceLoader is responding",
                "response_time_ms": round(response_time, 1)
            }
        except socket.timeout:
            sock.close()
            return {
                "connected": False,
                "message": "No response from JarvisDeviceLoader (timeout)",
                "response_time_ms": None
            }
            
    except Exception as e:
        return {
            "connected": False,
            "message": f"Connection test failed: {e}",
            "response_time_ms": None
        }


def validate_jarvis_device_loader(timeout: float = 2.0) -> Dict[str, Any]:
    """
    Validate that JarvisDeviceLoader Remote Script is loaded and responding in Ableton.
    
    This is a critical check before running any tests that use JarvisDeviceLoader
    for device loading/deletion. If the Remote Script is not loaded, all OSC
    operations to port 11002 will fail silently.
    
    Args:
        timeout: How long to wait for response (seconds)
        
    Returns:
        Dict with:
            - 'loaded': bool - True if Remote Script is responding
            - 'message': str - Status message
            - 'instructions': str - Fix instructions if not loaded
    """
    result = test_jarvis_device_loader_connection(timeout=timeout)
    
    if result.get("connected"):
        return {
            "loaded": True,
            "message": "JarvisDeviceLoader Remote Script is active and responding",
            "instructions": None
        }
    else:
        fix_instructions = """
To fix this issue:
1. Open Ableton Live
2. Go to Preferences (Ctrl+,) > Link/Tempo/MIDI
3. Under 'Control Surface', find an empty slot (shows 'None')
4. Click the dropdown and select 'JarvisDeviceLoader'
5. Restart Ableton Live

The Remote Script should be installed at:
Windows: C:\\ProgramData\\Ableton\\Live 11\\Resources\\MIDI Remote Scripts\\JarvisDeviceLoader\\
"""
        return {
            "loaded": False,
            "message": result.get("message", "JarvisDeviceLoader not responding on port 11002"),
            "instructions": fix_instructions
        }


def create_reliable_controller(verbose: bool = True) -> ReliableParameterController:
    """Create a ReliableParameterController instance"""
    return ReliableParameterController(ableton, verbose=verbose)


def run_chain_test(
    chain_name: str,
    chain_devices: List[Dict],
    track_index: int = 0,
    clear_track: bool = True,
    verbose: bool = True
) -> ChainTestResult:
    """
    Run a complete chain building test
    
    Args:
        chain_name: Name of the chain for reporting
        chain_devices: List of device specs with name, type, settings
        track_index: Track to load chain onto (0-based)
        clear_track: Whether to clear existing devices first
        verbose: Enable verbose logging
        
    Returns:
        ChainTestResult with all details
    """
    result = ChainTestResult(chain_name=chain_name, track_index=track_index)
    reliable = create_reliable_controller(verbose=verbose)
    
    print(f"\n🎵 Starting chain test: {chain_name}")
    print(f"   Track: {track_index} ({len(chain_devices)} devices)")
    
    # Clear track if requested
    if clear_track:
        clear_result = clear_track_devices(track_index, reliable, verbose=verbose)
        if not clear_result.get("success"):
            print(f"   ⚠️ Track clearing incomplete - {clear_result.get('devices_remaining', '?')} devices remain")
    
    # Get starting device count
    start_device_count = get_device_count(track_index)
    
    # Load and configure each device
    for i, device_spec in enumerate(chain_devices):
        device_name = device_spec.get("name", "Unknown")
        device_type = device_spec.get("type", "unknown")
        settings = device_spec.get("settings", {})
        
        print(f"\n   [{i+1}/{len(chain_devices)}] Loading {device_name}...")
        
        device_result = DeviceResult(
            device_name=device_name,
            device_type=device_type,
            device_index=None,
            load_success=False,
            load_message="",
            ready=False
        )
        
        # Load the device
        load_result = reliable.load_device_verified(
            track_index=track_index,
            device_name=device_name,
            timeout=5.0
        )
        
        device_result.load_success = load_result.get("success", False)
        device_result.load_message = load_result.get("message", "")
        device_result.device_index = load_result.get("device_index")
        
        if not device_result.load_success:
            print(f"      ❌ Load failed: {device_result.load_message}")
            result.device_results.append(device_result)
            continue
        
        print(f"      ✅ Loaded at index {device_result.device_index}")
        
        # Wait for device to be ready
        device_idx = device_result.device_index
        device_result.ready = reliable.wait_for_device_ready(
            track_index, device_idx, timeout=3.0
        )
        
        if not device_result.ready:
            print(f"      ⚠️ Device not ready for parameter access")
        
        # Configure parameters
        if settings and device_result.ready:
            print(f"      🎛️ Setting {len(settings)} parameters...")
            
            for param_name, value in settings.items():
                param_result = reliable.set_parameter_by_name(
                    track_index, device_idx, param_name, value
                )
                
                pr = ParameterResult(
                    param_name=param_name,
                    param_index=param_result.get("param_index"),
                    requested_value=value,
                    actual_value=param_result.get("actual_value"),
                    success=param_result.get("success", False),
                    verified=param_result.get("verified", False),
                    message=param_result.get("message", ""),
                    attempts=param_result.get("attempts", 1)
                )
                device_result.param_results.append(pr)
                
                status = "✅" if pr.success else "❌"
                if verbose:
                    print(f"         {status} {param_name}: {value} -> {pr.actual_value}")
            
            print(f"      📊 Params: {device_result.params_succeeded}/{len(settings)} "
                  f"({device_result.param_success_rate*100:.0f}%)")
        
        result.device_results.append(device_result)
    
    result.finish()
    return result


def save_test_results(results: List[ChainTestResult], filename: str = "chain_test_results.json"):
    """Save test results to a JSON file"""
    output_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "tests", filename
    )
    
    data = {
        "timestamp": datetime.now().isoformat(),
        "total_tests": len(results),
        "passed": sum(1 for r in results if r.overall_success),
        "failed": sum(1 for r in results if not r.overall_success),
        "results": [r.to_dict() for r in results]
    }
    
    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"📁 Results saved to: {output_path}")


def print_summary(results: List[ChainTestResult]):
    """Print a summary of all test results"""
    print("\n" + "=" * 60)
    print("📊 OVERALL TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for r in results if r.overall_success)
    total = len(results)
    
    print(f"\nTests: {passed}/{total} passed ({passed/total*100:.0f}%)")
    
    total_devices = sum(len(r.device_results) for r in results)
    loaded_devices = sum(r.devices_loaded for r in results)
    print(f"Devices: {loaded_devices}/{total_devices} loaded "
          f"({loaded_devices/total_devices*100:.0f}%)" if total_devices > 0 else "Devices: 0")
    
    total_params = sum(r.params_set + r.params_failed for r in results)
    set_params = sum(r.params_set for r in results)
    print(f"Parameters: {set_params}/{total_params} set "
          f"({set_params/total_params*100:.0f}%)" if total_params > 0 else "Parameters: 0")
    
    total_time = sum(r.execution_time for r in results)
    print(f"Total Time: {total_time:.2f}s")
    
    # Status per test
    print("\nPer-Test Results:")
    for r in results:
        status = "✅ PASS" if r.overall_success else "❌ FAIL"
        print(f"   {status} {r.chain_name}: "
              f"{r.devices_loaded}/{len(r.device_results)} devices, "
              f"{r.param_success_rate*100:.0f}% params, "
              f"{r.execution_time:.1f}s")
    
    print("\n" + "=" * 60 + "\n")
    
    # Overall verdict
    if passed == total:
        print("🎉 ALL TESTS PASSED! Ready for Voice Profiling.")
    else:
        print(f"⚠️  {total - passed} test(s) failed. Review failures above.")

