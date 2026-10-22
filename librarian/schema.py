from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import json

REQUIRED_SECTIONS = {"verse", "chorus", "background_vocals", "adlibs"}
VALID_STAGES = {"cleanup", "tone", "dynamics", "space", "creative", "utility"}


@dataclass
class SongMeta:
    title: str
    artist: str
    year: Optional[int] = None
    genre: Optional[str] = None


@dataclass
class Device:
    plugin: str
    stage: str
    key_params: Dict[str, Any]
    param_why: Dict[str, str]
    why: str


@dataclass
class Section:
    intent: str
    chain: List[Device]


@dataclass
class SongAnalysis:
    song: SongMeta
    global_tags: List[str]
    sections: Dict[str, Section]
    confidence: float
    notes: str = ""
    sources: List[str] = field(default_factory=list)


def _is_non_empty_string(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


def validate_song_data(data: dict) -> Tuple[bool, List[str]]:
    errors: List[str] = []

    song = data.get("song")
    if not isinstance(song, dict):
        errors.append("song must be an object")
    else:
        if not _is_non_empty_string(song.get("title")):
            errors.append("song.title must be a non-empty string")
        if not _is_non_empty_string(song.get("artist")):
            errors.append("song.artist must be a non-empty string")
        year = song.get("year")
        if year is not None and not isinstance(year, int):
            errors.append("song.year must be an integer or null")
        genre = song.get("genre")
        if genre is not None and not isinstance(genre, str):
            errors.append("song.genre must be a string or null")

    global_tags = data.get("global_tags")
    if not isinstance(global_tags, list) or not global_tags:
        errors.append("global_tags must be a non-empty list")
    elif any(not _is_non_empty_string(t) for t in global_tags):
        errors.append("global_tags must contain non-empty strings")

    sections = data.get("sections")
    if not isinstance(sections, dict):
        errors.append("sections must be an object")
    else:
        missing = REQUIRED_SECTIONS - set(sections.keys())
        if missing:
            errors.append(f"sections missing required keys: {sorted(missing)}")

        for sec_name, sec_data in sections.items():
            if not isinstance(sec_data, dict):
                errors.append(f"sections.{sec_name} must be an object")
                continue
            if not _is_non_empty_string(sec_data.get("intent", "")) and sec_data.get("intent") is not None:
                errors.append(f"sections.{sec_name}.intent must be a string")
            chain = sec_data.get("chain")
            if not isinstance(chain, list):
                errors.append(f"sections.{sec_name}.chain must be a list")
                continue

            for i, device in enumerate(chain):
                path = f"sections.{sec_name}.chain[{i}]"
                if not isinstance(device, dict):
                    errors.append(f"{path} must be an object")
                    continue
                if not _is_non_empty_string(device.get("plugin")):
                    errors.append(f"{path}.plugin must be a non-empty string")
                stage = device.get("stage")
                if stage not in VALID_STAGES:
                    errors.append(f"{path}.stage must be one of {sorted(VALID_STAGES)}")
                key_params = device.get("key_params")
                param_why = device.get("param_why")
                if not isinstance(key_params, dict):
                    errors.append(f"{path}.key_params must be an object")
                    key_params = {}
                if not isinstance(param_why, dict):
                    errors.append(f"{path}.param_why must be an object")
                    param_why = {}
                for k in key_params.keys():
                    if k not in param_why:
                        errors.append(f"{path}.param_why missing key '{k}'")
                if not _is_non_empty_string(device.get("why", "")):
                    errors.append(f"{path}.why must be a non-empty string")

    conf = data.get("confidence")
    if not isinstance(conf, (int, float)):
        errors.append("confidence must be a number between 0.0 and 1.0")
    elif conf < 0.0 or conf > 1.0:
        errors.append("confidence must be between 0.0 and 1.0")

    return (len(errors) == 0, errors)


def validate_song_file(path: str) -> Tuple[bool, List[str]]:
    p = Path(path)
    if not p.exists():
        return False, [f"File does not exist: {path}"]
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return False, [f"Failed to parse JSON: {e}"]
    return validate_song_data(data)
