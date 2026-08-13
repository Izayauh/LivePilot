#!/usr/bin/env python
"""Export Native Instruments Kontakt starred favorites for LivePilot."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from livepilot_tools.kontakt_library import export_kontakt_favorites, filter_favorites


def main() -> int:
    parser = argparse.ArgumentParser(description="Export Kontakt favorites from Native Instruments local databases.")
    parser.add_argument("--output", default=str(_REPO_ROOT / "config" / "kontakt_favorites.json"))
    parser.add_argument("--include-komplete-kontrol", action="store_true")
    parser.add_argument("--role", default=None, help="Optional role filter to print, e.g. piano, strings, pads.")
    args = parser.parse_args()

    data = export_kontakt_favorites(
        args.output,
        include_komplete_kontrol=args.include_komplete_kontrol,
    )
    print(f"Exported {len(data['favorites'])} Kontakt favorites to {args.output}")
    if args.role:
        matches = filter_favorites(data["favorites"], role=args.role)
        print(json.dumps(matches, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
