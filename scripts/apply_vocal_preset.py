#!/usr/bin/env python3
"""
Apply Vocal Preset — Single-preset live test

Reads a vocal chain JSON (default: Travis Scott) and applies it to a track
in Ableton Live using the bridge layer. No LLM, no research pipeline, no
async — just load devices and set parameters.

Usage:
    python scripts/apply_vocal_preset.py --track 0
    python scripts/apply_vocal_preset.py --track 0 --preset data/chains/travis_scott.json
    python scripts/apply_vocal_preset.py --track 0 --style cla_modern_pop
    python scripts/apply_vocal_preset.py --track 0 --dry-run          # validate only
    python scripts/apply_vocal_preset.py --track 0 --device 2         # start from device #2 only (skip loads, just set params)

Requirements:
    - Ableton Live running with AbletonOSC on port 11000
    - JarvisDeviceLoader Remote Script active on port 11002
"""

import argparse
import json
import os
import sys
import time

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from osc_preflight import check_osc_bridge
from livepilot_tools.chain_resolver import resolve_plugin
from livepilot_tools.chain_preferences import load_overrides, merge_with_template


DEFAULT_PRESET = os.path.join(_REPO_ROOT, "data", "chains", "travis_scott.json")
OWNED_PLUGINS_PATH = os.path.join(_REPO_ROOT, "config", "owned_plugins.json")
PLUGIN_CHAINS_PATH = os.path.join(_REPO_ROOT, "config", "vocal_chains.json")
DEVICE_LOAD_TIMEOUT_ENV = "LIVE_PILOT_DEVICE_LOAD_TIMEOUT_SEC"
DEFAULT_DEVICE_LOAD_TIMEOUT_SEC = 30.0
DEVICE_LOAD_POLL_INTERVAL_SEC = 1.0
DUPLICATE_DEVICE_EXIT_CODE = 2
LOAD_FAILURE_EXIT_CODE = 3


class DuplicateDeviceError(RuntimeError):
    """Raised when a load command creates more devices than requested."""

    def __init__(self, plugin_name: str, expected_count: int,
                 actual_count: int, track_index: int):
        self.plugin_name = plugin_name
        self.expected_count = expected_count
        self.actual_count = actual_count
        self.track_index = track_index
        super().__init__(
            f"Detected duplicate device after loading '{plugin_name}'. "
            f"Track has {actual_count} devices, expected {expected_count}."
        )


# ---------------------------------------------------------------------------
# Bridge helpers — call ableton_bridge functions in-process
# ---------------------------------------------------------------------------

def _execute(func_name: str, args: dict) -> dict:
    """Call an ableton_bridge function directly."""
    import ableton_bridge
    dispatch = ableton_bridge._build_dispatch(args)
    if func_name not in dispatch:
        return {"success": False, "message": f"Unknown function: {func_name}"}
    try:
        return dispatch[func_name]()
    except Exception as e:
        return {"success": False, "message": str(e)}


def _get_device_load_timeout_sec() -> float:
    raw = os.environ.get(DEVICE_LOAD_TIMEOUT_ENV)
    if not raw:
        return DEFAULT_DEVICE_LOAD_TIMEOUT_SEC
    try:
        value = float(raw)
    except ValueError:
        print(f"WARNING: Invalid {DEVICE_LOAD_TIMEOUT_ENV}={raw!r}; "
              f"using {DEFAULT_DEVICE_LOAD_TIMEOUT_SEC:.0f}s")
        return DEFAULT_DEVICE_LOAD_TIMEOUT_SEC
    return value if value > 0 else DEFAULT_DEVICE_LOAD_TIMEOUT_SEC


def _get_track_devices(track_index: int) -> list:
    devices_result = _execute("get_track_devices", {"track_index": track_index})
    if not devices_result.get("success"):
        raise RuntimeError(devices_result.get("message", "Could not get track devices"))
    return devices_result.get("devices", [])


