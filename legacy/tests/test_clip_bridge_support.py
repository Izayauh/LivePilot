import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from ableton_controls.controller import AbletonController


class TestControllerClipBridgeSupport(unittest.TestCase):
    def test_set_clip_path_sends_audio_clip_request(self):
        controller = object.__new__(AbletonController)
        calls = []

        def fake_send(address, args, timeout):
            calls.append((address, args, timeout))
            return {"success": True, "args": [1, "success", "loaded"]}

        controller._send_jarvis_request = fake_send
        controller._jarvis_status_result = AbletonController._jarvis_status_result.__get__(
            controller, AbletonController
        )

        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "vocal.wav"
            audio.write_bytes(b"fake")
            result = controller.set_clip_path(2, 0, str(audio))

        self.assertTrue(result["success"])
        self.assertEqual(calls[0][0], "/jarvis/clip/create_audio")
        self.assertEqual(calls[0][1][0:2], [2, 0])
        self.assertEqual(result["audio_path"], str(audio.resolve()))

    def test_get_clip_audio_path_returns_path_from_response(self):
        controller = object.__new__(AbletonController)
        controller._send_jarvis_request = mock.Mock(
            return_value={"success": True, "args": [1, "success", "C:\\audio\\ref.wav"]}
        )
        controller._jarvis_status_result = AbletonController._jarvis_status_result.__get__(
            controller, AbletonController
        )

        result = controller.get_clip_audio_path(0, 0)

        self.assertTrue(result["success"])
        self.assertEqual(result["audio_path"], "C:\\audio\\ref.wav")
        controller._send_jarvis_request.assert_called_once_with(
            "/jarvis/clip/get_audio_path", [0, 0], timeout=5.0
        )

    def test_set_clip_detune_returns_applied_cents(self):
        controller = object.__new__(AbletonController)
        controller._send_jarvis_request = mock.Mock(
            return_value={"success": True, "args": [1, "success", "Detune applied", 5.0]}
        )
        controller._jarvis_status_result = AbletonController._jarvis_status_result.__get__(
            controller, AbletonController
        )

        result = controller.set_clip_detune(3, 0, 5.0)

        self.assertTrue(result["success"])
        self.assertEqual(result["cents"], 5.0)
        controller._send_jarvis_request.assert_called_once_with(
            "/jarvis/clip/set_detune", [3, 0, 5.0], timeout=5.0
        )


class FakeClip:
    def __init__(self, path="C:\\audio\\ref.wav"):
        self.is_audio_clip = True
        self.file_path = path
        self.name = "ref"
        self.pitch_fine = 0.0


class FakeClipSlot:
    def __init__(self, clip=None):
        self.clip = clip
        self.has_clip = clip is not None
        self.deleted = False
        self.created_path = None

    def delete_clip(self):
        self.deleted = True
        self.has_clip = False
        self.clip = None

    def create_audio_clip(self, path):
        self.created_path = path
        self.clip = FakeClip(path)
        self.has_clip = True


class FakeTrack:
    def __init__(self, slot):
        self.clip_slots = [slot]


class FakeSong:
    def __init__(self, slot):
        self.tracks = [FakeTrack(slot)]


class FakeCInstance:
    def __init__(self, song):
        self._song = song

    def song(self):
        return self._song

    def log_message(self, _message):
        pass


def load_remote_script_module():
    sys.modules.setdefault("Live", types.SimpleNamespace(Application=types.SimpleNamespace()))
    path = Path(__file__).resolve().parents[1] / "ableton_remote_script" / "JarvisDeviceLoader" / "__init__.py"
    spec = importlib.util.spec_from_file_location("jarvis_device_loader_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestJarvisDeviceLoaderClipHelpers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_remote_script_module()

    def make_loader(self, slot):
        loader = object.__new__(self.module.JarvisDeviceLoader)
        loader._c_instance = FakeCInstance(FakeSong(slot))
        return loader

    def test_create_audio_clip_replaces_existing_clip(self):
        slot = FakeClipSlot(FakeClip())
        loader = self.make_loader(slot)

        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "ref.wav"
            audio.write_bytes(b"fake")
            result = loader._create_audio_clip(0, 0, str(audio))

        self.assertEqual(result[0:2], [1, "success"])
        self.assertTrue(slot.deleted)
        self.assertEqual(slot.created_path, str(audio))

    def test_get_clip_audio_path_requires_audio_clip(self):
        slot = FakeClipSlot(FakeClip("C:\\audio\\loaded.wav"))
        loader = self.make_loader(slot)

        result = loader._get_clip_audio_path(0, 0)

        self.assertEqual(result, [1, "success", "C:\\audio\\loaded.wav"])

    def test_set_clip_detune_updates_pitch_fine(self):
        clip = FakeClip()
        slot = FakeClipSlot(clip)
        loader = self.make_loader(slot)

        result = loader._set_clip_detune(0, 0, -5.0)

        self.assertEqual(result, [1, "success", "Detune applied", -5.0])
        self.assertEqual(clip.pitch_fine, -5.0)

    def test_set_clip_detune_rejects_out_of_range_values(self):
        slot = FakeClipSlot(FakeClip())
        loader = self.make_loader(slot)

        result = loader._set_clip_detune(0, 0, 60.0)

        self.assertEqual(result[0], 0)
        self.assertIn("between -50 and 49", result[2])


if __name__ == "__main__":
    unittest.main()
