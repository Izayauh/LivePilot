# Adaptive Layer Notes (2026-02-15)

## What shipped

### 1) Bridge now supports name-based parameter writes
Added new `ableton_bridge.py` commands:
- `set_device_parameter_by_name`
- `set_device_parameters_by_name`

Both are backward-compatible additions (no existing signatures changed).

### 2) New adaptive semantic layer
Added `adaptive_layer.py`:
- Friendly alias normalization (`air`, `presence`, `mud`, `low_cut`, etc.)
- Device alias registries for:
  - `EQ Eight`
  - `Compressor`
- Deterministic helper for batch setting by semantic names:
  - `set_device_params_adaptive(...)`
- Profile step builder for:
  - `airy_melodic`
  - `punchy_rap`

### 3) Desktop local deterministic preset path upgraded
Updated `jarvis_desktop_openclaw.py`:
- `_apply_vocal_profile` now tries adaptive name-based flow first.
- Falls back to legacy `param_index` flow if adaptive path is unavailable/fails.
- Uses `get_track_devices` to build runtime device map.
- Executes via new bridge method `set_device_parameters_by_name`.

### 4) Deterministic OSC preflight guard
Added `osc_preflight.py` and integrated in `scripts/test_librarian_full_chain.py`:
- Checks:
  - OSC bridge reachability
  - JarvisDeviceLoader reachability
  - target track accessibility
- Returns structured failure types:
  - `osc_unreachable_preflight`
  - `jarvis_loader_unreachable_preflight`
  - `track_unreachable`

## Validation run
From WSL/Linux python:

```bash
python3 -m unittest -q tests.test_adaptive_layer tests.test_osc_preflight tests.test_ableton_bridge
```

Result:
- **58 tests passed**

## Practical usage

### Name-based single parameter
```bash
python3 ableton_bridge.py set_device_parameter_by_name '{"track_index":0,"device_index":0,"param_name":"air","value":1.5}'
```

### Name-based batch
```bash
python3 ableton_bridge.py set_device_parameters_by_name '{"track_index":0,"device_index":0,"params":{"low_cut":100,"mud":-2.5,"presence":1.2}}'
```

## Remaining risks / next steps
1. Expand alias coverage to more stock + third-party devices.
2. Add per-device auto-calibration profiles (plugin-version aware).
3. Add execution telemetry (success rate per semantic alias).
4. Add one-shot end-to-end smoke command that runs preflight + one adaptive write + verify.