def _is_recoverable_load_result(load_result: dict) -> bool:
    if load_result.get("success"):
        return True
    message = str(load_result.get("message", "")).lower()
    return (
        "timeout" in message
        or "no response" in message
        or "not responding" in message
    )


def _load_device_verified(track_index: int, plugin_name: str,
                          timeout_sec: float = None,
                          poll_interval_sec: float = DEVICE_LOAD_POLL_INTERVAL_SEC) -> dict:
    """Load one device and verify exactly one device was added to the track."""
    timeout_sec = timeout_sec if timeout_sec is not None else _get_device_load_timeout_sec()
    before_devices = _get_track_devices(track_index)
    before_count = len(before_devices)
    expected_count = before_count + 1

    load_result = _execute("add_plugin_to_track", {
        "track_index": track_index,
        "plugin_name": plugin_name,
        "position": -1,
        "timeout": timeout_sec,
    })

    if not load_result.get("success") and not _is_recoverable_load_result(load_result):
        return {
            "success": False,
            "plugin_name": plugin_name,
            "before_count": before_count,
            "actual_count": before_count,
            "device_index": None,
            "devices": before_devices,
            "exit_code": LOAD_FAILURE_EXIT_CODE,
            "message": load_result.get("message", "Load failed"),
        }

    deadline = time.time() + timeout_sec
    last_devices = before_devices
    while time.time() <= deadline:
        last_devices = _get_track_devices(track_index)
        actual_count = len(last_devices)

        if actual_count == expected_count:
            return {
                "success": True,
                "plugin_name": plugin_name,
                "before_count": before_count,
                "actual_count": actual_count,
                "device_index": actual_count - 1,
                "devices": last_devices,
                "load_result": load_result,
                "message": "Device loaded and verified",
            }

        if actual_count > expected_count:
            raise DuplicateDeviceError(
                plugin_name=plugin_name,
                expected_count=expected_count,
                actual_count=actual_count,
                track_index=track_index,
            )

        time.sleep(poll_interval_sec)

    return {
        "success": False,
        "plugin_name": plugin_name,
        "before_count": before_count,
        "actual_count": len(last_devices),
        "device_index": None,
        "devices": last_devices,
        "exit_code": LOAD_FAILURE_EXIT_CODE,
        "message": (
            f"Timed out waiting for '{plugin_name}' to appear on track "
            f"{track_index}; expected {expected_count} devices, found {len(last_devices)}"
        ),
    }


def _load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_waves_style_preset(style: str) -> dict:
    chain_data = _load_json(PLUGIN_CHAINS_PATH)
    styles = chain_data.get("waves_vocal_chains", {})
    if style not in styles:
        available = ", ".join(sorted(styles))
        raise ValueError(f"Unknown Waves vocal chain style '{style}'. Available: {available}")

    style_data = styles[style]
    owned = _load_json(OWNED_PLUGINS_PATH)

    resolved_chain = []
    for step in style_data.get("chain", []):
        plugin_name, host = resolve_plugin(step.get("plugin_suggestions", []), owned)
        resolved_step = dict(step)
        resolved_step["plugin_name"] = plugin_name
        resolved_step["host"] = host
        resolved_chain.append(resolved_step)

    chain = merge_with_template(resolved_chain, load_overrides(style))
    return {
        "artist": style,
        "track_type": style_data.get("track_type", "vocal"),
        "description": style_data.get("description", ""),
        "style": style,
        "chain": [
            {
                "plugin_name": step["plugin_name"],
                "host": step.get("host"),
                "purpose": step.get("purpose", ""),
                "parameters": step.get("settings", {}),
            }
            for step in chain
        ],
    }


def _filter_parameters_for_device(track_index: int, device_index: int,
                                  parameters: dict) -> dict:
    """Skip parameters Ableton does not report for the loaded device."""
    if not parameters:
        return parameters

    params_result = _execute("get_device_parameters", {
        "track_index": track_index,
        "device_index": device_index,
    })
    if not params_result.get("success"):
        print(f"    WARNING: Could not inspect device parameters: "
              f"{params_result.get('message', 'unknown')}")
        return parameters

    available = set(params_result.get("names", []))
    if not available:
        return parameters

    filtered = {}
    for name, value in parameters.items():
        if name in available:
            filtered[name] = value
        else:
            print(f"      WARNING: Parameter '{name}' not found on device {device_index}; skipping")

    return filtered


