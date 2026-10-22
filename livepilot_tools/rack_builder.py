"""Turn a track's device chain in a saved .als into an Instrument / Audio Effect Rack .adg with macros.

The bridge cannot group devices, map macros or save presets inside Live, so this works on the files:
it reads the gzipped .als, lifts the named track's devices, wraps them in a minimal one-chain rack
(``rack_templates/``, stripped from Live 11.3 Core Library racks), maps macros, and gzips the .adg.

Macro mapping as Live 11.3 writes it: on the target parameter a <KeyMidi> goes right after <LomId>
with Channel 16 and NoteOrController = macro index, and MidiControllerRange Min/Max is the mapped
range. A plugin's on/off is mapped on its preset with PowerMacroControlIndex + PowerMacroMappingRange.
"""

from __future__ import annotations

import copy
import gzip
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from urllib.parse import quote

TEMPLATES = Path(__file__).resolve().parent / "rack_templates"
POWER_NAMES = {"on", "deviceon", "power", "onoff"}
# EQ Eight's display names ("1 Frequency A") to its XML (Bands.0/ParameterA/Freq).
_EQ8_NAME = re.compile(r"^(\d)\s*(frequency|freq|gain|resonance|q|filter on|filter type)\s*([ab])$", re.I)
_EQ8_LEAF = {"frequency": "Freq", "freq": "Freq", "gain": "Gain", "resonance": "Q", "q": "Q",
             "filter on": "IsOn", "filter type": "Mode"}


class RackError(ValueError):
    """The set, track, chain or macro spec cannot become a rack; the message says why."""


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _read_xml(path: Path) -> ET.Element:
    raw = path.read_bytes()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return ET.fromstring(raw)


