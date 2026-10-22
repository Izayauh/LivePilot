"""Track resolution shared by dial, chain, rack, recipe and audio_to_midi (no Live needed)."""
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("lp_dialcore", ROOT / "ableton_remote_script" / "LivePilot" / "lp_dialcore.py")
core = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(core)

TRACKS = [(0, "1-MNT_SS_110_violin_duo_waves_full_Em"), (1, "2-MIDI"), (2, "3-Audio"), (3, "4-Audio"), (4, "Piano Rig")]
RETURNS = [(-1, "A-Reverb"), (-2, "B-Delay")]


def name(spec, tracks=TRACKS):
    return core.resolve_track(spec, tracks, RETURNS)[1]


def test_number_finds_the_track_with_that_prefix():
    assert name("4") == "4-Audio"


def test_number_past_the_prefixes_is_the_position():
    assert name("5") == "Piano Rig"


def test_prefix_name_ignores_case():
    assert name("4-audio") == "4-Audio"


def test_exact_name_beats_number_and_position():
    tracks = TRACKS[:3] + [(3, "4"), (4, "4-Audio")]
    assert core.resolve_track("4", tracks, RETURNS) == (3, "4")


def test_whole_number_token_still_matches():
    assert name("110") == "1-MNT_SS_110_violin_duo_waves_full_Em"


def test_int_is_the_remote_script_index():
    assert core.resolve_track(3, TRACKS, RETURNS) == (3, "4-Audio")


def test_returns_and_master():
    assert name("return A") == "A-Reverb"
    assert core.resolve_track("master", TRACKS, RETURNS)[0] == core.MASTER


def test_several_prefixes_are_named():
    tracks = [(0, "4-Kick"), (1, "4 Snare"), (2, "Pad")]
    with pytest.raises(core.DialError, match="4-Kick, 4 Snare"):
        core.resolve_track("4", tracks, [])


def test_miss_names_three_closest_not_all():
    many = TRACKS + [(5, "Bass"), (6, "Vox"), (7, "Lead"), (8, "Pad")]
    with pytest.raises(core.DialError) as e:
        core.resolve_track("Pinao", many, RETURNS)
    msg = str(e.value)
    assert "Closest:" in msg and "Piano Rig" in msg
    assert len(msg.split("Closest:")[1].split(",")) <= 3
    assert "Vox" not in msg or "Closest" in msg


def test_number_miss_also_names_closest():
    with pytest.raises(core.DialError, match="Closest:"):
        core.resolve_track("99", TRACKS, RETURNS)


def test_short_prefix_and_exact_name_ignore_case():
    assert name("4-Aud") == "4-Audio"
    assert name("piano rig") == "Piano Rig"


def test_position_wins_when_prefix_disagrees():
    tracks = [(0, "Kick"), (1, "Snare"), (2, "Hats"), (3, "Bass"), (4, "4-Pad")]
    assert core.resolve_track("4", tracks, RETURNS) == (3, "Bass")


def test_numbers_count_regular_tracks_only():
    with pytest.raises(core.DialError):
        core.resolve_track("6", TRACKS, RETURNS)  # 5 tracks; returns A/B are not 6 and 7


def test_miss_names_exactly_three_tracks():
    with pytest.raises(core.DialError) as e:
        core.resolve_track("9", TRACKS, RETURNS)
    msg = str(e.value)
    assert msg.startswith("No track '9'. Closest: ")
    named = msg.split("Closest: ")[1].rstrip(".").split(", ")
    assert len(named) == 3
    assert all(n in [t for _, t in TRACKS + RETURNS] for n in named)