# ---------------------------------------------------------------------------
# Core: load one device and set its parameters
# ---------------------------------------------------------------------------

def load_and_configure_device(track_index: int, plugin_name: str,
                               parameters: dict, device_index: int,
                               dry_run: bool = False) -> dict:
    """
    Load a single device onto a track and configure its parameters.

    Args:
        track_index: 0-based track index
        plugin_name: Ableton device name (e.g. "EQ Eight")
        parameters: Dict of param_name -> value
        device_index: Expected device index after loading
        dry_run: If True, print plan without executing

    Returns:
        Summary dict with load/param results
    """
    result = {
        "plugin_name": plugin_name,
        "device_index": device_index,
        "loaded": False,
        "params_set": 0,
        "params_failed": 0,
        "param_details": [],
        "errors": [],
    }

    if dry_run:
        print(f"  [DRY-RUN] Would load '{plugin_name}' at device index {device_index}")
        for name, val in parameters.items():
            print(f"    {name} = {val}")
        result["loaded"] = True
        result["params_set"] = len(parameters)
        return result

    # --- Load the device ---
    print(f"  Loading '{plugin_name}'...", end=" ", flush=True)
    load_result = _execute("add_plugin_to_track", {
        "track_index": track_index,
        "plugin_name": plugin_name,
        "position": -1,
    })

    if not load_result.get("success"):
        msg = load_result.get("message", "unknown error")
        print(f"FAILED ({msg})")
        result["errors"].append(f"Load failed: {msg}")
        return result

    print("OK")
    result["loaded"] = True

    # Give Ableton time to initialize the device
    time.sleep(1.0)

    # --- Verify the device appeared ---
    devices_result = _execute("get_track_devices", {"track_index": track_index})
    if devices_result.get("success"):
        devices = devices_result.get("devices", [])
        print(f"    Device chain now: {devices}")
        if device_index < len(devices):
            actual_name = devices[device_index]
            if plugin_name.lower() not in actual_name.lower():
                print(f"    WARNING: Expected '{plugin_name}' at index {device_index}, "
                      f"got '{actual_name}'")

    # --- Set parameters ---
    if not parameters:
        return result

    parameters = _filter_parameters_for_device(track_index, device_index, parameters)
    if not parameters:
        return result

    print(f"    Setting {len(parameters)} parameters...")
    param_result = _execute("set_device_parameters_by_name", {
        "track_index": track_index,
        "device_index": device_index,
        "params": parameters,
    })

    if param_result.get("success"):
        total = param_result.get("total", 0)
        succeeded = param_result.get("succeeded", 0)
        failed_count = param_result.get("failed", 0)
        not_found = param_result.get("not_found", 0)
        result["params_set"] = succeeded
        result["params_failed"] = failed_count + not_found

        for detail in param_result.get("details", []):
            status = "OK" if detail.get("success") else "FAIL"
            name = detail.get("param_name", "?")
            req = detail.get("requested_value", "?")
            actual = detail.get("actual_value", "?")
            verified = detail.get("verified", False)
            vstr = "verified" if verified else "unverified"
            print(f"      [{status}] {name}: {req} -> {actual} ({vstr})")
            result["param_details"].append(detail)

        if not_found > 0:
            print(f"    {not_found} parameter(s) not found on device")
        if failed_count > 0:
            print(f"    {failed_count} parameter(s) failed to set")
    else:
        msg = param_result.get("message", "unknown")
        print(f"    Parameter setting failed: {msg}")
        result["errors"].append(f"Params failed: {msg}")
        
        # Even on failure, we might have details for partial successes or specific failures
        if "details" in param_result and param_result["details"]:
            for detail in param_result["details"]:
                status = "OK" if detail.get("success") else "FAIL"
                name = detail.get("param_name", "?")
                req = detail.get("requested_value", "?")
                actual = detail.get("actual_value", "?")
                verified = detail.get("verified", False)
                vstr = "verified" if verified else "unverified"
                print(f"      [{status}] {name}: {req} -> {actual} ({vstr})")
                result["param_details"].append(detail)
        
        result["params_failed"] = len(parameters)

    return result