def _dialcore():
    import importlib.util

    path = Path(__file__).resolve().parent.parent / "ableton_remote_script" / "LivePilot" / "lp_dialcore.py"
    spec = importlib.util.spec_from_file_location("lp_dialcore", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def find_track(root: ET.Element, name: str) -> ET.Element:
    """The track `name` resolves to under the same rules as dial: a name, or the number Live shows ("4", "4-Audio")."""
    core = _dialcore()
    live_set = root.find("LiveSet")
    elements = list(live_set.find("Tracks"))
    regular = [t for t in elements if t.tag != "ReturnTrack"]
    returns = [t for t in elements if t.tag == "ReturnTrack"]
    master = live_set.find("MasterTrack")

    def label(t):
        return t.find("Name/EffectiveName").get("Value")

    by_key = {i: t for i, t in enumerate(regular)}
    by_key.update({-(i + 1): t for i, t in enumerate(returns)})
    if master is not None:
        by_key[core.MASTER] = master
    tracks = [(i, label(t)) for i, t in enumerate(regular)]
    rets = [(-(i + 1), label(t)) for i, t in enumerate(returns)]
    try:
        key, found = core.resolve_track(name, tracks, rets)
    except core.DialError as e:
        raise RackError(str(e)) from None
    if key == core.MASTER and master is None:
        raise RackError("This set has no master track.")
    same = [n for _, n in tracks + rets if n == found]
    if len(same) > 1:
        raise RackError(f"{len(same)} tracks are named {found!r}; rename one so the name is unique")
    return by_key[key]


def _device_label(device: ET.Element) -> str:
    if device.tag != "PluginDevice":
        return device.tag
    info = device.find("PluginDesc")[0]
    label = info.find("PlugName") if info.find("PlugName") is not None else info.find("Name")
    return label.get("Value") if label is not None else "PluginDevice"


def _strip_mappings(element: ET.Element) -> None:
    """Drop MIDI/macro mappings the device carried on the track; only the new macros should map."""
    for parent in element.iter():
        for km in parent.findall("KeyMidi"):
            parent.remove(km)
        power = parent.find("PowerMacroControlIndex")
        if power is not None:
            power.set("Value", "-1")


def _plugin_preset(device: ET.Element, label: str) -> ET.Element:
    info = device.find("PluginDesc")[0]
    placeholder = info.find("IsPlaceholderDevice")
    if placeholder is not None and placeholder.get("Value") == "true":
        raise RackError(f"{label} is a placeholder in this set (plugin missing); the rack would load it empty")
    preset = copy.deepcopy(info.find("Preset")[0])
    _strip_mappings(preset)
    return preset


def _native_preset(device: ET.Element) -> ET.Element:
    preset = ET.Element("AbletonDevicePreset", Id="0")
    ET.SubElement(preset, "OverwriteProtectionNumber", Value="2819")
    inner = copy.deepcopy(device)
    inner.set("Id", "0")
    _strip_mappings(inner)
    ET.SubElement(preset, "Device").append(inner)
    ref = ET.SubElement(preset, "PresetRef")
    last = device.find("LastPresetRef/Value")
    if last is not None and len(last):
        ref.append(copy.deepcopy(last[0]))  # where Live loaded the device from, as Live writes it
    else:
        default = ET.SubElement(ref, "AbletonDefaultPresetRef", Id="0")
        file_ref = ET.SubElement(default, "FileRef")
        for tag, val in [("RelativePathType", "0"), ("RelativePath", ""), ("Path", ""), ("Type", "1"),
                         ("LivePackName", ""), ("LivePackId", ""), ("OriginalFileSize", "0"),
                         ("OriginalCrc", "0")]:
            ET.SubElement(file_ref, tag, Value=val)
        ET.SubElement(default, "DeviceId", Name=device.tag)
    return preset


def _mappable(device: ET.Element) -> dict[str, ET.Element]:
    """Every macro-mappable parameter of a native device, keyed by its path inside the device."""
    found: dict[str, ET.Element] = {}

    def walk(element: ET.Element, prefix: str) -> None:
        for child in element:
            path = f"{prefix}{child.tag}"
            if child.find("MidiControllerRange") is not None and child.find("Manual") is not None:
                found[path] = child
            else:
                walk(child, path + "/")
    walk(device, "")
    return found


def resolve_param(device: ET.Element, param: str) -> tuple[str, ET.Element]:
    """Find a native parameter by Live's name ('Threshold', 'Dry/Wet', '1 Frequency A') or XML path."""
    params = _mappable(device)
    if param in params:
        return param, params[param]
    eq = _EQ8_NAME.match(param.strip()) if device.tag == "Eq8" else None
    if eq:
        path = f"Bands.{int(eq.group(1)) - 1}/Parameter{eq.group(3).upper()}/{_EQ8_LEAF[eq.group(2).lower()]}"
        if path in params:
            return path, params[path]
    wanted = _norm(param)
    leaf = lambda p: _norm(p.rsplit("/", 1)[-1])  # noqa: E731
    for test in (lambda p: leaf(p) == wanted, lambda p: _norm(p) == wanted, lambda p: leaf(p).endswith(wanted)):
        hits = [p for p in params if test(p)]
        top = [p for p in hits if p.count("/") == min(h.count("/") for h in hits)]
        if len(top) == 1:  # 'Dry/Wet' is the device's, not SideChain/DryWet
            return top[0], params[top[0]]
        if len(hits) > 1:
            raise RackError(f"{param!r} on {device.tag} is ambiguous: {hits[:12]}; pass one of these paths")
    raise RackError(f"{device.tag} has no mappable parameter {param!r}. Paths: {sorted(params)[:40]}")


def _map_param(param: ET.Element, macro_index: int, lo: float, hi: float) -> None:
    keymidi = ET.Element("KeyMidi")
    for tag, val in [("PersistentKeyString", ""), ("IsNote", "false"), ("Channel", "16"),
                     ("NoteOrController", str(macro_index)), ("LowerRangeNote", "-1"),
                     ("UpperRangeNote", "-1"), ("ControllerMapMode", "0")]:
        ET.SubElement(keymidi, tag, Value=val)
    lom = param.find("LomId")
    param.insert(list(param).index(lom) + 1 if lom is not None else 0, keymidi)
    rng = param.find("MidiControllerRange")
    rng.find("Min").set("Value", repr(float(lo)))
    rng.find("Max").set("Value", repr(float(hi)))


def _default_value(param: ET.Element, lo: float, hi: float) -> float:
    """Macro position (0-127) that keeps the parameter where it sits now, linear in its raw value."""
    try:
        current = float(param.find("Manual").get("Value"))
    except (TypeError, ValueError):
        return 0.0
    if hi == lo:
        return 0.0
    return round(min(max((current - lo) / (hi - lo), 0.0), 1.0) * 127, 2)


def browser_uri(path: Path) -> str | None:
    """load_browser_item uri for a preset inside the User Library, else None."""
    parts = path.resolve().parts
    lowered = [p.lower() for p in parts]
    if "user library" not in lowered:
        return None
    rel = parts[lowered.index("user library") + 1:]
    return "query:UserLibrary#" + ":".join(quote(p) for p in rel)


def build_rack(als: str | Path, track: str, out: str | Path, macros: list[dict[str, Any]] | None = None,
               name: str | None = None, chain_name: str | None = None, overwrite: bool = False) -> dict[str, Any]:
    """Wrap `track`'s whole device chain from a saved .als into a rack preset at `out` (.adg).

    macros: up to 16 of {name, device (0-based slot in the track chain), param, min, max, value?}.
    param is Live's parameter name or the XML path; 'Device On' on a plugin maps its power.
    min/max are raw parameter values (Hz, dB, 0-1); value is the macro's start position 0-127
    (default: where the parameter sits now, linear, so pass it for log-scaled knobs like frequency).
    A MIDI track becomes an Instrument Rack, any other track an Audio Effect Rack.
    """
    als, out = Path(als), Path(out)
    macros = list(macros or [])
    if out.suffix.lower() != ".adg":
        raise RackError(f"out must be an .adg file, got {out.name}")
    if out.exists() and not overwrite:
        raise RackError(f"{out} exists; pass overwrite=True to replace it")
    if len(macros) > 16:
        raise RackError(f"A rack has 16 macros; got {len(macros)}")

    source = find_track(_read_xml(als), track)
    devices = list(source.find("DeviceChain/DeviceChain/Devices"))
    if not devices:
        raise RackError(f"Track {track!r} has no devices in {als.name}")
    labels = [_device_label(d) for d in devices]
    nested = [label for label in labels if label.endswith("GroupDevice")]
    if nested:
        raise RackError(f"Track {track!r} already holds a rack ({nested}); flatten it first")
    instrument = source.tag == "MidiTrack"
    presets = [_plugin_preset(d, label) if d.tag == "PluginDevice" else _native_preset(d)
               for d, label in zip(devices, labels)]

    readback = []
    for i, spec in enumerate(macros):
        slot = int(spec["device"])
        if not 0 <= slot < len(devices):
            raise RackError(f"Macro {spec['name']!r}: device {slot} is outside the chain {labels}")
        lo, hi = float(spec["min"]), float(spec["max"])
        preset = presets[slot]
        if devices[slot].tag == "PluginDevice":
            if _norm(spec["param"]) not in POWER_NAMES:
                raise RackError(f"Macro {spec['name']!r}: only a plugin's power ('Device On') can be "
                                f"mapped, not {spec['param']!r} on {labels[slot]}")
            preset.find("PowerMacroControlIndex").set("Value", str(i))
            preset.find("PowerMacroMappingRange/Min").set("Value", str(int(lo)))
            preset.find("PowerMacroMappingRange/Max").set("Value", str(int(hi)))
            path, value = "PowerMacroControlIndex", spec.get("value", 127.0)
        else:
            path, param = resolve_param(preset.find("Device")[0], spec["param"])
            _map_param(param, i, lo, hi)
            value = spec.get("value", _default_value(param, lo, hi))
        readback.append({"macro": i + 1, "name": spec["name"], "device": f"{slot}:{labels[slot]}",
                         "param": path, "min": lo, "max": hi, "value": float(value)})

    root = ET.parse(TEMPLATES / ("instrument_rack.xml" if instrument else "audio_effect_rack.xml")).getroot()
    group = root.find("GroupDevicePreset")
    rack = group.find("Device")[0]
    branch = group.find("BranchPresets")[0]
    device_presets = branch.find("DevicePresets")
    for i, preset in enumerate(presets):
        preset.set("Id", str(i))
        device_presets.append(preset)
    rack_name = name or out.stem
    rack.find("UserName").set("Value", rack_name)
    branch.find("Name").set("Value", chain_name or source.find("Name/EffectiveName").get("Value"))
    rack.find("NumVisibleMacroControls").set("Value", "8" if len(macros) <= 8 else "16")
    for row in readback:
        i = row["macro"] - 1
        rack.find(f"MacroDisplayNames.{i}").set("Value", row["name"])
        rack.find(f"MacroControls.{i}/Manual").set("Value", repr(row["value"]))
        rack.find(f"MacroDefaults.{i}").set("Value", repr(row["value"]))

    xml =b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode").encode("utf-8")
    out.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(out, "wb") as f:
        f.write(xml)
    return {"success": True, "path": str(out), "rack": rack_name,
            "kind": "Instrument Rack" if instrument else "Audio Effect Rack",
            "devices": [f"{i}:{label}" for i, label in enumerate(labels)], "macros": readback,
            "browser_uri": browser_uri(out),
            "note": "Live lists a new .adg after a browser rescan or a Live restart; then load it with "
                    "live_command('load_browser_item', {'track_index': n, 'uri': browser_uri})."}


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(description=build_rack.__doc__.splitlines()[0])
    parser.add_argument("als")
    parser.add_argument("track")
    parser.add_argument("out")
    parser.add_argument("--macros", default="[]", help="JSON list of {name, device, param, min, max, value?}")
    parser.add_argument("--name")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = build_rack(args.als, args.track, args.out, json.loads(args.macros),
                            name=args.name, overwrite=args.overwrite)
    except RackError as exc:
        result = {"success": False, "error": str(exc)}
    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
