#!/usr/bin/env python3
"""
Apply Vocal Preset — Single-preset live test

Reads a vocal chain JSON (default: Travis Scott) and applies it to a track
in Ableton Live using the bridge layer. No LLM, no research pipeline, no
async — just load devices and set parameters.

Usage:
    python scripts/apply_vocal_preset.py --track 0
    python scripts/apply_vocal_preset.py --track 0 --preset knowledge/chains/travis_scott.json
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
from plugins.chain_resolver import resolve_plugin
from preferences.chain_preferences import load_overrides, merge_with_template


DEFAULT_PRESET = os.path.join(_REPO_ROOT, "knowledge", "chains", "travis_scott.json")
OWNED_PLUGINS_PATH = os.path.join(_REPO_ROOT, "config", "owned_plugins.json")
PLUGIN_CHAINS_PATH = os.path.join(_REPO_ROOT, "knowledge", "plugin_chains.json")


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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Apply a vocal preset to a track")
    parser.add_argument("--track", type=int, required=True, help="Track index (0-based)")
    parser.add_argument("--preset", type=str, default=None,
                        help="Path to preset JSON file")
    parser.add_argument("--style", type=str, default=None,
                        help="Waves vocal chain style from knowledge/plugin_chains.json")
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
    results = []
    total_params_set = 0
    total_params_failed = 0
    total_loaded = 0
    total_load_failed = 0

    # Get current device count to calculate device indices
    if not args.dry_run and args.device is None:
        dev_count_result = _execute("get_num_devices", {"track_index": args.track})
        existing_devices = dev_count_result.get("count", 0) if dev_count_result.get("success") else 0
        print(f"Existing devices on track: {existing_devices}\n")
    else:
        existing_devices = 0

    for i, device in enumerate(chain):
        plugin_name = device.get("plugin_name", "")
        parameters = device.get("parameters", {})

        # Calculate the device index: existing devices + position in our chain
        if args.device is not None:
            # User specified starting device index — set params only
            dev_idx = args.device + i
            r = set_params_only(args.track, plugin_name, parameters, dev_idx)
        else:
            dev_idx = existing_devices + i
            r = load_and_configure_device(
                args.track, plugin_name, parameters, dev_idx,
                dry_run=args.dry_run)

        results.append(r)
        if r["loaded"]:
            total_loaded += 1
        else:
            total_load_failed += 1
        total_params_set += r["params_set"]
        total_params_failed += r["params_failed"]
        print()

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
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
