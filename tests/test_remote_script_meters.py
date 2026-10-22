"""Meter readers over the LivePilot remote script's TCP server (127.0.0.1:9878)."""

import json
import unittest
from unittest.mock import patch

from livepilot_tools import remote_script


class FakeSocket:
    """Records the request line and replays a canned response in small chunks."""

    def __init__(self, response=None, raw=None, chunk=7):
        self.sent = b""
        payload = raw if raw is not None else (json.dumps(response) + "\n").encode()
        self._chunks = [payload[i:i + chunk] for i in range(0, len(payload), chunk)]

    def sendall(self, data):
        self.sent += data

    def recv(self, _size):
        return self._chunks.pop(0) if self._chunks else b""

    closed = False

    def settimeout(self, _t):
        pass

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def request(self):
        return json.loads(self.sent.decode().rstrip("\n"))


def connect_returning(sock):
    return patch("livepilot_tools.remote_script.socket.create_connection",
                 return_value=sock)


class TestSendCommand(unittest.TestCase):
    def test_request_is_one_json_line_with_type_and_params(self):
        sock = FakeSocket({"id": "x", "ok": True, "result": {"level": 0.5}})
        with connect_returning(sock):
            remote_script.send_command("get_master_meters", {"a": 1})
        self.assertTrue(sock.sent.endswith(b"\n"))
        self.assertEqual(sock.sent.count(b"\n"), 1)
        req = sock.request()
        self.assertEqual(req["type"], "get_master_meters")
        self.assertEqual(req["params"], {"a": 1})
        self.assertIn("id", req)

    def test_error_envelope_is_not_success(self):
        sock = FakeSocket({"id": "x", "ok": False,
                           "error": {"code": "NOT_FOUND", "message": "Track 99 out of range"}})
        with connect_returning(sock):
            result = remote_script.send_command("get_track_meters", {"track_index": 99})
        self.assertFalse(result["success"])
        self.assertEqual(result["code"], "NOT_FOUND")
        self.assertIn("out of range", result["message"])

    def test_unreachable_server_is_not_success(self):
        with patch("livepilot_tools.remote_script.socket.create_connection",
                   side_effect=ConnectionRefusedError("refused")):
            result = remote_script.send_command("get_master_meters")
        self.assertFalse(result["success"])
        self.assertIn("9878", result["message"])

    def test_closed_without_response_is_not_success(self):
        with connect_returning(FakeSocket(raw=b"")):
            result = remote_script.send_command("get_master_meters")
        self.assertFalse(result["success"])

    def test_bad_json_is_not_success(self):
        with connect_returning(FakeSocket(raw=b"not json\n")):
            result = remote_script.send_command("get_master_meters")
        self.assertFalse(result["success"])

    def test_write_replaces_the_shared_socket_instead_of_opening_a_second(self):
        # The server is single-client: two sockets from one process kick each other.
        read = FakeSocket({"id": "x", "ok": True, "result": {}})
        with connect_returning(read):
            remote_script.send_command("get_session_info", persistent=True)
        write = FakeSocket({"id": "y", "ok": True, "result": {}})
        with connect_returning(write):
            remote_script.send_command("delete_device", {"track_index": 0, "device_index": 0})
        self.assertTrue(read.closed)
        self.assertIs(remote_script._conn, write)

    def test_write_is_never_resent(self):
        dead = FakeSocket(raw=b"")
        with connect_returning(dead) as connect:
            result = remote_script.send_command("delete_device", {"track_index": 0, "device_index": 0})
        self.assertFalse(result["success"])
        self.assertEqual(connect.call_count, 1)
        self.assertEqual(dead.sent.count(b"\n"), 1)


class TestMeters(unittest.TestCase):
    def test_master_meters(self):
        sock = FakeSocket({"id": "x", "ok": True,
                           "result": {"level": 0.8, "left": 0.79, "right": 0.8}})
        with connect_returning(sock):
            result = remote_script.get_master_meters()
        self.assertEqual(result, {"success": True, "level": 0.8, "left": 0.79, "right": 0.8})

    def test_track_meters_single_track_with_stereo(self):
        tracks = [{"index": 2, "name": "Vox", "level": 0.6, "left": 0.6, "right": 0.55}]
        sock = FakeSocket({"id": "x", "ok": True, "result": {"tracks": tracks}})
        with connect_returning(sock):
            result = remote_script.get_track_meters(track_index=2, include_stereo=True)
        self.assertEqual(sock.request()["params"], {"track_index": 2, "include_stereo": True})
        self.assertTrue(result["success"])
        self.assertEqual(result["tracks"], tracks)

    def test_track_meters_all_tracks_omits_track_index(self):
        sock = FakeSocket({"id": "x", "ok": True, "result": {"tracks": []}})
        with connect_returning(sock):
            remote_script.get_track_meters()
        self.assertEqual(sock.request()["params"], {"include_stereo": False})


class TestBridgeRegistration(unittest.TestCase):
    def test_meters_are_listed_and_dispatched(self):
        import ableton_bridge
        described = ableton_bridge._describe_functions()["functions"]
        dispatch = ableton_bridge._build_dispatch({"track_index": 1})
        for name in ("get_track_meters", "get_master_meters"):
            self.assertIn(name, described)
            self.assertIn(name, dispatch)
        self.assertFalse(described["get_track_meters"]["args"]["track_index"]["required"])

        sock = FakeSocket({"id": "x", "ok": True, "result": {"tracks": []}})
        with connect_returning(sock):
            dispatch["get_track_meters"]()
        self.assertEqual(sock.request()["params"], {"track_index": 1, "include_stereo": False})


if __name__ == "__main__":
    unittest.main()
