"""
LivePilot workflow handlers (repo-owned extension of the LivePilot remote script).

Source of truth: music/live-pilot/ableton_remote_script/LivePilot/lp_workflows.py.
Deployed by scripts/deploy_remote_handlers.py into the User Library copy of
Remote Scripts/LivePilot and picked up by its reload_handlers command, so no
Control Surface toggle is needed.

device_index -1 addresses the track's mixer: parameter 0 = Volume,
1 = Pan, 2.. = sends A, B, ...
"""

from .router import register
from .utils import get_track, get_device
from . import lp_dialcore

MIXER = -1


def _params(track, device_index):
    if int(device_index) == MIXER:
        return lp_dialcore.mixer_params(track)
    return list(get_device(track, int(device_index)).parameters)


def _string(param, value):
    try:
        return param.str_for_value(value)
    except Exception:
        return None


def _describe(index, param):
    entry = {
        "index": index,
        "name": param.name,
        "value": param.value,
        "min": param.min,
        "max": param.max,
        "is_quantized": param.is_quantized,
        "value_string": _string(param, param.value),
    }
    if param.is_quantized:
        try:
            entry["value_items"] = list(param.value_items)
        except Exception:
            pass
    return entry


@register("lp_clock")
def lp_clock(song, params):
    """Wall-clock time on Live's main thread, to split a round trip into its legs."""
    import time
    return {"t": time.time()}


def _target(song, params):
    """(track, rs_index, name) from params['track'] (name/index spec) or params['track_index'] (raw)."""
    if params.get("track") is not None:
        tracks = [(i, tr.name) for i, tr in enumerate(song.tracks)]
        returns = [(-(i + 1), tr.name) for i, tr in enumerate(song.return_tracks)]
        rs_index, name = lp_dialcore.resolve_track(params["track"], tracks, returns)
    else:
        rs_index, name = int(params["track_index"]), None
    track = get_track(song, rs_index)
    return track, rs_index, name or track.name


def _devices(track):
    return [{"index": i, "name": d.name, "class_name": d.class_name, "is_active": d.is_active}
            for i, d in enumerate(track.devices)]


@register("lp_chain")
def lp_chain(song, params):
    """Compact device chain: index, name, class, on/off. No parameters."""
    track, rs_index, name = _target(song, params)
    return {"track_index": rs_index, "track_name": name, "devices": _devices(track)}


@register("lp_chain_add")
def lp_chain_add(song, params):
    """Load one device by exact browser name at `position` (-1 = end) and return the new chain.

    Runs JarvisDeviceLoader's own load routine in this tick, so a load is one round trip.
    """
    import sys
    loader = getattr(sys.modules.get("JarvisDeviceLoader"), "INSTANCE", None)
    if loader is None:
        raise RuntimeError("JarvisDeviceLoader is not running in Live. Select it as a control surface "
                           "and restart Live once.")
    track, rs_index, name = _target(song, params)
    before = len(track.devices)
    if rs_index == lp_dialcore.MASTER:
        kind, index = "master", -1
    elif rs_index < 0:
        kind, index = "return", -rs_index - 1
    else:
        kind, index = "track", rs_index
    result = loader._load_device_on_track(index, params["name"], int(params.get("position", -1)), kind)
    devices = _devices(track)
    if len(devices) != before + 1:
        message = result[2] if len(result) > 2 else "load failed"
        raise RuntimeError("%s (chain went from %d to %d devices)" % (message, before, len(devices)))
    return {"track_index": rs_index, "track_name": name, "device_index": result[3] if len(result) > 3 else None,
            "devices": devices}


@register("lp_params")
def lp_params(song, params):
    """All parameters of a device (or the mixer) with display strings."""
    track = get_track(song, int(params["track_index"]))
    plist = _params(track, params["device_index"])
    return {"parameters": [_describe(i, p) for i, p in enumerate(plist)]}


