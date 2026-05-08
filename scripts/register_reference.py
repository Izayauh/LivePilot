#!/usr/bin/env python3
"""Register a local reference track and cache its LUFS."""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.setup_comparison import (  # noqa: E402
    ComparisonSetupError,
    REFERENCE_LIBRARY_PATH,
    load_reference_library,
    measure_lufs,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Register a local reference track for setup_comparison.py."
    )
    parser.add_argument("--slug", required=True, help="Stable key, e.g. jackie_brown")
    parser.add_argument("--path", required=True, help="Local audio path")
    parser.add_argument("--title", required=True, help="Reference title")
    parser.add_argument("--artist", required=True, help="Reference artist")
    parser.add_argument("--library", default=str(REFERENCE_LIBRARY_PATH),
                        help=argparse.SUPPRESS)
    return parser


def register_reference(
    slug: str,
    path: str,
    title: str,
    artist: str,
    library_path: Path = REFERENCE_LIBRARY_PATH,
) -> dict:
    audio_path = Path(path).expanduser()
    if not audio_path.exists():
        raise ComparisonSetupError(f"Reference file does not exist: {audio_path}")

    library = load_reference_library(library_path)
    library.setdefault("schemaVersion", "live-pilot/reference-library.v1")
    entries = library.setdefault("entries", {})
    lufs = measure_lufs(str(audio_path))

    entry = {
        "title": title,
        "artist": artist,
        "path": str(audio_path.resolve()),
        "lufs": round(lufs, 2),
        "addedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    entries[slug] = entry

    library_path.parent.mkdir(parents=True, exist_ok=True)
    with library_path.open("w", encoding="utf-8") as f:
        json.dump(library, f, indent=2)
        f.write("\n")
    return entry


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        entry = register_reference(
            args.slug,
            args.path,
            args.title,
            args.artist,
            Path(args.library),
        )
    except ComparisonSetupError as exc:
        parser.exit(2, f"ERROR: {exc}\n")

    print(
        f"Registered {args.slug}: {entry['artist']} - {entry['title']} "
        f"({entry['lufs']:.2f} LUFS)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