def set_params_only(track_index: int, plugin_name: str,
                    parameters: dict, device_index: int) -> dict:
    """Set parameters on an already-loaded device (skip loading)."""
    result = {
        "plugin_name": plugin_name,
        "device_index": device_index,
        "loaded": True,
        "params_set": 0,
        "params_failed": 0,
        "param_details": [],
        "errors": [],
    }

    parameters = _filter_parameters_for_device(track_index, device_index, parameters)
    print(f"  Setting params on existing device {device_index} ('{plugin_name}')...")
    if not parameters:
        return result

    param_result = _execute("set_device_parameters_by_name", {
        "track_index": track_index,
        "device_index": device_index,
        "params": parameters,
    })

    if param_result.get("success"):
        succeeded = param_result.get("succeeded", 0)
        failed_count = param_result.get("failed", 0)
        not_found = param_result.get("not_found", 0)
        result["params_set"] = succeeded
        result["params_failed"] = failed_count + not_found

        for detail in param_result.get("details", []):
            status = "OK" if detail.get("success") else "FAIL"
            name = detail.get("param_name", "?")
            req = detail.get("requested_value", "?")
            actual = detail.get("actual_value", "?")
            verified = detail.get("verified", False)
            vstr = "verified" if verified else "unverified"
            print(f"      [{status}] {name}: {req} -> {actual} ({vstr})")
            result["param_details"].append(detail)
    else:
        msg = param_result.get("message", "unknown")
        print(f"    Failed: {msg}")
        result["errors"].append(msg)
        result["params_failed"] = len(parameters)

    return result


def _empty_device_result(plugin_name: str, device_index: int = None) -> dict:
    return {
        "plugin_name": plugin_name,
        "device_index": device_index,
        "loaded": False,
        "params_set": 0,
        "params_failed": 0,
        "param_details": [],
        "errors": [],
    }


def _print_duplicate_error(error: DuplicateDeviceError):
    print(f"ERROR: Detected duplicate device after loading '{error.plugin_name}'.")
    print(f"Track has {error.actual_count} devices, expected {error.expected_count}.")
    print("Chain is in a corrupt state and was not configured.")
    print(f"Recovery: select all devices on track {error.track_index} in Ableton and delete, then re-run.")