@register("lp_dial")
def lp_dial(song, params):
    """Whole dial in one call: resolve names, solve the display value, set, read back."""
    return lp_dialcore.dial(song, get_track, params["track"], params["param"], to=params.get("to"),
                            by=params.get("by"), device=params.get("device"))


@register("lp_notes_write")
def lp_notes_write(song, params):
    """Replace (default) or append a clip's notes and read the whole clip back, in one call.

    params: track_index, clip_index, notes [[pitch, start, duration, velocity, mute]], mode.
    Returns the clip's notes before and after as the same five-field lists.
    """
    import Live
    from .utils import get_clip
    from ._clip_helpers import _extend_loop_end_for_notes

    clip = get_clip(song, int(params["track_index"]), int(params["clip_index"]))
    notes = [{"pitch": int(n[0]), "start_time": float(n[1]), "duration": float(n[2]),
              "velocity": float(n[3]), "mute": bool(n[4])} for n in params["notes"]]

    def read():
        return [[n.pitch, n.start_time, n.duration, n.velocity, int(n.mute)]
                for n in clip.get_notes_extended(0, 128, 0.0, 1e9)]

    before = read()
    song.begin_undo_step()
    try:
        if params.get("mode", "replace") == "replace":
            clip.remove_notes_extended(0, 128, 0.0, 1e9)
        if notes:
            _extend_loop_end_for_notes(clip, notes)
            clip.add_new_notes(tuple(Live.Clip.MidiNoteSpecification(**n) for n in notes))
    finally:
        song.end_undo_step()
    return {"before": before, "after": read()}


@register("lp_set")
def lp_set(song, params):
    """Write one raw value and read it back with its display string."""
    track = get_track(song, int(params["track_index"]))
    param = _params(track, params["device_index"])[int(params["parameter_index"])]
    value = float(params["value"])
    if not (param.min <= value <= param.max):
        raise ValueError("%s: %s is outside %s..%s" % (param.name, value, param.min, param.max))
    param.value = value
    return {"name": param.name, "value": param.value,
            "value_string": _string(param, param.value)}


@register("lp_marker")
def lp_marker(song, params):
    """Put a locator at a beat, or delete the one there (delete: true). Call until done is true.

    params: time (beats), delete (bool, optional).
    Live moves the playhead on its next tick and set_or_delete_cue acts where the playhead IS,
    so the first call moves the playhead and returns done false; the next call toggles the locator.
    Locator names are read-only through Live's API ("can't set attribute"), so this does not name them.
    """
    time, delete = float(params["time"]), bool(params.get("delete", False))
    def at():
        return next((c for c in song.cue_points if abs(c.time - time) < 1e-3), None)
    def listing():
        return [{"name": c.name, "time": c.time} for c in sorted(song.cue_points, key=lambda c: c.time)]
    if (at() is not None) != delete:
        return {"done": True, "cue_points": listing()}
    if abs(song.current_song_time - time) > 1e-3:
        song.current_song_time = time
        return {"done": False, "cue_points": listing()}
    song.set_or_delete_cue()
    return {"done": (at() is not None) != delete, "cue_points": listing()}


@register("lp_audio_clip")
def lp_audio_clip(song, params):
    """Where an arrangement audio clip's sound lives and how its file maps onto the song's beats.

    params: track_index, clip_index (arrangement). warp_markers are [sample_seconds, clip_beat];
    arrangement beat = start_time + clip_beat - start_marker.
    """
    track = get_track(song, int(params["track_index"]))
    clip = list(track.arrangement_clips)[int(params["clip_index"])]
    if not clip.is_audio_clip:
        raise ValueError("clip %s on track %s is not audio" % (params["clip_index"], params["track_index"]))
    return {"file_path": str(clip.file_path), "name": clip.name, "start_time": clip.start_time,
            "end_time": clip.end_time, "start_marker": clip.start_marker, "end_marker": clip.end_marker,
            "looping": bool(clip.looping), "warping": bool(clip.warping), "tempo": song.tempo,
            "warp_markers": [[m.sample_time, m.beat_time] for m in clip.warp_markers]}
