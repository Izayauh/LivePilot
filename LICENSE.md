# License

Copyright (c) 2026 Isaiah Washington. All rights reserved.

Live Pilot is source-available. You may download, install and run it for your own music,
and read or modify the code for your own use. You may not sell it, redistribute it, or
offer it as a service without written permission from the author.

These terms cover everything in this project except the files listed under the remote
script below, which are under their own license.

It comes as is, with no warranty of any kind. It changes your Ableton Live set when you
ask it to. Every change it makes through its own tools can be undone with `undo`, and
Live's own Undo (Ctrl+Z) still works, but save your work.

## The remote script inside Ableton Live (Business Source License 1.1)

- `ableton_remote_script/LivePilot_base/` is LivePilot by Pilot Studio
  (https://github.com/dreamrec/LivePilot, tag v1.25.0), (c) 2026 Pilot Studio, used under the
  Business Source License 1.1. Pilot Studio is the Licensor. Its `LICENSE` file is kept
  unchanged beside it and is installed into Ableton Live with it; that file is the full text.
- In short: the license lets you copy, modify, redistribute and make non-production use of it.
  Its Additional Use Grant also allows production use, as long as that use does not include
  offering it as a commercial hosted service to third parties. On its Change Date, April 13,
  2030 (or four years after a version was first publicly distributed, if that comes first), it
  becomes available under the MIT License. It grants no rights to Pilot Studio's trademarks or logos.
- `ableton_remote_script/LivePilot/server.py` is a modified copy of that work's TCP server, and
  `ableton_remote_script/LivePilot/lp_dialcore.py` and `lp_workflows.py` are handlers built on it
  and loaded by it. The installed `__init__.py` in `LivePilot_base/` is modified from upstream too.
  These files are derived from the licensed work and carry the same Business Source License 1.1,
  not the terms at the top of this file.

## Other third-party code

- Speech recognition uses NVIDIA Parakeet TDT 0.6B v2 (CC-BY-4.0) through onnx-asr, and
  Silero VAD (MIT). The models download from Hugging Face on first run.
- Python packages are under their own licenses; see each package.
