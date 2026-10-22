"""rack_builder: a track's chain in a saved .als becomes a rack .adg with macro mappings Live 11.3 reads."""

import gzip
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from livepilot_tools import rack_builder
from livepilot_tools.rack_builder import RackError, build_rack


def _param(tag, manual, lo=0, hi=1, keymidi=False):
    km = ('<KeyMidi><PersistentKeyString Value="" /><IsNote Value="false" /><Channel Value="3" />'
          '<NoteOrController Value="9" /></KeyMidi>') if keymidi else ""
    return (f'<{tag}><LomId Value="0" />{km}<Manual Value="{manual}" />'
            f'<MidiControllerRange><Min Value="{lo}" /><Max Value="{hi}" /></MidiControllerRange>'
            f'<AutomationTarget Id="7"><LockEnvelope Value="0" /></AutomationTarget></{tag}>')


def _plugin(name, placeholder="false"):
    return (f'<PluginDevice Id="0"><LastPresetRef><Value /></LastPresetRef><PluginDesc><Vst3PluginInfo Id="0">'
            f'<IsPlaceholderDevice Value="{placeholder}" /><Preset><Vst3Preset Id="0">'
            '<OverwriteProtectionNumber Value="2819" /><IsOn Value="true" />'
            '<PowerMacroControlIndex Value="3" /><PowerMacroMappingRange><Min Value="64" /><Max Value="127" />'
            '</PowerMacroMappingRange><ProcessorState>DEADBEEF</ProcessorState><Name Value="" /></Vst3Preset>'
            f'</Preset><Name Value="{name}" /></Vst3PluginInfo></PluginDesc></PluginDevice>')


EQ8 = ('<Eq8 Id="0"><LastPresetRef><Value><AbletonDefaultPresetRef Id="1"><FileRef>'
       '<RelativePath Value="Devices/Audio Effects/EQ Eight" /></FileRef><DeviceId Name="Eq8" />'
       '</AbletonDefaultPresetRef></Value></LastPresetRef>'
       f'<Bands.0><ParameterA>{_param("Freq", 70, 10, 22000)}{_param("Gain", 0, -15, 15)}</ParameterA></Bands.0>'
       f'<Bands.1><ParameterA>{_param("Freq", 300, 10, 22000)}{_param("Gain", -2.5, -15, 15)}</ParameterA></Bands.1>'
       '</Eq8>')
GLUE = ('<GlueCompressor Id="0"><LastPresetRef><Value /></LastPresetRef>'
        '<On><LomId Value="0" /><Manual Value="true" /></On>'
        f'{_param("Threshold", -15, -40, 0, keymidi=True)}{_param("Makeup", 2, 0, 20)}{_param("DryWet", 0.75)}'
        f'<SideChain>{_param("DryWet", 1)}</SideChain></GlueCompressor>')


def _track(kind, name, devices):
    return (f'<{kind} Id="0"><Name><EffectiveName Value="{name}" /></Name>'
            f'<DeviceChain><DeviceChain><Devices>{devices}</Devices></DeviceChain></DeviceChain></{kind}>')


SET = ('<?xml version="1.0" encoding="UTF-8"?><Ableton MajorVersion="5" MinorVersion="11.0_11300"><LiveSet><Tracks>'
       + _track("MidiTrack", "Piano Rig", _plugin("Kontakt") + EQ8 + _plugin("Guitar Rig 7") + GLUE)
       + _track("AudioTrack", "4-Audio", GLUE)
       + _track("AudioTrack", "Vox", _plugin("Ghost", placeholder="true"))
       + _track("MidiTrack", "Empty", "")
       + '</Tracks><MasterTrack><Name><EffectiveName Value="Master" /></Name>'
       '<DeviceChain><DeviceChain><Devices /></DeviceChain></DeviceChain></MasterTrack></LiveSet></Ableton>')

PIANO_MACROS = [
    {"name": "Low Cut", "device": 1, "param": "1 Frequency A", "min": 30, "max": 300, "value": 47},
    {"name": "Mud Cut", "device": 1, "param": "2 Gain A", "min": 0, "max": -8, "value": 40},
    {"name": "Squash", "device": 3, "param": "Threshold", "min": 0, "max": -30, "value": 68},
    {"name": "Comp Mix", "device": 3, "param": "Dry/Wet", "min": 0, "max": 1},
    {"name": "Amp", "device": 2, "param": "Device On", "min": 64, "max": 127, "value": 127},
]


class RackBuilderTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.als = self.dir / "set.als"
        with gzip.open(self.als, "wb") as f:
            f.write(SET.encode("utf-8"))

    def tearDown(self):
        self._tmp.cleanup()

    def build(self, track="Piano Rig", macros=PIANO_MACROS, out="Piano Rig.adg", **kw):
        result = build_rack(self.als, track, self.dir / out, macros, **kw)
        return result, ET.fromstring(gzip.open(self.dir / out).read())

    def test_midi_track_becomes_instrument_rack_with_chain_in_order(self):
        result, root = self.build()
        self.assertEqual(result["kind"], "Instrument Rack")
        rack = root.find("GroupDevicePreset/Device/InstrumentGroupDevice")
        self.assertEqual(rack.find("UserName").get("Value"), "Piano Rig")
        presets = list(root.find("GroupDevicePreset/BranchPresets/InstrumentBranchPreset/DevicePresets"))
        self.assertEqual([p.tag for p in presets],
                         ["Vst3Preset", "AbletonDevicePreset", "Vst3Preset", "AbletonDevicePreset"])
        self.assertEqual([p.get("Id") for p in presets], ["0", "1", "2", "3"])
        self.assertEqual(presets[1].find("Device")[0].tag, "Eq8")
        self.assertEqual(presets[0].find("ProcessorState").text, "DEADBEEF")
        self.assertEqual(result["devices"], ["0:Kontakt", "1:Eq8", "2:Guitar Rig 7", "3:GlueCompressor"])

    def test_native_macro_is_keymidi_after_lomid_on_channel_16(self):
        _, root = self.build()
        presets = root.find("GroupDevicePreset/BranchPresets/InstrumentBranchPreset/DevicePresets")
        freq = presets[1].find("Device/Eq8/Bands.0/ParameterA/Freq")
        self.assertEqual([c.tag for c in freq][:3], ["LomId", "KeyMidi", "Manual"])
        self.assertEqual(freq.find("KeyMidi/Channel").get("Value"), "16")
        self.assertEqual(freq.find("KeyMidi/NoteOrController").get("Value"), "0")
        self.assertEqual(freq.find("MidiControllerRange/Min").get("Value"), "30.0")
        self.assertEqual(freq.find("MidiControllerRange/Max").get("Value"), "300.0")
        gain = presets[1].find("Device/Eq8/Bands.1/ParameterA/Gain")
        self.assertEqual(gain.find("KeyMidi/NoteOrController").get("Value"), "1")

    def test_old_mappings_are_dropped_and_only_new_ones_remain(self):
        _, root = self.build()
        glue = root.find("GroupDevicePreset/BranchPresets/InstrumentBranchPreset/DevicePresets")[3]
        threshold = glue.find("Device/GlueCompressor/Threshold")
        self.assertEqual(len(threshold.findall("KeyMidi")), 1)  # the set's channel-3 mapping is gone
        self.assertEqual(threshold.find("KeyMidi/Channel").get("Value"), "16")
        self.assertIsNone(glue.find("Device/GlueCompressor/Makeup/KeyMidi"))

    def test_plugin_power_macro_and_unmapped_plugin_reset(self):
        _, root = self.build()
        presets = root.find("GroupDevicePreset/BranchPresets/InstrumentBranchPreset/DevicePresets")
        amp = presets[2]
        self.assertEqual(amp.find("PowerMacroControlIndex").get("Value"), "4")
        self.assertEqual(amp.find("PowerMacroMappingRange/Min").get("Value"), "64")
        self.assertEqual(amp.find("PowerMacroMappingRange/Max").get("Value"), "127")
        self.assertEqual(presets[0].find("PowerMacroControlIndex").get("Value"), "-1")

    def test_macro_names_values_and_count(self):
        result, root = self.build()
        rack = root.find("GroupDevicePreset/Device/InstrumentGroupDevice")
        self.assertEqual(rack.find("NumVisibleMacroControls").get("Value"), "8")
        self.assertEqual(rack.find("MacroDisplayNames.0").get("Value"), "Low Cut")
        self.assertEqual(rack.find("MacroControls.0/Manual").get("Value"), "47.0")
        self.assertEqual(rack.find("MacroDefaults.2").get("Value"), "68.0")
        self.assertEqual(rack.find("MacroDisplayNames.5").get("Value"), "Macro 6")
        # no value given: keep Dry/Wet where it sits (0.75 of 0..1)
        self.assertAlmostEqual(result["macros"][3]["value"], 95.25)

    def test_dry_wet_is_the_device_param_not_the_sidechain_one(self):
        result, _ = self.build()
        self.assertEqual(result["macros"][3]["param"], "DryWet")

    def test_preset_ref_comes_from_where_live_loaded_the_device(self):
        _, root = self.build()
        presets = root.find("GroupDevicePreset/BranchPresets/InstrumentBranchPreset/DevicePresets")
        ref = presets[1].find("PresetRef/AbletonDefaultPresetRef")
        self.assertEqual(ref.find("FileRef/RelativePath").get("Value"), "Devices/Audio Effects/EQ Eight")
        fallback = presets[3].find("PresetRef/AbletonDefaultPresetRef/DeviceId")
        self.assertEqual(fallback.get("Name"), "GlueCompressor")

    def test_audio_track_becomes_audio_effect_rack(self):
        result, root = self.build(track="4-Audio", out="bus.adg", macros=[
            {"name": "Squash", "device": 0, "param": "Threshold", "min": 0, "max": -30, "value": 10}])
        self.assertEqual(result["kind"], "Audio Effect Rack")
        branch = root.find("GroupDevicePreset/BranchPresets/AudioEffectBranchPreset")
        self.assertEqual(branch.find("Name").get("Value"), "4-Audio")
        self.assertEqual(len(branch.find("DevicePresets")), 1)
        self.assertIsNotNone(root.find("GroupDevicePreset/Device/AudioEffectGroupDevice"))

    def test_track_is_matched_by_number(self):
        result, root = self.build(track="2", out="bus.adg", macros=[
            {"name": "Squash", "device": 0, "param": "Threshold", "min": 0, "max": -30, "value": 10}])
        self.assertEqual(result["kind"], "Audio Effect Rack")
        branch = root.find("GroupDevicePreset/BranchPresets/AudioEffectBranchPreset")
        self.assertEqual(branch.find("Name").get("Value"), "4-Audio")
        self.assertEqual(len(branch.find("DevicePresets")), 1)
        self.assertIsNotNone(root.find("GroupDevicePreset/Device/AudioEffectGroupDevice"))

    def test_missing_track_names_the_closest_three(self):
        with self.assertRaisesRegex(RackError, "Closest:") as cm:
            self.build(track="Audoi", macros=[])
        self.assertIn("4-Audio", str(cm.exception))
        self.assertNotIn("Tracks:", str(cm.exception))

    def test_bad_specs_fail_with_a_reason(self):
        cases = [
            ({"name": "x", "device": 9, "param": "Threshold", "min": 0, "max": 1}, "outside the chain"),
            ({"name": "x", "device": 3, "param": "Nope", "min": 0, "max": 1}, "no mappable parameter"),
            ({"name": "x", "device": 0, "param": "Volume", "min": 0, "max": 1}, "only a plugin's power"),
        ]
        for spec, message in cases:
            with self.assertRaisesRegex(RackError, message):
                self.build(macros=[spec], out="bad.adg")
        with self.assertRaisesRegex(RackError, "placeholder"):
            self.build(track="Vox", macros=[], out="vox.adg")
        with self.assertRaisesRegex(RackError, "no devices"):
            self.build(track="Empty", macros=[], out="empty.adg")

    def test_never_overwrites_unless_asked(self):
        self.build()
        with self.assertRaisesRegex(RackError, "exists"):
            self.build()
        self.build(overwrite=True)

    def test_browser_uri_for_user_library_presets(self):
        path = Path(r"C:\Users\x\Documents\Ableton\User Library\Presets\Instruments\Instrument Rack\Piano Rig.adg")
        self.assertEqual(rack_builder.browser_uri(path),
                         "query:UserLibrary#Presets:Instruments:Instrument%20Rack:Piano%20Rig.adg")
        self.assertIsNone(rack_builder.browser_uri(self.dir / "x.adg"))


if __name__ == "__main__":
    unittest.main()
