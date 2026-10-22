"""
Name resolution and display-value solving for dial, shared by Live and the client.

Pure Python 3.7 (Live 11's interpreter), no relative imports, so the same file
runs inside Live (imported by lp_workflows) and in the MCP server (loaded by
livepilot_tools/workflows.py from this path).

dial() does a whole dial inside one Live command: resolve the track, device
and parameter by name, solve the raw value whose display reads the target
using Live's own str_for_value, write it, and read it back. Measured
2026-10-14: the old client-side loop made 5-7 round trips at 220-550 ms each.
"""

import difflib
import hashlib
import json
import math
import re

MASTER = -1000
MIXER = -1

MIXER_ALIASES = {"volume": 0, "vol": 0, "fader": 0, "level": 0, "gain": 0,
                 "pan": 1, "panning": 1, "balance": 1}

_UNIT_ALIASES = {"db": "db", "hz": "hz", "khz": "khz", "ms": "ms", "s": "s", "sec": "s",
                 "%": "%", "pct": "%", "percent": "%", "st": "st", "semitones": "st",
                 "ct": "ct", "cents": "ct", ":1": "ratio", "x": "x"}


class DialError(ValueError):
    """A failure with a plain-English fix the caller can relay as-is."""


# ---------------------------------------------------------------------------
# Name resolution
# ---------------------------------------------------------------------------

def norm(text):
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()


def closest(spec, names, n=3):
    """Up to n names nearest to spec: difflib matches first, padded by similarity ratio."""
    want = str(spec).lower()
    low = {}
    for name in names:
        low.setdefault(str(name).lower(), name)
    found = difflib.get_close_matches(want, list(low), n=n, cutoff=0.1)
    rest = sorted((k for k in low if k not in found),
                  key=lambda k: -difflib.SequenceMatcher(None, want, k).ratio())
    return [low[k] for k in (found + rest)[:n]]


def pick(spec, items, what):
    """Exact (case/punctuation-insensitive) match, then unique substring, then all-words match."""
    want = norm(spec)
    for key, name in items:
        if norm(name) == want:
            return key, name
    for test in (lambda n: want in norm(n),
                 lambda n: all(w in norm(n).split() or w in norm(n) for w in want.split())):
        hits = [(k, n) for k, n in items if test(n)]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            raise DialError("'%s' matches several %ss: %s. Be more specific."
                            % (spec, what, ", ".join(n for _, n in hits[:8])))
    if what == "track":
        return _no_track(spec, items)
    raise DialError("No %s named '%s'. Available: %s."
                    % (what, spec, ", ".join(n for _, n in items[:20]) or "none"))


def _no_track(spec, items):
    near = closest(spec, [n for _, n in items])
    raise DialError("No track '%s'.%s" % (spec, " Closest: %s." % ", ".join(near) if near else ""))


def set_sig(names):
    """Which set we are in: Live exposes no file path, so hash the track and return names."""
    return hashlib.sha1(json.dumps(names).encode("utf-8")).hexdigest()[:10] if names else ""


def resolve_track(spec, tracks, returns):
    """Track spec -> (remote-script index, name). tracks/returns: [(rs_index, name)].

    An int is the remote-script index. A string tries, in order: exact name, 'master',
    'return A', then for a digit string N: the Nth regular track in Live's order (1-based,
    returns and master not counted), the track named "N-..." / "N ...", a whole number
    token ("808" -> "1-808 Drifter");
    else unique substring / all-words. A miss names the three closest tracks.
    """
    if isinstance(spec, bool):
        raise DialError("track must be a name or number")
    if isinstance(spec, (int, float)):
        idx = int(spec)
        for key, name in tracks:
            if key == idx:
                return key, name
        raise DialError("No track %d. Tracks are 0..%d." % (idx, len(tracks) - 1))
    s = norm(spec)
    allt = tracks + returns
    for key, name in allt:
        if norm(name) == s:
            return key, name
    if s in ("master", "main", "master track"):
        return MASTER, "Master"
    m = re.match(r"(?:return|ret|send)\s*([a-z])$", s)
    if m:
        ri = ord(m.group(1)) - ord("a")
        if ri < len(returns):
            return returns[ri]
        raise DialError("No return %s." % m.group(1).upper())
    if s.isdigit():
        if 1 <= int(s) <= len(tracks):  # position wins over a "N-..." name elsewhere in the set
            return tracks[int(s) - 1]
        lead = [(k, n) for k, n in tracks if re.match(re.escape(s) + r"(?!\d)", norm(n))]
        if len(lead) == 1:
            return lead[0]
        if len(lead) > 1:
            raise DialError("'%s' starts several tracks: %s." % (spec, ", ".join(n for _, n in lead[:3])))
        token_hits = [(k, n) for k, n in allt if s in norm(n).split()]
        if len(token_hits) == 1:
            return token_hits[0]
        if len(token_hits) > 1:
            raise DialError("'%s' matches several tracks: %s." % (spec, ", ".join(n for _, n in token_hits[:8])))
        for key, name in tracks:
            if key == int(s):  # nothing else fits: the remote-script index, as before
                return key, name
        _no_track(spec, allt)
    return pick(str(spec), allt, "track")


