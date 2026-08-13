#!/usr/bin/env python3
"""Generate song analysis JSON files for the local librarian.

Uses Gemini 2.5 Pro with extended thinking for high-quality
vocal production analysis. Free tier supports 25 requests/day.

Usage:
    # Generate from a single prompt file
    python generate_song_data.py --prompt docs/Research/002_kanye-west-saint-pablo.prompt.txt

    # Generate from song info (builds prompt automatically)
    python generate_song_data.py --song "Saint Pablo" --artist "Kanye West"

    # Batch generate all prompt files that don't have a JSON yet
    python generate_song_data.py --batch docs/Research/

    # Validate an existing JSON file
    python generate_song_data.py --validate docs/Research/ultralight_beam.json

    # Use a different model (default: gemini-2.5-pro)
    python generate_song_data.py --prompt FILE --model gemini-2.5-flash
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from librarian.schema import validate_song_data, validate_song_file

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower()).strip("_")
    return s or "song"


def default_prompt(song: str, artist: str) -> str:
    """Build the full structured prompt when no .prompt.txt file is provided."""
    return (
        "You are an elite vocal production analyst helping build an offline "
        "vocal-chain database for an AI DAW assistant.\n"
        f"Song to analyze - ({song} - {artist})\n"
        'Return EXACTLY one valid JSON object (no markdown, no commentary) '
        "that follows this schema intent:\n"
        '{"song":{"title":string,"artist":string,"year":integer|null,"genre":string|null},'
        '"global_tags":string[],"sections":{"verse":{"intent":string,"chain":Device[]},'
        '"chorus":{"intent":string,"chain":Device[]},"background_vocals":{"intent":string,'
        '"chain":Device[]},"adlibs":{"intent":string,"chain":Device[]}},'
        '"confidence":number(0..1),"notes":string,"sources":string[]}\n'
        "Where each Device is:\n"
        '{"plugin":string,"stage":"cleanup"|"tone"|"dynamics"|"space"|"creative"|"utility",'
        '"key_params":{...},"param_why":{"param_name":"short reason"},"why":string}\n'
        f'Song to analyze:\n- title: "{song}"\n- artist: "{artist}"\n'
        "- optional context: \"JarvisAbleton training export\"\n"
        "Hard requirements:\n"
        "1) Include all 4 sections: verse, chorus, background_vocals, adlibs.\n"
        "2) For each section, provide an ORDERED chain (5-10 devices typical).\n"
        "3) key_params must be practical and machine-usable.\n"
        "4) Prefer common plugins and/or stock-equivalent naming.\n"
        "5) Do NOT fabricate false precision.\n"
        "6) Add global_tags for retrieval.\n"
        "7) Ensure param_why covers key_params entries.\n"
        "Return JSON only."
    )


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------

def call_gemini(prompt_text: str, model: str) -> str:
    """Send prompt to Gemini and return the raw response text.

    Uses extended thinking (thinking_budget) on models that support it
    (2.5 Pro, 2.5 Flash) for deeper reasoning about production choices.
    """
    from google import genai
    from google.genai import types

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("ERROR: GOOGLE_API_KEY not set. Add it to your .env file.")
        sys.exit(1)

    client = genai.Client(api_key=api_key)

    # Enable extended thinking for reasoning-capable models
    thinking_config = None
    if "2.5" in model:
        thinking_config = types.ThinkingConfig(thinking_budget=8192)

    config = types.GenerateContentConfig(
        temperature=0.3,  # Low temp for precision, thinking handles creativity
        thinking_config=thinking_config,
        response_mime_type="application/json",
    )

    print(f"  Calling {model} (thinking enabled: {thinking_config is not None})...")
    t0 = time.time()

    response = client.models.generate_content(
        model=model,
        contents=prompt_text,
        config=config,
    )

    elapsed = time.time() - t0
    print(f"  Response received in {elapsed:.1f}s")

    return response.text


def extract_json(raw: str) -> dict:
    """Parse JSON from the LLM response, stripping markdown fences if present."""
    text = raw.strip()
    # Strip ```json ... ``` wrapper if the model ignores instructions
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```\s*$", "", text)
    return json.loads(text)


# ---------------------------------------------------------------------------
# Core generate flow
# ---------------------------------------------------------------------------

def generate_from_prompt(prompt_text: str, output_path: Path, model: str) -> int:
    """Send prompt to LLM, validate response, save JSON. Returns exit code."""

    raw = call_gemini(prompt_text, model)

    # Parse JSON
    try:
        data = extract_json(raw)
    except json.JSONDecodeError as e:
        print(f"  ERROR: LLM response was not valid JSON: {e}")
        # Save raw response for debugging
        debug_path = output_path.with_suffix(".raw.txt")
        debug_path.write_text(raw, encoding="utf-8")
        print(f"  Raw response saved to: {debug_path}")
        return 1

    # Validate against schema
    ok, errs = validate_song_data(data)
    if ok:
        output_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"  VALID - saved to: {output_path}")
        return 0
    else:
        # Save as draft for manual review
        draft_path = output_path.with_suffix(".draft.json")
        draft_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"  INVALID - saved draft to: {draft_path}")
        for e in errs:
            print(f"    - {e}")
        return 1


def guess_output_name(prompt_text: str) -> str:
    """Try to extract song title from prompt text for the output filename."""
    m = re.search(r'title:\s*"([^"]+)"', prompt_text)
    if m:
        return slugify(m.group(1))
    m = re.search(r"Song to analyze - \((.+?) - ", prompt_text)
    if m:
        return slugify(m.group(1))
    return "unknown_song"


# ---------------------------------------------------------------------------
# Validate
# ---------------------------------------------------------------------------

def validate_and_print(path: Path) -> int:
    ok, errs = validate_song_file(str(path))
    if ok:
        print(f"VALID: {path}")
        return 0
    print(f"INVALID: {path}")
    for e in errs:
        print(f"  - {e}")
    return 1


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Generate or validate local librarian song JSON files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--validate", metavar="FILE", help="Validate an existing JSON file")
    parser.add_argument("--song", help="Song title (used with --artist)")
    parser.add_argument("--artist", help="Artist name (used with --song)")
    parser.add_argument("--prompt", metavar="FILE", help="Path to a .prompt.txt file")
    parser.add_argument("--batch", metavar="DIR", help="Directory with *.prompt.txt files")
    parser.add_argument(
        "--model",
        default="gemini-2.5-pro",
        help="Gemini model ID (default: gemini-2.5-pro for best quality)",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="In batch mode, skip songs that already have a .json file",
    )
    args = parser.parse_args()

    out_dir = Path(__file__).resolve().parent / "docs" / "Research"
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- Validate ---
    if args.validate:
        return validate_and_print(Path(args.validate))

    # --- Single prompt file ---
    if args.prompt:
        prompt_path = Path(args.prompt)
        if not prompt_path.exists():
            print(f"Prompt not found: {prompt_path}")
            return 1
        prompt_text = prompt_path.read_text(encoding="utf-8", errors="ignore")
        slug = guess_output_name(prompt_text)
        output_path = out_dir / f"{slug}.json"
        print(f"Generating: {prompt_path.name} -> {output_path.name}")
        return generate_from_prompt(prompt_text, output_path, args.model)

    # --- Song + Artist (generate prompt on the fly) ---
    if args.song and args.artist:
        prompt_text = default_prompt(args.song, args.artist)
        slug = slugify(args.song)
        output_path = out_dir / f"{slug}.json"
        print(f"Generating: {args.song} by {args.artist} -> {output_path.name}")
        return generate_from_prompt(prompt_text, output_path, args.model)

    # --- Batch ---
    if args.batch:
        d = Path(args.batch)
        prompt_files = sorted(d.glob("*.prompt.txt"))
        if not prompt_files:
            print(f"No .prompt.txt files found in {d}")
            return 1

        print(f"Found {len(prompt_files)} prompt files in {d}")
        results = {"success": 0, "failed": 0, "skipped": 0}

        for i, pf in enumerate(prompt_files, 1):
            prompt_text = pf.read_text(encoding="utf-8", errors="ignore")
            slug = guess_output_name(prompt_text)
            output_path = out_dir / f"{slug}.json"

            if args.skip_existing and output_path.exists():
                print(f"[{i}/{len(prompt_files)}] SKIP (exists): {output_path.name}")
                results["skipped"] += 1
                continue

            print(f"\n[{i}/{len(prompt_files)}] {pf.name}")
            rc = generate_from_prompt(prompt_text, output_path, args.model)
            if rc == 0:
                results["success"] += 1
            else:
                results["failed"] += 1

            # Brief pause between calls to respect rate limits
            if i < len(prompt_files):
                print("  (waiting 3s between calls...)")
                time.sleep(3)

        print(f"\n--- Batch complete ---")
        print(f"  Success: {results['success']}")
        print(f"  Failed:  {results['failed']}")
        print(f"  Skipped: {results['skipped']}")
        return 1 if results["failed"] > 0 else 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
