"""
Gemini FunctionDeclaration for the build_chain_pipeline tool.

This defines the tool schema that Gemini uses to generate a complete
chain execution plan in a single function_call. The schema mirrors
pipeline.schemas.ChainPipelinePlan.
"""

from google.genai import types


BUILD_CHAIN_PIPELINE_TOOL = types.FunctionDeclaration(
    name="build_chain_pipeline",
    description=(
        "Build and execute a complete plugin/device chain on a track in a SINGLE call. "
        "Provide the target track, ordered list of devices with ALL their parameters, "
        "and all settings upfront. The system will load each device, set all parameters "
        "with verification, and return a complete result. "
        "This replaces multiple add_plugin_to_track + set_device_parameter calls. "
        "Parameter names use semantic keys matching SEMANTIC_PARAM_MAPPINGS: "
        "For EQ Eight: band1_freq_hz, band1_gain_db, band1_q, band1_type, "
        "band2_freq_hz, band2_gain_db, band2_q, band2_type, "
        "band3_freq_hz, band3_gain_db, band3_q, band3_type, "
        "band4_freq_hz, band4_gain_db, band4_q, band4_type. "
        "For Compressor: threshold_db, ratio, attack_ms, release_ms, "
        "output_gain_db, knee_db, dry_wet_pct. "
        "For Glue Compressor: threshold_db, ratio, attack_ms, release_ms, "
        "makeup_db, dry_wet_pct. "
        "For Saturator: drive_db, output_db, dry_wet_pct, type. "
        "For Reverb: decay_time_ms, predelay_ms, dry_wet_pct, room_size, "
        "high_cut_hz, low_cut_hz. "
        "For Delay: delay_time_ms, feedback_pct, dry_wet_pct, "
        "filter_freq_hz, filter_on. "
        "For Utility: gain_db, pan, width_pct, mute. "
        "Values are in human-readable units: Hz for frequency, dB for "
        "gain/threshold, ms for attack/release/decay, ratio for compression "
        "ratio (e.g. 4.0 means 4:1), percentage 0-100 for dry/wet."
    ),
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "track_index": types.Schema(
                type="INTEGER",
                description="0-based track index (Track 1 = 0, Track 2 = 1)"
            ),
            "devices": types.Schema(
                type="ARRAY",
                description="Ordered list of devices to load (signal chain order)",
                items=types.Schema(
                    type="OBJECT",
                    properties={
                        "name": types.Schema(
                            type="STRING",
                            description=(
                                "Exact device name: 'EQ Eight', 'Compressor', "
                                "'Glue Compressor', 'Reverb', 'Delay', 'Saturator', "
                                "'Limiter', 'Utility', 'Multiband Dynamics', 'Gate', "
                                "'Auto Filter', 'Echo', 'Pedal', 'Overdrive', "
                                "'Chorus-Ensemble', 'Phaser-Flanger', 'Drum Buss'"
                            )
                        ),
                        "purpose": types.Schema(
                            type="STRING",
                            description=(
                                "What this device does in the chain (e.g., "
                                "'high_pass', 'dynamics', 'de_essing', 'warmth', "
                                "'presence_boost', 'space', 'depth')"
                            )
                        ),
                        "params": types.Schema(
                            type="ARRAY",
                            description="Parameters to set (semantic names + human-readable values)",
                            items=types.Schema(
                                type="OBJECT",
                                properties={
                                    "name": types.Schema(
                                        type="STRING",
                                        description=(
                                            "Semantic param key: threshold_db, ratio, "
                                            "attack_ms, release_ms, band1_freq_hz, "
                                            "band1_gain_db, band1_q, band1_type, "
                                            "band2_freq_hz, band2_gain_db, band2_q, "
                                            "band2_type, band3_freq_hz, band3_gain_db, "
                                            "band3_q, band3_type, band4_freq_hz, "
                                            "band4_gain_db, band4_q, band4_type, "
                                            "dry_wet_pct, drive_db, output_db, "
                                            "decay_time_ms, predelay_ms, room_size, "
                                            "high_cut_hz, low_cut_hz, output_gain_db, "
                                            "knee_db, makeup_db, delay_time_ms, "
                                            "feedback_pct, filter_freq_hz, filter_on, "
                                            "gain_db, pan, width_pct, mute"
                                        )
                                    ),
                                    "value": types.Schema(
                                        type="NUMBER",
                                        description="Human-readable value (Hz, dB, ms, ratio, pct)"
                                    ),
                                },
                                required=["name", "value"]
                            )
                        ),
                        "enabled": types.Schema(
                            type="BOOLEAN",
                            description="True=active, False=bypassed. Default True."
                        ),
                        "fallback": types.Schema(
                            type="STRING",
                            description="Alternative device if primary unavailable"
                        ),
                    },
                    required=["name"]
                )
            ),
            "description": types.Schema(
                type="STRING",
                description="What this chain achieves (e.g., 'Kanye Donda vocal chain')"
            ),
            "clear_existing": types.Schema(
                type="BOOLEAN",
                description="Remove existing devices first. Default false."
            ),
            "dry_run": types.Schema(
                type="BOOLEAN",
                description="Validate without executing. Default false."
            ),
        },
        required=["track_index", "devices"]
    )
)