def is_mixer_param(spec):
    s = norm(spec)
    return s in MIXER_ALIASES or re.match(r"send\s*[a-z]$", s) is not None


def resolve_param_index(names, spec, is_mixer):
    """names: parameter names in order. Returns the chosen index."""
    if isinstance(spec, int) and not isinstance(spec, bool):
        if 0 <= spec < len(names):
            return spec
        raise DialError("No parameter %d (%d parameters)." % (spec, len(names)))
    s = norm(spec)
    if is_mixer:
        if s in MIXER_ALIASES:
            return MIXER_ALIASES[s]
        m = re.match(r"send\s*([a-z])$", s)
        if m and 2 + ord(m.group(1)) - ord("a") < len(names):
            return 2 + ord(m.group(1)) - ord("a")
    key, _ = pick(str(spec), list(enumerate(names)), "parameter")
    return key


# ---------------------------------------------------------------------------
# Display values
# ---------------------------------------------------------------------------

def parse_display(text):
    """'-6.0 dB' -> (-6.0, 'db'), '2.50 kHz' -> (2500, 'hz'), '30L' -> (-30, 'pan'), 'C' -> (0, 'pan')."""
    if text is None:
        return None
    t = str(text).strip().lower().replace(",", "")
    if t in ("c", "center", "centre"):
        return 0.0, "pan"
    m = re.match(r"(\d+(?:\.\d+)?)\s*([lr])$", t)
    if m:
        v = float(m.group(1))
        return (-v if m.group(2) == "l" else v), "pan"
    if t in ("-inf db", "-inf"):
        return -math.inf, "db"
    m = re.match(r"([+-]?\d+(?:\.\d+)?)\s*(?::\s*1)?\s*([a-z%]*)$", t)
    if not m:
        return None
    value, unit = float(m.group(1)), m.group(2)
    if ":" in t:
        return value, "ratio"
    unit = _UNIT_ALIASES.get(unit, unit)
    if unit == "khz":
        return value * 1000.0, "hz"
    if unit == "s":
        return value * 1000.0, "ms"
    return value, unit


def _units_match(target_unit, unit):
    return target_unit == "" or unit == "" or target_unit == unit


def solve_raw(param, target, unit):
    """Find the raw value whose display reads `target` (in `unit`), using Live's own formatter.

    Samples the range, finds the bracketing pair, and refines. Nothing is written.
    """
    lo, hi = float(param.min), float(param.max)
    best = None  # (error, raw)
    for n in (256, 64, 64):
        raws = [lo + (hi - lo) * i / n for i in range(n + 1)]
        parsed = [parse_display(_string(param, r)) for r in raws]
        points = [(r, p[0]) for r, p in zip(raws, parsed) if p is not None and _units_match(unit, p[1])]
        if not points:
            raise DialError("%s does not display in %s (it shows e.g. '%s')."
                            % (param.name, unit or "numbers", _string(param, param.value)))
        for r, v in points:
            err = abs(v - target) if math.isfinite(v) else (0.0 if v == target else math.inf)
            if best is None or err < best[0]:
                best = (err, r)
        bracket = None
        for (r1, v1), (r2, v2) in zip(points, points[1:]):
            if min(v1, v2) <= target <= max(v1, v2):
                bracket = (r1, r2)
                break
        if bracket is None:
            raise DialError("%s cannot reach %g %s; it goes from %s to %s."
                            % (param.name, target, unit, _string(param, float(param.min)),
                               _string(param, float(param.max))))
        lo, hi = bracket
        if best[0] == 0.0:
            break
    return best[1]


def _items(param):
    try:
        return list(param.value_items) if param.is_quantized else []
    except Exception:
        return []


