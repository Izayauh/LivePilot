"""
Gemini Tool Definitions for Ableton Live Control

Defines all function declarations that Gemini can call to control Ableton.
These map to the functions in ableton_controls.py.
"""

from google.genai import types

# Import non-chatty pipeline tool
from pipeline.tool_definition import BUILD_CHAIN_PIPELINE_TOOL

# All tool definitions for Gemini function calling
ABLETON_TOOLS = [
    # ==================== PLAYBACK CONTROLS ====================
    types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name="play",
                description="Start playback in Ableton Live",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={},
                    required=[]
                )
            ),
            types.FunctionDeclaration(
                name="stop",
                description="Stop playback in Ableton Live",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={},
                    required=[]
                )
            ),
            types.FunctionDeclaration(
                name="continue_playback",
                description="Continue playback from the current position in Ableton Live",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={},
                    required=[]
                )
            ),
            types.FunctionDeclaration(
                name="start_recording",
                description="Start recording in Ableton Live",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={},
                    required=[]
                )
            ),
            types.FunctionDeclaration(
                name="stop_recording",
                description="Stop recording in Ableton Live",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={},
                    required=[]
                )
            ),
            types.FunctionDeclaration(
                name="toggle_metronome",
                description="Turn the metronome on or off in Ableton Live",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "state": types.Schema(
                            type="INTEGER",
                            description="1 to turn metronome on, 0 to turn it off"
                        )
                    },
                    required=["state"]
                )
            ),
            
            # ==================== TRANSPORT CONTROLS ====================
            types.FunctionDeclaration(
                name="set_tempo",
                description="Set the tempo/BPM in Ableton Live",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "bpm": types.Schema(
                            type="NUMBER",
                            description="Tempo in beats per minute (20-999)"
                        )
                    },
                    required=["bpm"]
                )
            ),
            types.FunctionDeclaration(
                name="set_position",
                description="Set the playback position in Ableton Live",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "beat": types.Schema(
                            type="NUMBER",
                            description="Position in beats"
                        )
                    },
                    required=["beat"]
                )
            ),
            types.FunctionDeclaration(
                name="set_loop",
                description="Enable or disable the loop in Ableton Live",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "enabled": types.Schema(
                            type="INTEGER",
                            description="1 to enable loop, 0 to disable"
                        )
                    },
                    required=["enabled"]
                )
            ),
            types.FunctionDeclaration(
                name="set_loop_start",
                description="Set the loop start position in Ableton Live",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "beat": types.Schema(
                            type="NUMBER",
                            description="Loop start position in beats"
                        )
                    },
                    required=["beat"]
                )
            ),
            types.FunctionDeclaration(
                name="set_loop_length",
                description="Set the loop length in Ableton Live",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "beats": types.Schema(
                            type="NUMBER",
                            description="Loop length in beats"
                        )
                    },
                    required=["beats"]
                )
            ),
            
            # ==================== TRACK CONTROLS ====================
            # Note: Track indices are 0-based (Track 1 in Ableton = index 0)
            types.FunctionDeclaration(
                name="mute_track",
                description="Mute or unmute a track in Ableton Live. Note: Track 1 in Ableton is index 0.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "track_index": types.Schema(
                            type="INTEGER",
                            description="Track index (0-based, so Track 1 = 0, Track 2 = 1, etc.)"
                        ),
                        "muted": types.Schema(
                            type="INTEGER",
                            description="1 to mute the track, 0 to unmute"
                        )
                    },
                    required=["track_index", "muted"]
                )
            ),
            types.FunctionDeclaration(
                name="solo_track",
                description="Solo or unsolo a track in Ableton Live. Note: Track 1 in Ableton is index 0.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "track_index": types.Schema(
                            type="INTEGER",
                            description="Track index (0-based, so Track 1 = 0, Track 2 = 1, etc.)"
                        ),
                        "soloed": types.Schema(
                            type="INTEGER",
                            description="1 to solo the track, 0 to unsolo"
                        )
                    },
                    required=["track_index", "soloed"]
                )
            ),
            types.FunctionDeclaration(
                name="arm_track",
                description="Arm or disarm a track for recording in Ableton Live. Note: Track 1 in Ableton is index 0.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "track_index": types.Schema(
                            type="INTEGER",
                            description="Track index (0-based, so Track 1 = 0, Track 2 = 1, etc.)"
                        ),
                        "armed": types.Schema(
                            type="INTEGER",
                            description="1 to arm the track, 0 to disarm"
                        )
                    },
                    required=["track_index", "armed"]
                )
            ),

            # ==================== TRACK STATUS QUERIES ====================
            types.FunctionDeclaration(
                name="get_track_mute",
                description="Get the mute status of a track. Returns whether the track is currently muted or not. Note: Track 1 in Ableton is index 0.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "track_index": types.Schema(
                            type="INTEGER",
                            description="Track index (0-based, so Track 1 = 0, Track 2 = 1, etc.)"
                        )
                    },
                    required=["track_index"]
                )
            ),
            types.FunctionDeclaration(
                name="get_track_solo",
                description="Get the solo status of a track. Returns whether the track is currently soloed or not. Note: Track 1 in Ableton is index 0.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "track_index": types.Schema(
                            type="INTEGER",
                            description="Track index (0-based, so Track 1 = 0, Track 2 = 1, etc.)"
                        )
                    },
                    required=["track_index"]
                )
            ),
            types.FunctionDeclaration(
                name="get_track_arm",
                description="Get the arm status of a track. Returns whether the track is currently armed for recording or not. Note: Track 1 in Ableton is index 0.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "track_index": types.Schema(
                            type="INTEGER",
                            description="Track index (0-based, so Track 1 = 0, Track 2 = 1, etc.)"
                        )
                    },
                    required=["track_index"]
                )
            ),
            types.FunctionDeclaration(
                name="get_track_status",
                description="Get the complete status of a track including mute, solo, and arm states. Returns all three states in one call. Note: Track 1 in Ableton is index 0.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "track_index": types.Schema(
                            type="INTEGER",
                            description="Track index (0-based, so Track 1 = 0, Track 2 = 1, etc.)"
                        )
                    },
                    required=["track_index"]
                )
            ),
            types.FunctionDeclaration(
                name="get_armed_tracks",
                description="Get a list of all currently armed tracks. This is useful for finding which track(s) are ready for recording. Returns track indices and names of armed tracks.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={},
                    required=[]
                )
            ),

            # ==================== TRACK REFERENCE RESOLUTION ====================
            types.FunctionDeclaration(
                name="find_track_by_name",
                description="Find track(s) by name using fuzzy matching. Use this when the user refers to a track by a partial name like 'vocal', 'the lead', 'drum track', etc. Returns matching tracks with their indices. ALWAYS use this tool before performing track operations when the user refers to a track by name.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "query": types.Schema(
                            type="STRING",
                            description="The track name or partial name to search for (e.g., 'vocal', 'lead', 'drums')"
                        )
                    },
                    required=["query"]
                )
            ),

            types.FunctionDeclaration(
                name="set_track_volume",
                description="Set the volume level of a track in Ableton Live. Note: Track 1 in Ableton is index 0.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "track_index": types.Schema(
                            type="INTEGER",
                            description="Track index (0-based, so Track 1 = 0, Track 2 = 1, etc.)"
                        ),
                        "volume": types.Schema(
                            type="NUMBER",
                            description="Volume level from 0.0 (silent) to 1.0 (full volume)"
                        )
                    },
                    required=["track_index", "volume"]
                )
            ),
            types.FunctionDeclaration(
                name="set_track_pan",
                description="Set the pan position of a track in Ableton Live. Note: Track 1 in Ableton is index 0.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "track_index": types.Schema(
                            type="INTEGER",
                            description="Track index (0-based, so Track 1 = 0, Track 2 = 1, etc.)"
                        ),
                        "pan": types.Schema(
                            type="NUMBER",
                            description="Pan value from -1.0 (hard left) to 1.0 (hard right), 0.0 is center"
                        )
                    },
                    required=["track_index", "pan"]
                )
            ),
            types.FunctionDeclaration(
                name="set_track_send",
                description="Set a send level on a track in Ableton Live. Note: Track 1 in Ableton is index 0.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "track_index": types.Schema(
                            type="INTEGER",
                            description="Track index (0-based, so Track 1 = 0, Track 2 = 1, etc.)"
                        ),
                        "send_index": types.Schema(
                            type="INTEGER",
                            description="Send index (0-based, so Send A = 0, Send B = 1, etc.)"
                        ),
                        "level": types.Schema(
                            type="NUMBER",
                            description="Send level from 0.0 to 1.0"
                        )
                    },
                    required=["track_index", "send_index", "level"]
                )
            ),
            
            # ==================== SCENE CONTROLS ====================
            types.FunctionDeclaration(
                name="fire_scene",
                description="Fire a scene in Ableton Live (launch all clips in the scene). Note: Scene 1 is index 0.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "scene_index": types.Schema(
                            type="INTEGER",
                            description="Scene index (0-based, so Scene 1 = 0, Scene 2 = 1, etc.)"
                        )
                    },
                    required=["scene_index"]
                )
            ),
            
            # ==================== CLIP CONTROLS ====================
            types.FunctionDeclaration(
                name="fire_clip",
                description="Fire (launch) a clip in Ableton Live. Note: Track 1 is index 0, Clip slot 1 is index 0.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "track_index": types.Schema(
                            type="INTEGER",
                            description="Track index (0-based, so Track 1 = 0)"
                        ),
                        "clip_index": types.Schema(
                            type="INTEGER",
                            description="Clip slot index (0-based, so first slot = 0)"
                        )
                    },
                    required=["track_index", "clip_index"]
                )
            ),
            types.FunctionDeclaration(
                name="stop_clip",
                description="Stop all clips on a track in Ableton Live. Note: Track 1 is index 0.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "track_index": types.Schema(
                            type="INTEGER",
                            description="Track index (0-based, so Track 1 = 0)"
                        )
                    },
                    required=["track_index"]
                )
            ),
            
            # ==================== TRACK MANAGEMENT ====================
            types.FunctionDeclaration(
                name="create_audio_track",
                description="Create a new audio track in Ableton Live. Use index -1 to add at end, or specify position (0 = first).",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "index": types.Schema(
                            type="INTEGER",
                            description="Position to insert track (-1 = end of list, 0 = first position, etc.)"
                        )
                    },
                    required=[]
                )
            ),
            types.FunctionDeclaration(
                name="create_midi_track",
                description="Create a new MIDI track in Ableton Live. Use index -1 to add at end, or specify position (0 = first).",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "index": types.Schema(
                            type="INTEGER",
                            description="Position to insert track (-1 = end of list, 0 = first position, etc.)"
                        )
                    },
                    required=[]
                )
            ),
            types.FunctionDeclaration(
                name="create_return_track",
                description="Create a new return track in Ableton Live for effects sends.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={},
                    required=[]
                )
            ),
            types.FunctionDeclaration(
                name="delete_track",
                description="Delete a track in Ableton Live. Note: Track 1 is index 0.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "track_index": types.Schema(
                            type="INTEGER",
                            description="Track index (0-based, so Track 1 = 0, Track 2 = 1, etc.)"
                        )
                    },
                    required=["track_index"]
                )
            ),
            types.FunctionDeclaration(
                name="delete_return_track",
                description="Delete a return track in Ableton Live. Note: Return A is index 0.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "track_index": types.Schema(
                            type="INTEGER",
                            description="Return track index (0-based, so Return A = 0, Return B = 1, etc.)"
                        )
                    },
                    required=["track_index"]
                )
            ),
            types.FunctionDeclaration(
                name="duplicate_track",
                description="Duplicate/copy a track in Ableton Live. Note: Track 1 is index 0.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "track_index": types.Schema(
                            type="INTEGER",
                            description="Track index (0-based, so Track 1 = 0, Track 2 = 1, etc.)"
                        )
                    },
                    required=["track_index"]
                )
            ),
            types.FunctionDeclaration(
                name="set_track_name",
                description="Rename a track in Ableton Live. Note: Track 1 is index 0.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "track_index": types.Schema(
                            type="INTEGER",
                            description="Track index (0-based, so Track 1 = 0, Track 2 = 1, etc.)"
                        ),
                        "name": types.Schema(
                            type="STRING",
                            description="New name for the track"
                        )
                    },
                    required=["track_index", "name"]
                )
            ),
            types.FunctionDeclaration(
                name="set_track_color",
                description="Set the color of a track in Ableton Live. Note: Track 1 is index 0.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "track_index": types.Schema(
                            type="INTEGER",
                            description="Track index (0-based, so Track 1 = 0, Track 2 = 1, etc.)"
                        ),
                        "color_index": types.Schema(
                            type="INTEGER",
                            description="Color index from Ableton's palette (0-69)"
                        )
                    },
                    required=["track_index", "color_index"]
                )
            ),
            
            # ==================== TRACK QUERY CONTROLS ====================
            types.FunctionDeclaration(
                name="get_track_list",
                description="Get a list of all tracks with their names and indices. CRITICAL: Use this BEFORE any track operation to confirm which track the user is referring to.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={},
                    required=[]
                )
            ),

            # ==================== DEVICE QUERY CONTROLS ====================
            types.FunctionDeclaration(
                name="get_num_devices",
                description="Get the number of devices/plugins on a track. Note: Track 1 is index 0.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "track_index": types.Schema(
                            type="INTEGER",
                            description="Track index (0-based, so Track 1 = 0, Track 2 = 1, etc.)"
                        )
                    },
                    required=["track_index"]
                )
            ),
            types.FunctionDeclaration(
                name="get_track_devices",
                description="Get all device/plugin names on a track. Note: Track 1 is index 0.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "track_index": types.Schema(
                            type="INTEGER",
                            description="Track index (0-based, so Track 1 = 0, Track 2 = 1, etc.)"
                        )
                    },
                    required=["track_index"]
                )
            ),
            types.FunctionDeclaration(
                name="get_device_name",
                description="Get a specific device's name. Note: Track 1 is index 0, Device 1 is index 0.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "track_index": types.Schema(
                            type="INTEGER",
                            description="Track index (0-based, so Track 1 = 0)"
                        ),
                        "device_index": types.Schema(
                            type="INTEGER",
                            description="Device index on track (0-based, so first device = 0)"
                        )
                    },
                    required=["track_index", "device_index"]
                )
            ),
            types.FunctionDeclaration(
                name="get_device_class_name",
                description="Get a device's class name (e.g., Reverb, Compressor, Operator). Note: Track 1 is index 0.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "track_index": types.Schema(
                            type="INTEGER",
                            description="Track index (0-based, so Track 1 = 0)"
                        ),
                        "device_index": types.Schema(
                            type="INTEGER",
                            description="Device index on track (0-based, so first device = 0)"
                        )
                    },
                    required=["track_index", "device_index"]
                )
            ),
            types.FunctionDeclaration(
                name="get_device_parameters",
                description="Get all parameter names for a device. Note: Track 1 is index 0, Device 1 is index 0.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "track_index": types.Schema(
                            type="INTEGER",
                            description="Track index (0-based, so Track 1 = 0)"
                        ),
                        "device_index": types.Schema(
                            type="INTEGER",
                            description="Device index on track (0-based, so first device = 0)"
                        )
                    },
                    required=["track_index", "device_index"]
                )
            ),
            types.FunctionDeclaration(
                name="get_device_parameter_value",
                description="Get a specific parameter value from a device. Note: Track 1 is index 0, Device 1 is index 0, Parameter 1 is index 0.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "track_index": types.Schema(
                            type="INTEGER",
                            description="Track index (0-based, so Track 1 = 0)"
                        ),
                        "device_index": types.Schema(
                            type="INTEGER",
                            description="Device index on track (0-based, so first device = 0)"
                        ),
                        "param_index": types.Schema(
                            type="INTEGER",
                            description="Parameter index (0-based, so first parameter = 0)"
                        )
                    },
                    required=["track_index", "device_index", "param_index"]
                )
            ),
            
            # ==================== DEVICE PARAMETER CONTROLS ====================
            types.FunctionDeclaration(
                name="set_device_parameter",
                description="Set a specific parameter value on a device. Note: Track 1 is index 0, Device 1 is index 0, Parameter 1 is index 0.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "track_index": types.Schema(
                            type="INTEGER",
                            description="Track index (0-based, so Track 1 = 0)"
                        ),
                        "device_index": types.Schema(
                            type="INTEGER",
                            description="Device index on track (0-based, so first device = 0)"
                        ),
                        "param_index": types.Schema(
                            type="INTEGER",
                            description="Parameter index (0-based, so first parameter = 0)"
                        ),
                        "value": types.Schema(
                            type="NUMBER",
                            description="Parameter value (typically 0.0 to 1.0 for most parameters)"
                        )
                    },
                    required=["track_index", "device_index", "param_index", "value"]
                )
            ),
            types.FunctionDeclaration(
                name="set_device_enabled",
                description="Enable or bypass a device/plugin. Note: Track 1 is index 0, Device 1 is index 0.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "track_index": types.Schema(
                            type="INTEGER",
                            description="Track index (0-based, so Track 1 = 0)"
                        ),
                        "device_index": types.Schema(
                            type="INTEGER",
                            description="Device index on track (0-based, so first device = 0)"
                        ),
                        "enabled": types.Schema(
                            type="INTEGER",
                            description="1 to enable device, 0 to bypass"
                        )
                    },
                    required=["track_index", "device_index", "enabled"]
                )
            ),
            types.FunctionDeclaration(
                name="delete_device",
                description="Delete/remove a specific device/plugin FROM a track. This removes the device from the track's device chain, NOT the track itself. Use this when the user says 'delete the compressor', 'remove the plugin', 'delete all devices', etc. Note: Track 1 is index 0, Device 1 is index 0.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "track_index": types.Schema(
                            type="INTEGER",
                            description="Track index (0-based, so Track 1 = 0)"
                        ),
                        "device_index": types.Schema(
                            type="INTEGER",
                            description="Device index on track (0-based, so first device = 0). Use get_track_devices first to find device indices."
                        )
                    },
                    required=["track_index", "device_index"]
                )
            ),

            # ==================== PLUGIN MANAGEMENT ====================
            types.FunctionDeclaration(
                name="add_plugin_to_track",
                description="Add a plugin/device to a track by name. Searches for the best matching plugin from available VSTs and Ableton native devices. Note: Track 1 is index 0.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "track_index": types.Schema(
                            type="INTEGER",
                            description="Track index (0-based, so Track 1 = 0, Track 2 = 1, etc.)"
                        ),
                        "plugin_name": types.Schema(
                            type="STRING",
                            description="Name of the plugin to add (e.g., 'EQ Eight', 'FabFilter Pro-Q 3', 'Compressor')"
                        ),
                        "position": types.Schema(
                            type="INTEGER",
                            description="Position in device chain (-1 = end, 0 = first). Default is -1 (add at end)."
                        )
                    },
                    required=["track_index", "plugin_name"]
                )
            ),
            types.FunctionDeclaration(
                name="create_plugin_chain",
                description="Research and create a plugin chain based on an artist or style. Searches for production techniques and matches to available plugins. Note: Track 1 is index 0.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "track_index": types.Schema(
                            type="INTEGER",
                            description="Track index (0-based, so Track 1 = 0, Track 2 = 1, etc.)"
                        ),
                        "artist_or_style": types.Schema(
                            type="STRING",
                            description="Artist name or style to research (e.g., 'Billie Eilish', 'The Weeknd', 'modern pop', 'hip hop')"
                        ),
                        "track_type": types.Schema(
                            type="STRING",
                            description="Type of track: 'vocal', 'drums', 'bass', 'guitar', 'synth', 'master'. Default is 'vocal'."
                        )
                    },
                    required=["track_index", "artist_or_style"]
                )
            ),
            types.FunctionDeclaration(
                name="get_available_plugins",
                description="Get a list of all available plugins and devices. Can be filtered by category.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "category": types.Schema(
                            type="STRING",
                            description="Optional category filter: 'eq', 'compressor', 'reverb', 'delay', 'distortion', 'modulation', 'dynamics', 'utility'. Leave empty for all plugins."
                        )
                    },
                    required=[]
                )
            ),
            types.FunctionDeclaration(
                name="find_plugin",
                description="Search for a specific plugin by name with fuzzy matching. Returns the best match from available plugins.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "query": types.Schema(
                            type="STRING",
                            description="Plugin name or partial match to search for (e.g., 'Pro-Q', 'SSL', 'compressor')"
                        ),
                        "category": types.Schema(
                            type="STRING",
                            description="Optional category filter to narrow results"
                        )
                    },
                    required=["query"]
                )
            ),
            types.FunctionDeclaration(
                name="load_preset_chain",
                description="Load a preset plugin chain onto a track. Available presets: 'basic', 'full', 'minimal'.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "track_index": types.Schema(
                            type="INTEGER",
                            description="Track index (0-based, so Track 1 = 0)"
                        ),
                        "preset_name": types.Schema(
                            type="STRING",
                            description="Preset name: 'basic', 'full', or 'minimal'"
                        ),
                        "track_type": types.Schema(
                            type="STRING",
                            description="Track type: 'vocal', 'drums', 'bass', 'master'. Default is 'vocal'."
                        )
                    },
                    required=["track_index", "preset_name"]
                )
            ),
            types.FunctionDeclaration(
                name="refresh_plugin_list",
                description="Refresh the list of available plugins by re-scanning Ableton's browser. Use this if new plugins were installed.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={},
                    required=[]
                )
            ),
            
            # ==================== AUDIO ENGINEER INTELLIGENCE ====================
            types.FunctionDeclaration(
                name="consult_audio_engineer",
                description="Ask the AI audio engineer agent for production advice, technique recommendations, or workflow guidance. Use this for questions about mixing, mastering, EQ, compression, or any audio production topic.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "question": types.Schema(
                            type="STRING",
                            description="Question or production challenge to ask the audio engineer (e.g., 'How do I make my drums punch through the mix?', 'What EQ settings for vocals?')"
                        ),
                        "track_type": types.Schema(
                            type="STRING",
                            description="Optional track type for context: 'vocal', 'drums', 'bass', 'guitar', 'synth', 'master'"
                        )
                    },
                    required=["question"]
                )
            ),
            types.FunctionDeclaration(
                name="get_parameter_info",
                description="Get detailed information about what a device parameter does, including audio engineering context, typical ranges, and common settings.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "device_name": types.Schema(
                            type="STRING",
                            description="Name of the device (e.g., 'EQ Eight', 'Compressor', 'Reverb')"
                        ),
                        "param_index": types.Schema(
                            type="INTEGER",
                            description="Parameter index (0-based)"
                        )
                    },
                    required=["device_name", "param_index"]
                )
            ),
            types.FunctionDeclaration(
                name="suggest_device_settings",
                description="Get suggested parameter settings for a device based on the intended purpose and track type. Returns specific values and explanations.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "device_name": types.Schema(
                            type="STRING",
                            description="Name of the device (e.g., 'EQ Eight', 'Compressor', 'Reverb')"
                        ),
                        "purpose": types.Schema(
                            type="STRING",
                            description="What you're trying to achieve (e.g., 'high_pass', 'cut_mud', 'add_warmth', 'vocal_control', 'punch', 'glue')"
                        ),
                        "track_type": types.Schema(
                            type="STRING",
                            description="Type of track: 'vocal', 'drums', 'bass', 'guitar', 'synth', 'master'. Default is 'vocal'."
                        )
                    },
                    required=["device_name", "purpose"]
                )
            ),
            types.FunctionDeclaration(
                name="apply_audio_intent",
                description="Analyze a natural language audio production request and suggest the appropriate device and settings. Use for requests like 'make it brighter', 'remove the mud', 'add warmth', etc.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "intent": types.Schema(
                            type="STRING",
                            description="Natural language description of what you want (e.g., 'make the vocal brighter', 'remove mud', 'add punch to the drums')"
                        ),
                        "track_type": types.Schema(
                            type="STRING",
                            description="Type of track: 'vocal', 'drums', 'bass', 'guitar', 'synth', 'master'. Default is 'vocal'."
                        ),
                        "track_index": types.Schema(
                            type="INTEGER",
                            description="Optional track index to apply the settings to (0-based). If provided, will apply the suggested settings."
                        ),
                        "device_index": types.Schema(
                            type="INTEGER",
                            description="Optional device index on the track (0-based). If provided with track_index, will apply settings to this device."
                        )
                    },
                    required=["intent"]
                )
            ),
            types.FunctionDeclaration(
                name="explain_adjustment",
                description="Get an audio engineering explanation for a parameter adjustment. Helps understand why a certain change was made or should be made.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "device_name": types.Schema(
                            type="STRING",
                            description="Name of the device"
                        ),
                        "param_index": types.Schema(
                            type="INTEGER",
                            description="Parameter index (0-based)"
                        ),
                        "value": types.Schema(
                            type="NUMBER",
                            description="The parameter value being set"
                        ),
                        "track_type": types.Schema(
                            type="STRING",
                            description="Optional track type for context"
                        )
                    },
                    required=["device_name", "param_index", "value"]
                )
            ),
            
            # ==================== RESEARCH-DRIVEN VOCAL CHAINS ====================
            types.FunctionDeclaration(
                name="lookup_song_chain",
                description="Search the local song database for a vocal chain and return chain_spec data for a song section.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "song_title": types.Schema(
                            type="STRING",
                            description="Song title to search for"
                        ),
                        "artist": types.Schema(
                            type="STRING",
                            description="Artist name"
                        ),
                        "section": types.Schema(
                            type="STRING",
                            description="Song section: verse, chorus, background_vocals, adlibs",
                            enum=["verse", "chorus", "background_vocals", "adlibs"]
                        )
                    },
                    required=["song_title"]
                )
            ),
            types.FunctionDeclaration(
                name="explain_parameter",
                description="Explain why a specific parameter was set, grounded in local param_why data from the active chain.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "plugin_name": types.Schema(
                            type="STRING",
                            description="Plugin name in active chain"
                        ),
                        "param_name": types.Schema(
                            type="STRING",
                            description="Parameter name to explain"
                        )
                    },
                    required=["plugin_name", "param_name"]
                )
            ),
            types.FunctionDeclaration(
                name="list_library",
                description="List all songs available in the local chain library.",
                parameters=types.Schema(type="OBJECT", properties={}, required=[])
            ),
            types.FunctionDeclaration(
                name="search_library_by_vibe",
                description="Search local song library by vibe/style tags.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "tags": types.Schema(
                            type="ARRAY",
                            items=types.Schema(type="STRING"),
                            description="List of vibe/style tags"
                        )
                    },
                    required=["tags"]
                )
            ),
            types.FunctionDeclaration(
                name="research_vocal_chain",
                description="Research vocal chain settings from YouTube tutorials and web articles. Uses AI to extract specific plugin settings from online sources. Returns a ChainSpec with devices and parameters. Note: This is research only - use create_plugin_chain to actually load devices.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "query": types.Schema(
                            type="STRING",
                            description="Search query describing the vocal sound (e.g., 'Kanye Runaway vocal', 'Billie Eilish whisper vocal', 'aggressive hip hop vocal')"
                        ),
                        "use_youtube": types.Schema(
                            type="BOOLEAN",
                            description="Whether to search YouTube tutorials. Default is True."
                        ),
                        "use_web": types.Schema(
                            type="BOOLEAN",
                            description="Whether to search web articles. Default is True."
                        ),
                        "max_sources": types.Schema(
                            type="INTEGER",
                            description="Maximum number of sources to analyze per type. Default is 3."
                        ),
                        "budget_mode": types.Schema(
                            type="STRING",
                            description="Cost/quality mode: 'cheap' (lowest cost), 'balanced' (default), or 'deep' (highest quality)."
                        ),
                        "prefer_cache": types.Schema(
                            type="BOOLEAN",
                            description="Reuse recent cached research when available. Default is True."
                        ),
                        "cache_max_age_days": types.Schema(
                            type="INTEGER",
                            description="Maximum age of cached research in days. Default is 14."
                        ),
                        "max_total_llm_calls": types.Schema(
                            type="INTEGER",
                            description="Hard cap for total LLM calls during this research request."
                        )
                    },
                    required=["query"]
                )
            ),
            types.FunctionDeclaration(
                name="apply_research_chain",
                description="Apply a previously-researched vocal chain to a track. Call this AFTER research_vocal_chain returns results and the user confirms the proposed chain. Takes the chain_spec from the research result and loads matched plugins onto the track with parameter configuration.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "track_index": types.Schema(
                            type="INTEGER",
                            description="Track index (0-based, so Track 1 = 0, Track 2 = 1, etc.)"
                        ),
                        "chain_spec": types.Schema(
                            type="OBJECT",
                            description="The chain_spec object returned by research_vocal_chain. Pass the entire chain_spec dict from the research result."
                        ),
                        "track_type": types.Schema(
                            type="STRING",
                            description="Type of track: 'vocal', 'drums', 'bass', 'guitar', 'synth', 'master'. Default is 'vocal'."
                        )
                    },
                    required=["track_index", "chain_spec"]
                )
            ),
            types.FunctionDeclaration(
                name="apply_basic_vocal_parameters",
                description="Anti-stall fallback: apply a safe baseline vocal parameter profile to common stock devices already loaded on a track (EQ Eight, Compressor, Glue Compressor, Reverb, Limiter, Multiband Dynamics). Use this when parameter-resolution loops or index lookup fails.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "track_index": types.Schema(
                            type="INTEGER",
                            description="Track index (0-based, so Track 1 = 0, Track 2 = 1, etc.)"
                        ),
                        "voice_profile": types.Schema(
                            type="STRING",
                            description="Voice profile preset. Default 'male_tenor'."
                        )
                    },
                    required=["track_index"]
                )
            ),
            types.FunctionDeclaration(
                name="get_plugin_semantic_info",
                description="Get semantic information about an Ableton plugin from the knowledge base. Includes parameter descriptions, typical ranges, and common vocal settings.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "plugin_name": types.Schema(
                            type="STRING",
                            description="Name of the plugin (e.g., 'EQ Eight', 'Compressor', 'Reverb', 'Saturator')"
                        ),
                        "use_case": types.Schema(
                            type="STRING",
                            description="Optional use case for typical range recommendations (e.g., 'vocal_cut_mud', 'aggressive_vocal', 'gentle_compression')"
                        )
                    },
                    required=["plugin_name"]
                )
            ),
            types.FunctionDeclaration(
                name="find_parameters_for_intent",
                description="Find plugin parameters that match a semantic intent. Useful for discovering which parameters to adjust for a specific goal.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "plugin_name": types.Schema(
                            type="STRING",
                            description="Name of the plugin (e.g., 'EQ Eight', 'Compressor')"
                        ),
                        "intent": types.Schema(
                            type="STRING",
                            description="What you want to achieve (e.g., 'cut_mud', 'add_presence', 'threshold', 'warmth')"
                        )
                    },
                    required=["plugin_name", "intent"]
                )
            ),
            types.FunctionDeclaration(
                name="get_signal_flow_recommendation",
                description="Get recommended plugin order for a vocal chain type. Returns optimal signal flow based on production best practices.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "chain_type": types.Schema(
                            type="STRING",
                            description="Type of chain: 'standard_vocal_chain', 'aggressive_vocal_chain', 'intimate_vocal_chain'"
                        )
                    },
                    required=["chain_type"]
                )
            ),

            # ==================== MACRO SYSTEM ====================
            types.FunctionDeclaration(
                name="execute_macro",
                description="Execute a predefined macro (reusable command sequence). Available macros include: 'Solo Check All', 'Mute All', 'Unmute All', 'Reset Mix', 'Playback Start', 'Quick Vocal Setup', 'Quick Drum Bus', 'Mastering Chain', 'A/B Reference', 'Bounce Check'",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "macro_name": types.Schema(
                            type="STRING",
                            description="Name of the macro to execute"
                        )
                    },
                    required=["macro_name"]
                )
            ),
            types.FunctionDeclaration(
                name="list_macros",
                description="List all available macros",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={},
                    required=[]
                )
            ),

            # ==================== UNDO SYSTEM ====================
            types.FunctionDeclaration(
                name="undo_last_action",
                description="Undo the last action that was performed. Supports undoing mute/solo/arm toggles, volume/pan changes, and tempo changes.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={},
                    required=[]
                )
            ),
            types.FunctionDeclaration(
                name="get_undo_history",
                description="Get a list of recent actions that can be undone",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "limit": types.Schema(
                            type="INTEGER",
                            description="Maximum number of actions to return (default 10)"
                        )
                    },
                    required=[]
                )
            ),
        ]
    ),
    # ==================== STORAGE MANAGEMENT ====================
    types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name="clean_storage",
                description="Clean up accumulated files (screenshots, logs, cache, crash reports). Use category='all' to clean everything, or specify a category. Set dry_run=true to preview without deleting.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "category": types.Schema(
                            type="STRING",
                            description="Category to clean: 'all', 'screenshots', 'logs', 'cache', 'crash_reports'"
                        ),
                        "dry_run": types.Schema(
                            type="BOOLEAN",
                            description="If true, preview what would be deleted without actually deleting"
                        )
                    },
                    required=[]
                )
            ),
        ]
    ),
    # ==================== NON-CHATTY CHAIN PIPELINE ====================
    types.Tool(
        function_declarations=[
            BUILD_CHAIN_PIPELINE_TOOL,
        ]
    ),
]


def get_function_name_list():
    """
    Get a list of all available function names
    
    Returns:
        list: List of function names that Jarvis can call
    """
    functions = []
    for tool in ABLETON_TOOLS:
        for func in tool.function_declarations:
            functions.append(func.name)
    return functions


# Print available functions for debugging
if __name__ == "__main__":
    print("=== Available Ableton Control Functions ===")
    for func_name in get_function_name_list():
        print(f"  - {func_name}")
    print(f"\nTotal: {len(get_function_name_list())} functions")

