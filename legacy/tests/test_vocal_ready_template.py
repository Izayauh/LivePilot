import unittest
from unittest.mock import patch

from scripts.improve_vocal_ready_template import (
    DEVICE_PROFILES,
    EQ_PROFILES,
    PRIORITY_BUS_DYNAMICS,
    PRIORITY_RETURN_DELAYS,
    RETURN_SEND_TARGETS,
    ROUTING_PLAN,
    SEND_PLAN,
    TRACK_DEVICE_PROFILE_OVERRIDES,
    delay_display_value_matches,
    ensure_return_slots_for_send_plan,
    ensure_devices,
    ensure_routing_and_sends,
    expected_delay_readback_value,
    expected_dynamics_readback_value,
    expected_readback_value,
    expanded_routing_plan,
    find_priority_bus_dynamics_device,
    find_priority_return_delay_device,
    find_eq_eight_device_for_readback,
    frequency_hz_to_normalized,
    glue_display_value_matches,
    parameter_profile_track_order,
    parameter_profile_work_items,
    probe_return_slot_count,
    profile_for_device,
    required_return_slot_count,
    verify_routing_readback_for_template_routes,
    verify_send_readback_for_template_sends,
    verify_priority_bus_dynamics_readback,
    verify_return_delay_readback_for_template_returns,
    should_report_delay_value_string,
    should_report_dynamics_value_string,
    ensure_track_settings,
)
from ableton_controls.reliable_params import ReliableParameterController, smart_normalize_parameter
from templates.template_manager import template_manager


