"""Deterministic helpers for aligning full-length audio stems in Ableton."""

from __future__ import annotations

from typing import Any, Iterable


def normalize_full_length_stems(
    *,
    bpm: float,
    track_indices: Iterable[int],
    clip_index: int = 0,
    duration_seconds: float | None = None,
    scene_index: int | None = None,
    controller: Any,
) -> dict[str, Any]:
    """Play full-song stems at their original speed from a common zero point."""
    bpm = float(bpm)
    tracks = [int(index) for index in track_indices]
    clip_index = int(clip_index)

    if not 20.0 <= bpm <= 999.0:
        raise ValueError("bpm must be between 20 and 999")
    if not tracks:
        raise ValueError("track_indices must contain at least one track")
    if len(set(tracks)) != len(tracks):
        raise ValueError("track_indices must not contain duplicates")
    if clip_index < 0:
        raise ValueError("clip_index must be non-negative")
    if duration_seconds is not None and float(duration_seconds) <= 0:
        raise ValueError("duration_seconds must be positive")

    operations: list[dict[str, Any]] = []

    tempo_result = controller.set_tempo(bpm)
    operations.append({"operation": "set_tempo", "result": tempo_result})
    if not tempo_result.get("success"):
        return {
            "success": False,
            "bpm": bpm,
            "track_indices": tracks,
            "operations": operations,
        }

    for track_index in tracks:
        clip_operations = (
            ("disable_warp", controller.set_audio_clip_warping, False),
            ("disable_loop", controller.set_audio_clip_looping, False),
            ("set_start_marker", controller.set_audio_clip_start_marker, 0.0),
            ("set_loop_start", controller.set_audio_clip_loop_start, 0.0),
        )
        for operation, method, value in clip_operations:
            result = method(track_index, clip_index, value)
            operations.append(
                {
                    "operation": operation,
                    "track_index": track_index,
                    "clip_index": clip_index,
                    "result": result,
                }
            )
            if not result.get("success"):
                return {
                    "success": False,
                    "bpm": bpm,
                    "track_indices": tracks,
                    "operations": operations,
                }

        if duration_seconds is not None:
            end = float(duration_seconds)
            end_operations = (
                ("set_end_marker", controller.set_audio_clip_end_marker),
                ("set_loop_end", controller.set_audio_clip_loop_end),
            )
            for operation, method in end_operations:
                result = method(track_index, clip_index, end)
                operations.append(
                    {
                        "operation": operation,
                        "track_index": track_index,
                        "clip_index": clip_index,
                        "result": result,
                    }
                )
                if not result.get("success"):
                    return {
                        "success": False,
                        "bpm": bpm,
                        "track_indices": tracks,
                        "operations": operations,
                    }

    if scene_index is not None:
        scene_result = controller.fire_scene(int(scene_index))
        operations.append(
            {
                "operation": "fire_scene",
                "scene_index": int(scene_index),
                "result": scene_result,
            }
        )
        if not scene_result.get("success"):
            return {
                "success": False,
                "bpm": bpm,
                "track_indices": tracks,
                "operations": operations,
            }

    return {
        "success": True,
        "bpm": bpm,
        "track_indices": tracks,
        "clip_index": clip_index,
        "warping": False,
        "looping": False,
        "start_marker": 0.0,
        "loop_start": 0.0,
        "duration_seconds": (
            float(duration_seconds) if duration_seconds is not None else None
        ),
        "scene_index": scene_index,
        "operations": operations,
    }