def apply_chain(track_index: int, chain: list, dry_run: bool = False,
                start_device: int = None) -> dict:
    """Apply a chain and return a summary dict without exiting."""
    results = []
    exit_code = 0
    aborted = False

    if dry_run:
        for i, device in enumerate(chain):
            plugin_name = device.get("plugin_name", "")
            parameters = device.get("parameters", {})
            dev_idx = (start_device + i) if start_device is not None else i
            r = load_and_configure_device(
                track_index, plugin_name, parameters, dev_idx, dry_run=True)
            results.append(r)
            print()
        return {
            "results": results,
            "exit_code": 0,
            "aborted": False,
            "final_devices": [],
        }

    if start_device is not None:
        for i, device in enumerate(chain):
            plugin_name = device.get("plugin_name", "")
            parameters = device.get("parameters", {})
            dev_idx = start_device + i
            results.append(set_params_only(track_index, plugin_name, parameters, dev_idx))
            print()
        return {
            "results": results,
            "exit_code": 0,
            "aborted": False,
            "final_devices": [],
        }

    try:
        initial_devices = _get_track_devices(track_index)
    except RuntimeError as e:
        print(f"[FAIL] Could not snapshot track devices: {e}")
        return {
            "results": results,
            "exit_code": LOAD_FAILURE_EXIT_CODE,
            "aborted": True,
            "final_devices": [],
        }

    print(f"Existing devices on track: {len(initial_devices)}\n")

    for device in chain:
        plugin_name = device.get("plugin_name", "")
        result = _empty_device_result(plugin_name)
        print(f"  Loading '{plugin_name}'...", end=" ", flush=True)
        try:
            load_result = _load_device_verified(track_index, plugin_name)
        except DuplicateDeviceError as e:
            print("DUPLICATE")
            _print_duplicate_error(e)
            result["errors"].append(str(e))
            results.append(result)
            aborted = True
            exit_code = DUPLICATE_DEVICE_EXIT_CODE
            break
        except RuntimeError as e:
            print(f"FAILED ({e})")
            result["errors"].append(str(e))
            results.append(result)
            aborted = True
            exit_code = LOAD_FAILURE_EXIT_CODE
            break

        if not load_result.get("success"):
            msg = load_result.get("message", "unknown error")
            print(f"FAILED ({msg})")
            result["errors"].append(f"Load failed: {msg}")
            results.append(result)
            aborted = True
            exit_code = LOAD_FAILURE_EXIT_CODE
            break

        print("OK")
        result["loaded"] = True
        result["device_index"] = load_result.get("device_index")
        results.append(result)
        print(f"    Device chain now: {load_result.get('devices', [])}")
        print()

    if aborted:
        return {
            "results": results,
            "exit_code": exit_code,
            "aborted": True,
            "final_devices": [],
        }

    final_devices = _get_track_devices(track_index)
    expected_total = len(initial_devices) + len(chain)
    if len(final_devices) != expected_total:
        print(f"[FAIL] Chain verification failed: track has {len(final_devices)} devices, "
              f"expected {expected_total}. Parameters were not set.")
        return {
            "results": results,
            "exit_code": LOAD_FAILURE_EXIT_CODE,
            "aborted": True,
            "final_devices": final_devices,
        }

    for i, device in enumerate(chain):
        plugin_name = device.get("plugin_name", "")
        expected_index = len(initial_devices) + i
        actual_name = final_devices[expected_index]
        if plugin_name.lower() not in actual_name.lower():
            print(f"[FAIL] Chain verification failed: expected '{plugin_name}' at "
                  f"index {expected_index}, got '{actual_name}'. Parameters were not set.")
            return {
                "results": results,
                "exit_code": LOAD_FAILURE_EXIT_CODE,
                "aborted": True,
                "final_devices": final_devices,
            }

    for i, device in enumerate(chain):
        parameters = device.get("parameters", {})
        if not parameters:
            continue

        plugin_name = device.get("plugin_name", "")
        device_index = len(initial_devices) + i
        param_result = set_params_only(track_index, plugin_name, parameters, device_index)
        results[i]["params_set"] = param_result["params_set"]
        results[i]["params_failed"] = param_result["params_failed"]
        results[i]["param_details"] = param_result["param_details"]
        results[i]["errors"].extend(param_result["errors"])
        print()

    return {
        "results": results,
        "exit_code": 0,
        "aborted": False,
        "final_devices": final_devices,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Apply a vocal preset to a track")
    parser.add_argument("--track", type=int, required=True, help="Track index (0-based)")
    parser.add_argument("--preset", type=str, default=None,
                        help="Path to preset JSON file")
    parser.add_argument("--style", type=str, default=None,
                        help="Waves vocal chain style from config/vocal_chains.json")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print plan without executing")
    parser.add_argument("--device", type=int, default=None,
                        help="Start device index (skip loading, just set params from this index)")
    parser.add_argument("--skip-preflight", action="store_true",
                        help="Skip OSC preflight check")
    args = parser.parse_args()

    # Load preset
    if args.style and args.preset:
        parser.error("--style and --preset are mutually exclusive")

    if args.style:
        print(f"Loading Waves vocal chain style: {args.style}")
        try:
            preset = _load_waves_style_preset(args.style)
        except ValueError as e:
            print(f"[FAIL] {e}")
            sys.exit(1)
        preset_label = f"style:{args.style}"
    else:
        preset_path = args.preset or DEFAULT_PRESET
        print(f"Loading preset: {preset_path}")
        with open(preset_path, encoding="utf-8") as f:
            preset = json.load(f)
        preset_label = os.path.basename(preset_path)

    artist = preset.get("artist", "Unknown")
    track_type = preset.get("track_type", "vocal")
    chain = preset.get("chain", [])
    print(f"Preset: {artist} {track_type} chain ({len(chain)} devices)")
    print()

    # Preflight
    if not args.dry_run and not args.skip_preflight:
        print("[PREFLIGHT] Checking OSC bridge...")
        preflight = check_osc_bridge(_execute, attempts=3, delay_s=0.5)
        if not preflight["ok"]:
            print(f"[FAIL] OSC bridge unreachable: {preflight['message']}")
            print("Make sure Ableton is running with AbletonOSC active.")
            sys.exit(1)
        print(f"[OK] OSC bridge responding\n")

        # Verify track exists
        track_list = _execute("get_track_list", {})
        if track_list.get("success"):
            tracks = track_list.get("tracks", [])
            if args.track >= len(tracks):
                print(f"[FAIL] Track {args.track} does not exist. "
                      f"Available: {len(tracks)} tracks (0-{len(tracks)-1})")
                sys.exit(1)
            track_name = tracks[args.track].get("name", f"Track {args.track + 1}")
            print(f"Target: Track {args.track + 1} ({track_name})\n")

    # Show plan
    print("=" * 60)
    print(f"VOCAL CHAIN: {artist}")
    print("=" * 60)
    for i, device in enumerate(chain):
        name = device.get("plugin_name", "?")
        host = device.get("host")
        purpose = device.get("purpose", "")
        params = device.get("parameters", {})
        host_label = f" [{host}]" if host else ""
        print(f"  {i+1}. {name}{host_label} ({len(params)} params) — {purpose}")
    print()

    if args.dry_run:
        print("[DRY-RUN MODE] No changes will be made.\n")

    # Apply chain
    apply_result = apply_chain(
        track_index=args.track,
        chain=chain,
        dry_run=args.dry_run,
        start_device=args.device,
    )
    results = apply_result["results"]
    total_loaded = sum(1 for r in results if r["loaded"])
    total_load_failed = len(chain) - total_loaded
    total_params_set = sum(r["params_set"] for r in results)
    total_params_failed = sum(r["params_failed"] for r in results)

    # Summary
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"  Devices loaded:     {total_loaded}/{len(chain)}")
    if total_load_failed:
        print(f"  Devices FAILED:     {total_load_failed}")
    print(f"  Parameters set:     {total_params_set}")
    if total_params_failed:
        print(f"  Parameters FAILED:  {total_params_failed}")

    # Per-device summary
    print()
    for r in results:
        status = "OK" if r["loaded"] and r["params_failed"] == 0 else "PARTIAL" if r["loaded"] else "FAIL"
        print(f"  [{status}] {r['plugin_name']}: "
              f"{r['params_set']}/{r['params_set']+r['params_failed']} params")
        for err in r["errors"]:
            print(f"         Error: {err}")

    # Write report
    log_dir = os.path.join(_REPO_ROOT, "logs")
    os.makedirs(log_dir, exist_ok=True)
    report_path = os.path.join(log_dir, "vocal_preset_report.json")
    report = {
        "preset": preset_label,
        "artist": artist,
        "track_index": args.track,
        "dry_run": args.dry_run,
        "devices_loaded": total_loaded,
        "devices_failed": total_load_failed,
        "params_set": total_params_set,
        "params_failed": total_params_failed,
        "results": results,
    }
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\nReport: {report_path}")

    all_ok = total_load_failed == 0 and total_params_failed == 0
    if apply_result.get("exit_code"):
        sys.exit(apply_result["exit_code"])
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