class TestVocalReadyTemplate(unittest.TestCase):
    def setUp(self):
        self.template = template_manager.get_template("vocal_ready_beat")

    def test_template_is_registered(self):
        self.assertIsNotNone(self.template)
        self.assertIn("vocal_ready_beat", template_manager.list_templates())

    def test_core_tracks_are_present(self):
        names = {track.name for track in self.template.tracks}
        expected = {
            "DRUMS - Kick",
            "DRUM BUS",
            "BASS - Sub 808",
            "MUSIC BUS - Vocal Pocket",
            "VOCAL - Lead Placeholder",
            "VOCAL BUS",
            "REFERENCE / PRINT",
        }
        self.assertTrue(expected.issubset(names))

    def test_vocal_pocket_metadata_exists(self):
        pocket_tracks = [
            track for track in self.template.tracks
            if track.settings.get("pocket") or track.settings.get("pocket_key")
        ]
        self.assertGreaterEqual(len(pocket_tracks), 8)

        music_bus = next(
            track for track in self.template.tracks
            if track.name == "MUSIC BUS - Vocal Pocket"
        )
        self.assertIn("carve_ranges_hz", music_bus.settings)

    def test_returns_are_filtered_for_vocals(self):
        return_names = {track.name for track in self.template.return_tracks}
        self.assertIn("SEND - Short Plate", return_names)
        self.assertIn("SEND - Throw Delay", return_names)

        filtered_returns = [
            track for track in self.template.return_tracks
            if "high_pass_hz" in track.settings and "low_pass_hz" in track.settings
        ]
        self.assertGreaterEqual(len(filtered_returns), 4)

    def test_template_avoids_blocked_or_bad_resolver_devices(self):
        blocked = {
            "Pro-Q 3",
            "Pro-Q 4",
            "FabFilter Pro-Q 3",
            "FabFilter Pro-Q 4",
            "Wavetable",
            "Operator",
        }
        devices = {
            device
            for track in self.template.tracks + self.template.return_tracks
            for device in track.devices
        }
        self.assertFalse(blocked & devices)

        bass = next(track for track in self.template.tracks if track.name == "BASS - Sub 808")
        self.assertIn("Drift", bass.devices)

    def test_stock_synth_placeholders_request_drift_directly(self):
        for track_name in ["BASS - Sub 808", "MUSIC - Chords", "MUSIC - Keys Pad", "MUSIC - Lead Hook"]:
            track = next(track for track in self.template.tracks if track.name == track_name)
            self.assertEqual(track.devices[0], "Drift")

    def test_bus_routing_plan_exists_for_core_sources(self):
        self.assertEqual(ROUTING_PLAN["DRUMS - Kick"], "DRUM BUS")
        self.assertEqual(ROUTING_PLAN["BASS - Sub 808"], "BASS BUS")
        self.assertEqual(ROUTING_PLAN["MUSIC - Chords"], "MUSIC BUS - Vocal Pocket")
        self.assertEqual(ROUTING_PLAN["FX - Transitions Texture"], "MUSIC BUS - Vocal Pocket")
        self.assertEqual(ROUTING_PLAN["VOCAL - Lead Placeholder"], "VOCAL BUS")

    def test_supplemental_template_family_tracks_route_to_matching_buses(self):
        template_names = {track.name for track in self.template.tracks}
        track_names = set(template_names) | {
            "BASS - Boomin 808 Floor Audio",
            "DRUMS - Extra Perc",
            "MUSIC - Verse Texture",
            "VOCAL - Hook Stack",
            "REFERENCE / PRINT Alt",
        }

        plan = expanded_routing_plan(template_names, track_names)

        self.assertEqual(plan["BASS - Boomin 808 Floor Audio"], "BASS BUS")
        self.assertEqual(plan["DRUMS - Extra Perc"], "DRUM BUS")
        self.assertEqual(plan["MUSIC - Verse Texture"], "MUSIC BUS - Vocal Pocket")
        self.assertEqual(plan["VOCAL - Hook Stack"], "VOCAL BUS")
        self.assertNotIn("REFERENCE / PRINT Alt", plan)

    def test_mix_profiles_cover_vocal_pocket_tracks(self):
        for track_name in [
            "MUSIC BUS - Vocal Pocket",
            "VOCAL - Lead Placeholder",
            "VOCAL BUS",
            "DRUMS - Kick",
            "DRUM BUS",
            "BASS BUS",
        ]:
            self.assertIn(track_name, EQ_PROFILES)
            self.assertIn("1 Frequency A", EQ_PROFILES[track_name])

    def test_eq8_low_cut_profiles_use_high_pass_filter_type(self):
        for track_name, profile in EQ_PROFILES.items():
            if "1 Filter Type A" in profile:
                self.assertEqual(
                    profile["1 Filter Type A"],
                    4,
                    f"{track_name} band 1 should be HP12, not LP/filter type 0",
                )

    def test_eq8_filter_type_normalization_uses_raw_enum(self):
        normalized, method = smart_normalize_parameter(
            "1 Filter Type A",
            4,
            "EQ Eight",
            0,
            7,
        )
        self.assertEqual(method, "enum_raw")
        self.assertEqual(normalized, 4.0)

    def test_drum_and_bass_bus_low_cuts_do_not_remove_body(self):
        self.assertLessEqual(EQ_PROFILES["DRUM BUS"]["1 Frequency A"], 35)
        self.assertLessEqual(EQ_PROFILES["BASS BUS"]["1 Frequency A"], 35)

    def test_music_bus_has_lower_presence_vocal_carve(self):
        music_bus_profile = EQ_PROFILES["MUSIC BUS - Vocal Pocket"]
        self.assertEqual(music_bus_profile["5 Filter Type A"], 7)
        self.assertGreaterEqual(music_bus_profile["5 Frequency A"], 1200)
        self.assertLessEqual(music_bus_profile["5 Frequency A"], 1800)
        self.assertLess(music_bus_profile["5 Gain A"], 0)

    def test_send_plan_gives_vocals_space(self):
        self.assertIn("VOCAL - Lead Placeholder", SEND_PLAN)
        self.assertIn(0, SEND_PLAN["VOCAL - Lead Placeholder"])
        self.assertIn(1, SEND_PLAN["VOCAL - Lead Placeholder"])

    def test_transition_texture_has_filtered_throw_send(self):
        throw_delay = next(track for track in self.template.return_tracks if track.name == "SEND - Throw Delay")
        profile = profile_for_device("SEND - Throw Delay", "delay")

        self.assertEqual(RETURN_SEND_TARGETS[3], "SEND - Throw Delay")
        self.assertEqual(PRIORITY_RETURN_DELAYS["SEND - Throw Delay"], ("Ping Pong Delay", "Delay", "Simple Delay"))
        self.assertEqual(SEND_PLAN["FX - Transitions Texture"], {3: 0.05})
        self.assertEqual(TRACK_DEVICE_PROFILE_OVERRIDES["SEND - Throw Delay"]["delay"], "throw_delay")
        self.assertEqual(profile, DEVICE_PROFILES["throw_delay"])
        self.assertEqual(profile["Feedback"], throw_delay.settings["feedback"] * 100)
        self.assertLessEqual(profile["Dry/Wet"], 18)

    def test_throw_delay_readback_helpers_handle_display_values(self):
        self.assertAlmostEqual(expected_delay_readback_value("Dry/Wet", 16), 0.16)
        self.assertAlmostEqual(expected_delay_readback_value("Feedback", 32), 0.32)
        self.assertEqual(expected_delay_readback_value("Time", 3), 3)
        self.assertTrue(should_report_delay_value_string("Time"))
        self.assertTrue(should_report_delay_value_string("Sync"))
        self.assertTrue(delay_display_value_matches("Feedback", 32, "32 %"))
        self.assertTrue(delay_display_value_matches("Dry/Wet", 16, "16 %"))
        self.assertTrue(delay_display_value_matches("Time", 3, "3/16"))
        self.assertFalse(delay_display_value_matches("Feedback", 32, "12 %"))

    def test_chords_have_low_filtered_long_hall_send(self):
        chords = next(track for track in self.template.tracks if track.name == "MUSIC - Chords")

        self.assertEqual(RETURN_SEND_TARGETS[2], "SEND - Long Hall")
        self.assertEqual(SEND_PLAN["MUSIC - Chords"], {2: 0.035})
        self.assertEqual(chords.settings["ambience_send"], "Low SEND - Long Hall for filtered harmonic depth behind vocals.")

    def test_long_hall_uses_dedicated_reverb_profile(self):
        long_hall = next(track for track in self.template.return_tracks if track.name == "SEND - Long Hall")
        profile = profile_for_device("SEND - Long Hall", "reverb")

        self.assertEqual(TRACK_DEVICE_PROFILE_OVERRIDES["SEND - Long Hall"]["reverb"], "long_hall_reverb")
        self.assertEqual(profile, DEVICE_PROFILES["long_hall_reverb"])
        self.assertEqual(profile["Decay Time"], long_hall.settings["decay_s"])
        self.assertEqual(profile["LowCut"], long_hall.settings["high_pass_hz"])
        self.assertEqual(profile["HighCut"], long_hall.settings["low_pass_hz"])
        self.assertGreater(profile["Decay Time"], DEVICE_PROFILES["reverb"]["Decay Time"])

    def test_drum_bus_has_parallel_compression_send(self):
        return_names = [track.name for track in self.template.return_tracks]
        parallel_return = next(track for track in self.template.return_tracks if track.name == "SEND - Parallel Drum Comp")

        self.assertEqual(return_names[4], "SEND - Parallel Drum Comp")
        self.assertEqual(RETURN_SEND_TARGETS[4], "SEND - Parallel Drum Comp")
        self.assertEqual(SEND_PLAN["DRUM BUS"], {4: 0.10})
        self.assertEqual(required_return_slot_count(), 5)
        self.assertEqual(parallel_return.settings["high_pass_hz"], 35)
        self.assertEqual(parallel_return.settings["low_pass_hz"], 7800)

    def test_all_named_send_targets_have_eq_profiles(self):
        return_names = {track.name for track in self.template.return_tracks}

        for return_name in RETURN_SEND_TARGETS.values():
            self.assertIn(return_name, return_names)
            self.assertIn(return_name, EQ_PROFILES)
            self.assertEqual(EQ_PROFILES[return_name]["1 Filter Type A"], 4)
            self.assertGreater(EQ_PROFILES[return_name]["1 Frequency A"], 0)

    def test_send_indices_target_short_plate_and_slap_delay(self):
        return_names = [track.name for track in self.template.return_tracks]
        for send_index, return_name in RETURN_SEND_TARGETS.items():
            self.assertEqual(return_names[send_index], return_name)

        self.assertEqual(RETURN_SEND_TARGETS[0], "SEND - Short Plate")
        self.assertEqual(RETURN_SEND_TARGETS[1], "SEND - Slap Delay")
        self.assertEqual(RETURN_SEND_TARGETS[2], "SEND - Long Hall")

    def test_reference_print_lane_is_muted_by_default(self):
        reference = next(track for track in self.template.tracks if track.name == "REFERENCE / PRINT")
        self.assertIs(reference.settings.get("muted"), True)

    def test_support_lanes_have_conservative_starter_pan(self):
        pan_by_track = {
            track.name: track.settings.get("starter_pan")
            for track in self.template.tracks
            if "starter_pan" in track.settings
        }

        self.assertEqual(pan_by_track["MUSIC - Keys Pad"], -0.10)
        self.assertEqual(pan_by_track["VOCAL - Doubles Adlibs"], 0.12)
        self.assertNotIn("DRUMS - Kick", pan_by_track)
        self.assertNotIn("BASS - Sub 808", pan_by_track)

    def test_track_settings_apply_starter_pan_defaults(self):
        tracks = [
            {"name": "MUSIC - Keys Pad", "color": 18, "settings": {"target_peak_db": -14, "starter_pan": -0.10}},
            {"name": "VOCAL - Lead Placeholder", "color": 27, "settings": {"target_peak_db": -10}},
        ]
        calls = []

        def fake_run_bridge(function, params=None, timeout=30):
            if function == "get_track_list":
                return {
                    "success": True,
                    "tracks": [
                        {"index": 0, "name": "MUSIC - Keys Pad"},
                        {"index": 1, "name": "VOCAL - Lead Placeholder"},
                    ],
                }
            calls.append((function, params))
            return {"success": True}

        with patch("scripts.improve_vocal_ready_template.run_bridge", side_effect=fake_run_bridge):
            changes = ensure_track_settings(tracks, dry_run=False)

        self.assertIn(("set_track_pan", {"track_index": 0, "pan": -0.10, "verify": False}), calls)
        self.assertFalse([call for call in calls if call[0] == "set_track_pan" and call[1]["track_index"] == 1])
        self.assertIn("Applied color, conservative volume, and starter pan defaults to template tracks", changes)

    def test_device_loading_prioritizes_route_enabling_midi_devices(self):
        tracks = [
            {"name": "DRUMS - Kick", "type": "midi", "devices": ["Drum Rack", "EQ Eight"]},
            {"name": "BASS - Sub 808", "type": "midi", "devices": ["Drift", "EQ Eight"]},
            {"name": "DRUM BUS", "type": "audio", "devices": ["EQ Eight"]},
        ]
        calls = []

        with patch("scripts.improve_vocal_ready_template.get_track_map", return_value={
            "DRUMS - Kick": 0,
            "BASS - Sub 808": 1,
            "DRUM BUS": 2,
        }), patch("scripts.improve_vocal_ready_template.get_devices", return_value=[]), patch(
            "scripts.improve_vocal_ready_template.load_first_available",
            side_effect=lambda track_index, desired, dry_run: calls.append((track_index, desired)) or f"Loaded {desired}",
        ):
            changes = ensure_devices(tracks, dry_run=False, max_device_loads=2)

        self.assertEqual(calls, [(0, "Drum Rack"), (1, "Drift")])
        self.assertIn("Stopped device loading at max_device_loads for this run", changes)

    def test_device_loading_prioritizes_bus_eq_before_source_effects(self):
        tracks = [
            {"name": "DRUMS - Kick", "type": "midi", "devices": ["Drum Rack", "EQ Eight", "Saturator"]},
            {"name": "BASS - Sub 808", "type": "midi", "devices": ["Drift", "EQ Eight"]},
            {"name": "DRUM BUS", "type": "audio", "devices": ["EQ Eight", "Glue Compressor"]},
            {"name": "BASS BUS", "type": "audio", "devices": ["EQ Eight", "Compressor"]},
            {"name": "MUSIC BUS - Vocal Pocket", "type": "audio", "devices": ["EQ Eight", "Compressor"]},
            {"name": "VOCAL BUS", "type": "audio", "devices": ["EQ Eight", "Compressor"]},
        ]
        calls = []

        def fake_get_devices(track_index):
            if track_index in (0, 1):
                return ["Drum Rack"] if track_index == 0 else ["Drift"]
            return []

        with patch("scripts.improve_vocal_ready_template.get_track_map", return_value={
            "DRUMS - Kick": 0,
            "BASS - Sub 808": 1,
            "DRUM BUS": 2,
            "BASS BUS": 3,
            "MUSIC BUS - Vocal Pocket": 4,
            "VOCAL BUS": 5,
        }), patch("scripts.improve_vocal_ready_template.get_devices", side_effect=fake_get_devices), patch(
            "scripts.improve_vocal_ready_template.load_first_available",
            side_effect=lambda track_index, desired, dry_run: calls.append((track_index, desired)) or f"Loaded {desired}",
        ):
            changes = ensure_devices(tracks, dry_run=False, max_device_loads=4)

        self.assertEqual(
            calls,
            [
                (3, "EQ Eight"),
                (2, "EQ Eight"),
                (4, "EQ Eight"),
                (5, "EQ Eight"),
            ],
        )
        self.assertIn("Stopped device loading at max_device_loads for this run", changes)

    def test_device_loading_prioritizes_bus_dynamics_after_bus_eq(self):
        tracks = [
            {"name": "DRUMS - Kick", "type": "midi", "devices": ["Drum Rack", "EQ Eight", "Saturator"]},
            {"name": "BASS - Sub 808", "type": "midi", "devices": ["Drift", "EQ Eight"]},
            {"name": "DRUM BUS", "type": "audio", "devices": ["EQ Eight", "Glue Compressor"]},
            {"name": "BASS BUS", "type": "audio", "devices": ["EQ Eight", "Compressor"]},
            {"name": "MUSIC BUS - Vocal Pocket", "type": "audio", "devices": ["EQ Eight", "Compressor"]},
            {"name": "VOCAL BUS", "type": "audio", "devices": ["EQ Eight", "Compressor"]},
        ]
        calls = []

        def fake_get_devices(track_index):
            if track_index == 0:
                return ["Drum Rack"]
            if track_index == 1:
                return ["Drift"]
            return []

        with patch("scripts.improve_vocal_ready_template.get_track_map", return_value={
            "DRUMS - Kick": 0,
            "BASS - Sub 808": 1,
            "DRUM BUS": 2,
            "BASS BUS": 3,
            "MUSIC BUS - Vocal Pocket": 4,
            "VOCAL BUS": 5,
        }), patch("scripts.improve_vocal_ready_template.get_devices", side_effect=fake_get_devices), patch(
            "scripts.improve_vocal_ready_template.load_first_available",
            side_effect=lambda track_index, desired, dry_run: calls.append((track_index, desired)) or f"Loaded {desired}",
        ):
            changes = ensure_devices(tracks, dry_run=False, max_device_loads=6)

        self.assertEqual(
            calls,
            [
                (3, "EQ Eight"),
                (2, "EQ Eight"),
                (4, "EQ Eight"),
                (5, "EQ Eight"),
                (2, "Glue Compressor"),
                (4, "Compressor"),
            ],
        )
        self.assertEqual(PRIORITY_BUS_DYNAMICS["DRUM BUS"], ("Glue Compressor",))
        self.assertEqual(PRIORITY_BUS_DYNAMICS["MUSIC BUS - Vocal Pocket"], ("Compressor",))
        self.assertIn("Stopped device loading at max_device_loads for this run", changes)

    def test_parameter_profiles_prioritize_buses(self):
        tracks = [{"name": track.name} for track in self.template.tracks]
        ordered_names = [track["name"] for track in parameter_profile_track_order(tracks)]
        self.assertEqual(
            ordered_names[:4],
            ["DRUM BUS", "BASS BUS", "MUSIC BUS - Vocal Pocket", "VOCAL BUS"],
        )

    def test_parameter_profiles_prioritize_bus_eq_devices(self):
        tracks = [{"name": track.name} for track in self.template.tracks]
        track_map = {track.name: index for index, track in enumerate(self.template.tracks)}
        devices_by_track = {track.name: list(track.devices) for track in self.template.tracks}
        ordered = parameter_profile_work_items(tracks, track_map, devices_by_track)
        ordered_track_devices = [(track["name"], device_name) for track, _, _, device_name in ordered]
        self.assertEqual(
            ordered_track_devices[:4],
            [
                ("DRUM BUS", "EQ Eight"),
                ("BASS BUS", "EQ Eight"),
                ("MUSIC BUS - Vocal Pocket", "EQ Eight"),
                ("VOCAL BUS", "EQ Eight"),
            ],
        )

    def test_eq_readback_compares_frequency_as_normalized_value(self):
        normalized = frequency_hz_to_normalized(95)
        self.assertGreater(normalized, 0)
        self.assertLess(normalized, 1)
        self.assertAlmostEqual(expected_readback_value("1 Frequency A", 95), normalized)
        self.assertEqual(expected_readback_value("1 Filter Type A", 4), 4)

    def test_bus_dynamics_readback_uses_normalized_compressor_values(self):
        threshold = expected_dynamics_readback_value("Compressor", "Threshold", -18)
        ratio = expected_dynamics_readback_value("Compressor", "Ratio", 2.2)
        dry_wet = expected_dynamics_readback_value("Compressor", "Dry/Wet", 70)

        self.assertGreater(threshold, 0)
        self.assertLess(threshold, 1)
        self.assertGreater(ratio, 0)
        self.assertLess(ratio, 1)
        self.assertAlmostEqual(dry_wet, 0.70)

    def test_glue_compressor_semantic_fallback_indices_match_local_ableton(self):
        mapping = ReliableParameterController.SEMANTIC_PARAM_MAPPINGS["Glue Compressor"]

        self.assertEqual(mapping["threshold"], ("Threshold", 1))
        self.assertEqual(mapping["range"], ("Range", 2))
        self.assertEqual(mapping["makeup"], ("Makeup", 3))
        self.assertEqual(mapping["attack"], ("Attack", 4))
        self.assertEqual(mapping["ratio"], ("Ratio", 5))
        self.assertEqual(mapping["release"], ("Release", 6))
        self.assertEqual(mapping["dry_wet"], ("Dry/Wet", 7))

    def test_glue_compressor_normalization_uses_local_discrete_controls(self):
        ratio, ratio_method = smart_normalize_parameter("Ratio", 2.0, "Glue Compressor", 0.0, 2.0)
        attack, attack_method = smart_normalize_parameter("Attack", 10, "Glue Compressor", 0.0, 6.0)
        release, release_method = smart_normalize_parameter("Release", 100, "Glue Compressor", 0.0, 6.0)
        threshold, threshold_method = smart_normalize_parameter("Threshold", -10, "Glue Compressor", -40.0, 0.0)

        self.assertEqual((ratio, ratio_method), (0.0, "glue_ratio_enum"))
        self.assertEqual((attack, attack_method), (5.0, "glue_attack_enum"))
        self.assertEqual((release, release_method), (0.0, "glue_release_enum"))
        self.assertEqual((threshold, threshold_method), (-10, "glue_threshold_raw_db"))
        self.assertEqual(expected_dynamics_readback_value("Glue Compressor", "Ratio", 2.0), 0.0)
        self.assertEqual(expected_dynamics_readback_value("Glue Compressor", "Attack", 10), 5.0)
        self.assertEqual(expected_dynamics_readback_value("Glue Compressor", "Release", 100), 0.0)
        self.assertEqual(expected_dynamics_readback_value("Glue Compressor", "Threshold", -10), -10)
        self.assertTrue(should_report_dynamics_value_string("Glue Compressor", "Ratio"))
        self.assertFalse(should_report_dynamics_value_string("Compressor", "Ratio"))
        self.assertTrue(glue_display_value_matches("Threshold", -10, "-10.0 dB"))
        self.assertTrue(glue_display_value_matches("Release", 100, ".1"))
        self.assertFalse(glue_display_value_matches("Threshold", -10, "0.00 dB"))

    def test_priority_bus_dynamics_device_resolves_loaded_fallback(self):
        devices = ["EQ Eight", "Solid Bus Comp", "Utility"]
        device_index, device_name = find_priority_bus_dynamics_device(devices, "Glue Compressor")

        self.assertEqual(device_index, 1)
        self.assertEqual(device_name, "Solid Bus Comp")

    def test_priority_return_delay_device_resolves_loaded_fallback(self):
        devices = ["EQ Eight", "Delay", "Utility"]
        device_index, device_name = find_priority_return_delay_device(
            devices,
            PRIORITY_RETURN_DELAYS["SEND - Throw Delay"],
        )

        self.assertEqual(device_index, 1)
        self.assertEqual(device_name, "Delay")

    def test_eq_readback_resolves_exact_eq_eight_with_required_params(self):
        devices = ["Utility", "EQ Eight", "Q10 Paragraphic EQ Stereo", "EQ Eight"]
        required = ["1 Filter Type A", "1 Frequency A"]

        with patch(
            "scripts.improve_vocal_ready_template.parameter_name_list_with_retry",
            side_effect=[
                (["Device On"], None),
                (["Device On", "1 Filter Type A", "1 Frequency A"], None),
            ],
        ):
            device_index, names, error = find_eq_eight_device_for_readback(7, devices, required)

        self.assertEqual(device_index, 3)
        self.assertIn("1 Frequency A", names)
        self.assertIsNone(error)

    def test_template_send_readback_verifies_planned_levels(self):
        tracks = [{"name": track.name} for track in self.template.tracks]
        track_map = {track["name"]: index for index, track in enumerate(tracks)}

        def fake_run_bridge(function, params=None, timeout=30):
            if function == "get_track_list":
                return {
                    "success": True,
                    "tracks": [
                        {"index": index, "name": name}
                        for name, index in track_map.items()
                    ],
                }
            if function == "get_track_send":
                track_name = tracks[params["track_index"]]["name"]
                return {"success": True, "level": SEND_PLAN[track_name][params["send_index"]]}
            raise AssertionError(function)

        with patch("scripts.improve_vocal_ready_template.run_bridge", side_effect=fake_run_bridge):
            changes = verify_send_readback_for_template_sends(tracks, dry_run=False)

        self.assertIn("Verified template send readback on VOCAL - Lead Placeholder", changes)
        self.assertFalse([change for change in changes if "mismatch" in change])

    def test_priority_bus_dynamics_readback_verifies_planned_profiles(self):
        tracks = [{"name": track.name} for track in self.template.tracks]
        track_map = {track["name"]: index for index, track in enumerate(tracks)}
        device_names = {
            "DRUM BUS": ["EQ Eight", "Glue Compressor"],
            "MUSIC BUS - Vocal Pocket": ["EQ Eight", "Compressor"],
        }
        parameter_names = {
            ("DRUM BUS", 1): ["Device On", "Threshold", "Ratio", "Attack", "Release", "Dry/Wet"],
            ("MUSIC BUS - Vocal Pocket", 1): ["Device On", "Threshold", "Ratio", "Attack", "Release", "Dry/Wet"],
        }

        def fake_run_bridge(function, params=None, timeout=30):
            if function == "get_track_list":
                return {
                    "success": True,
                    "tracks": [
                        {"index": index, "name": name}
                        for name, index in track_map.items()
                    ],
                }
            if function == "get_track_devices":
                track_name = tracks[params["track_index"]]["name"]
                return {"success": True, "devices": device_names.get(track_name, [])}
            if function == "get_device_parameters":
                track_name = tracks[params["track_index"]]["name"]
                return {"success": True, "names": parameter_names[(track_name, params["device_index"])]}
            if function == "get_device_parameter_value":
                track_name = tracks[params["track_index"]]["name"]
                device_name = device_names[track_name][params["device_index"]]
                param_name = parameter_names[(track_name, params["device_index"])][params["param_index"]]
                kind = "glue_compressor" if device_name == "Glue Compressor" else "compressor"
                profile_key = {
                    "DRUM BUS": {"glue_compressor": "glue_compressor"},
                    "MUSIC BUS - Vocal Pocket": {"compressor": "compressor"},
                }[track_name][kind]
                expected = {"Device On": 1.0}
                from scripts.improve_vocal_ready_template import DEVICE_PROFILES
                expected.update(DEVICE_PROFILES[profile_key])
                return {
                    "success": True,
                    "value": expected_dynamics_readback_value(device_name, param_name, expected[param_name]),
                }
            if function == "get_device_parameter_value_string":
                track_name = tracks[params["track_index"]]["name"]
                device_name = device_names[track_name][params["device_index"]]
                param_name = parameter_names[(track_name, params["device_index"])][params["param_index"]]
                if device_name == "Glue Compressor":
                    display_values = {
                        "Threshold": "-10.0 dB",
                        "Ratio": "2",
                        "Attack": "10",
                        "Release": ".1",
                        "Dry/Wet": "55 %",
                    }
                    return {"success": True, "value_string": display_values[param_name]}
                raise AssertionError("display readback should only be requested for Glue Compressor")
            raise AssertionError(function)

        with patch("scripts.improve_vocal_ready_template.run_bridge", side_effect=fake_run_bridge):
            changes = verify_priority_bus_dynamics_readback(tracks, dry_run=False)

        self.assertTrue(
            any(
                change.startswith("Verified bus dynamics readback on DRUM BUS: Glue Compressor")
                and "Ratio=2" in change
                for change in changes
            )
        )
        self.assertIn("Verified bus dynamics readback on MUSIC BUS - Vocal Pocket: Compressor", changes)
        self.assertFalse([change for change in changes if "mismatch" in change])

    def test_return_delay_readback_reports_display_timing_values(self):
        tracks = [{"name": track.name} for track in self.template.tracks] + [{"name": "SEND - Throw Delay"}]
        track_map = {track["name"]: index for index, track in enumerate(tracks)}
        device_names = {"SEND - Throw Delay": ["EQ Eight", "Delay", "Utility"]}
        parameter_names = {
            ("SEND - Throw Delay", 1): ["Device On", "Dry/Wet", "Feedback", "Time", "Sync"],
        }

        def fake_run_bridge(function, params=None, timeout=30):
            if function == "get_track_list":
                return {
                    "success": True,
                    "tracks": [
                        {"index": index, "name": name}
                        for name, index in track_map.items()
                    ],
                }
            if function == "get_track_devices":
                track_name = tracks[params["track_index"]]["name"]
                return {"success": True, "devices": device_names.get(track_name, [])}
            if function == "get_device_parameters":
                track_name = tracks[params["track_index"]]["name"]
                return {"success": True, "names": parameter_names[(track_name, params["device_index"])]}
            if function == "get_device_parameter_value":
                track_name = tracks[params["track_index"]]["name"]
                param_name = parameter_names[(track_name, params["device_index"])][params["param_index"]]
                expected = {"Device On": 1.0}
                expected.update(DEVICE_PROFILES["throw_delay"])
                return {"success": True, "value": expected_delay_readback_value(param_name, expected[param_name])}
            if function == "get_device_parameter_value_string":
                track_name = tracks[params["track_index"]]["name"]
                param_name = parameter_names[(track_name, params["device_index"])][params["param_index"]]
                display_values = {
                    "Dry/Wet": "16 %",
                    "Feedback": "32 %",
                    "Time": "3/16",
                    "Sync": "Sync",
                }
                return {"success": True, "value_string": display_values[param_name]}
            raise AssertionError(function)

        with patch("scripts.improve_vocal_ready_template.run_bridge", side_effect=fake_run_bridge):
            changes = verify_return_delay_readback_for_template_returns(tracks, dry_run=False)

        self.assertTrue(
            any(
                change.startswith("Verified return delay readback on SEND - Throw Delay: Delay")
                and "Time=3/16" in change
                and "Feedback=32 %" in change
                for change in changes
            )
        )
        self.assertFalse([change for change in changes if "mismatch" in change])

    def test_return_slot_probe_stops_at_first_unavailable_slot(self):
        def fake_run_bridge(function, params=None, timeout=30):
            if function == "get_track_send":
                return {"success": params["send_index"] < 2, "level": 0.0}
            raise AssertionError(function)

        with patch("scripts.improve_vocal_ready_template.run_bridge", side_effect=fake_run_bridge):
            self.assertEqual(probe_return_slot_count(track_index=0, max_slots=5), 2)

    def test_ensure_return_slots_creates_missing_send_slots(self):
        current_slots = {"count": 2}

        def fake_run_bridge(function, params=None, timeout=30):
            if function == "get_track_send":
                return {"success": params["send_index"] < current_slots["count"], "level": 0.0}
            if function == "create_return_track":
                current_slots["count"] += 1
                return {"success": True}
            raise AssertionError(function)

        with patch("scripts.improve_vocal_ready_template.run_bridge", side_effect=fake_run_bridge), patch(
            "scripts.improve_vocal_ready_template.time.sleep"
        ):
            changes = ensure_return_slots_for_send_plan({"DRUM BUS": 0}, dry_run=False)

        self.assertEqual(current_slots["count"], 5)
        self.assertIn("Created return slot 4 for SEND - Parallel Drum Comp", changes)

    def test_parallel_drum_send_gets_set_after_missing_return_slot_is_created(self):
        tracks = [{"name": "DRUM BUS"}]
        current_slots = {"count": 2}

        def fake_run_bridge(function, params=None, timeout=30):
            if function == "get_track_list":
                return {"success": True, "tracks": [{"index": 0, "name": "DRUM BUS"}]}
            if function == "get_track_send":
                return {"success": params["send_index"] < current_slots["count"], "level": 0.0}
            if function == "create_return_track":
                current_slots["count"] += 1
                return {"success": True}
            if function == "set_track_send":
                self.assertEqual(params["send_index"], 4)
                self.assertEqual(params["level"], 0.10)
                return {"success": True}
            raise AssertionError(function)

        with patch("scripts.improve_vocal_ready_template.get_track_map", return_value={"DRUM BUS": 0}), patch(
            "scripts.improve_vocal_ready_template.osc_request",
            side_effect=[[0, "Master"], [0, "Master"]],
        ), patch("scripts.improve_vocal_ready_template.osc_send"), patch(
            "scripts.improve_vocal_ready_template.run_bridge",
            side_effect=fake_run_bridge,
        ), patch(
            "scripts.improve_vocal_ready_template.time.sleep"
        ):
            changes = ensure_routing_and_sends(tracks, dry_run=False)

        self.assertEqual(current_slots["count"], 5)
        self.assertIn("Created return slot 4 for SEND - Parallel Drum Comp", changes)
        self.assertIn("Set send 4 on DRUM BUS to 0.1", changes)

    def test_template_routing_readback_verifies_supplemental_tracks(self):
        tracks = [{"name": track.name} for track in self.template.tracks]
        tracks.append({"name": "BASS - Boomin 808 Floor Audio"})
        track_map = {track["name"]: index for index, track in enumerate(tracks)}

        def fake_osc_request(address, args):
            self.assertEqual(address, "/live/track/get/output_routing_type")
            track_name = tracks[args[0]]["name"]
            if track_name == "BASS - Boomin 808 Floor Audio":
                return [args[0], "BASS BUS"]
            return [args[0], ROUTING_PLAN[track_name]]

        with patch("scripts.improve_vocal_ready_template.get_track_map", return_value=track_map), patch(
            "scripts.improve_vocal_ready_template.osc_request",
            side_effect=fake_osc_request,
        ):
            changes = verify_routing_readback_for_template_routes(tracks, dry_run=False)

        self.assertIn(
            "Verified template routing readback on BASS - Boomin 808 Floor Audio -> BASS BUS",
            changes,
        )
        self.assertFalse([change for change in changes if "mismatch" in change])

    def test_template_routing_readback_reports_mismatches(self):
        tracks = [{"name": track.name} for track in self.template.tracks]
        track_map = {track["name"]: index for index, track in enumerate(tracks)}

        with patch("scripts.improve_vocal_ready_template.get_track_map", return_value=track_map), patch(
            "scripts.improve_vocal_ready_template.osc_request",
            return_value=[0, "Master"],
        ):
            changes = verify_routing_readback_for_template_routes(tracks, dry_run=False)

        self.assertTrue(
            any("Template routing readback mismatch on DRUMS - Kick" in change for change in changes)
        )

    def test_template_send_readback_reports_mismatches(self):
        tracks = [{"name": track.name} for track in self.template.tracks]
        track_map = {track["name"]: index for index, track in enumerate(tracks)}

        def fake_run_bridge(function, params=None, timeout=30):
            if function == "get_track_list":
                return {
                    "success": True,
                    "tracks": [
                        {"index": index, "name": name}
                        for name, index in track_map.items()
                    ],
                }
            if function == "get_track_send":
                return {"success": True, "level": 0.0}
            raise AssertionError(function)

        with patch("scripts.improve_vocal_ready_template.run_bridge", side_effect=fake_run_bridge):
            changes = verify_send_readback_for_template_sends(tracks, dry_run=False)

        self.assertTrue(any("Template send readback mismatch on VOCAL - Lead Placeholder" in change for change in changes))


if __name__ == "__main__":
    unittest.main()
