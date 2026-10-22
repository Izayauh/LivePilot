# LivePilot connector, installed base (backup)

The rest of the LivePilot remote script that Ableton loads from
`C:\ProgramData\Ableton\Live 11 Standard\Resources\MIDI Remote Scripts\LivePilot`
(version 1.25.0, written for Live 12, running on Live 11 Standard). Copied here on
2026-10-20 so a Live reinstall can't wipe it: Live Pilot Studio talks to this
connector over TCP 9878 and it is the one piece of the old system being kept.

The three repo-owned files (`server.py`, `lp_dialcore.py`, `lp_workflows.py`) live
in `../LivePilot/` and are not duplicated here. `__init__.py` is the installed copy,
including the import lines `scripts/deploy_remote_handlers.py` added.

Kept in its own folder on purpose: the deploy script copies every `*.py` in
`../LivePilot/` and adds an import line for each, which would break on
`__init__.py`, `router.py` and the helpers.

Restore after a reinstall: copy this folder's `*.py` and `../LivePilot/*.py` into the
install path above, then restart Live.

Origin: LivePilot by Pilot Studio, https://github.com/dreamrec/LivePilot, tag v1.25.0.
License: Business Source License 1.1, copied unchanged from that tag into `LICENSE`
(its header still names 1.10.0; upstream fixed that wording in a later release).
BSL 1.1 allows copying, modifying and redistributing; production use is allowed
except offering it as a commercial hosted service; it becomes MIT on 2030-04-13.
The same license covers the modified upstream files in `../LivePilot/`
(`server.py`, `__init__.py`).