def target_raw(param, to, by):
    """Turn to=/by= into a raw value. Numbers are raw Live values; strings are display values."""
    pmin, pmax = float(param.min), float(param.max)
    if param.is_quantized and isinstance(to, str):
        word = norm(to)
        items = _items(param)
        for i, item in enumerate(items):
            if norm(item) == word:
                return pmin + i
        if word in ("on", "enable", "enabled", "true") and pmax - pmin == 1:
            return pmax
        if word in ("off", "disable", "disabled", "false", "bypass") and pmax - pmin == 1:
            return pmin
        raise DialError("%s options: %s." % (param.name, ", ".join(items) or "%g..%g" % (pmin, pmax)))
    if to is not None:
        if isinstance(to, (int, float)):
            return float(to)
        parsed = parse_display(to)
        if parsed is None:
            raise DialError("Could not read '%s' as a value. Try '-6 dB', '310 ms', '2.5 kHz', '40 %%', '30L'." % to)
        return solve_raw(param, parsed[0], parsed[1])
    if isinstance(by, (int, float)):
        return float(param.value) + float(by)
    delta = parse_display(by)
    current = parse_display(_string(param, param.value))
    if delta is None or current is None or not math.isfinite(current[0]):
        raise DialError("Could not apply '%s' to %s (currently %s)." % (by, param.name, _string(param, param.value)))
    if delta[1] and current[1] and delta[1] != current[1]:
        raise DialError("%s is in %s, not %s." % (param.name, current[1], delta[1]))
    return solve_raw(param, current[0] + delta[0], current[1])


def _string(param, value):
    try:
        return param.str_for_value(value)
    except Exception:
        return None


def _close(a, b, span):
    return abs(a - b) <= max(1e-6, abs(span) * 0.002)


# ---------------------------------------------------------------------------
# One-call dial over Live objects
# ---------------------------------------------------------------------------

def mixer_params(track):
    mixer = track.mixer_device
    return [mixer.volume, mixer.panning] + list(mixer.sends)


def dial(song, get_track, track, param, to=None, by=None, device=None):
    """Resolve, solve, set and read back one parameter. Reads only when to and by are None.

    song: Live.Song (or a stand-in with .tracks, .return_tracks, .master_track).
    get_track(song, rs_index): the remote script's track lookup.
    """
    tracks = [(i, t.name) for i, t in enumerate(song.tracks)]
    returns = [(-(i + 1), t.name) for i, t in enumerate(song.return_tracks)]
    rs_index, track_name = resolve_track(track, tracks, returns)
    if device is None and not is_mixer_param(param):
        raise DialError("Which device on %s? Pass device= (e.g. 'EQ Eight'), "
                        "or use volume / pan / send A for the mixer." % track_name)
    live_track = get_track(song, rs_index)
    if device is None or norm(device) in ("mixer", "fader", "channel"):
        device_index, device_name, plist = MIXER, "Mixer", mixer_params(live_track)
    else:
        devices = list(live_track.devices)
        if isinstance(device, int) or (isinstance(device, str) and device.strip().isdigit()):
            device_index = int(device)
            if not 0 <= device_index < len(devices):
                raise DialError("No device %d on this track (%d devices)." % (device_index, len(devices)))
        else:
            try:
                device_index, _ = pick(str(device), [(i, d.name) for i, d in enumerate(devices)], "device")
            except DialError:
                device_index, _ = pick(str(device), [(i, d.class_name) for i, d in enumerate(devices)], "device")
        device_name = devices[device_index].name
        plist = list(devices[device_index].parameters)
    p_index = resolve_param_index([p.name for p in plist], param, device_index == MIXER)
    p = plist[p_index]
    label = "%s > %s > %s" % (track_name, device_name, p.name)
    before_raw, before = p.value, _string(p, p.value)
    out = {"track": rs_index, "device": device_index, "device_name": device_name, "param": p_index,
           "label": label, "before_raw": before_raw, "before": before, "range": [p.min, p.max],
           "set": set_sig([n for _, n in tracks] + [n for _, n in returns])}
    if to is None and by is None:
        out["read_only"] = True
        return out
    raw = target_raw(p, to, by)
    if not float(p.min) <= raw <= float(p.max):
        raise DialError("%s raw range is %g..%g; %g is outside it." % (p.name, p.min, p.max, raw))
    p.value = raw
    out.update({"after_raw": p.value, "after": _string(p, p.value),
                "verified": _close(float(p.value), raw, float(p.max) - float(p.min))})
    return out
