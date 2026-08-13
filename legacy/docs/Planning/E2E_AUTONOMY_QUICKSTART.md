# E2E Autonomy Quickstart

## 1) Required setup
- Ableton installed and launchable from Windows user session.
- Jarvis project venv exists at `venv\Scripts\python.exe`.
- Open Ableton at least once manually (plugin scans/first-run prompts done).

## 2) Run E2E (Windows PowerShell)
```powershell
cd C:\Users\isaia\Documents\JarvisAbleton
.\scripts\run_jarvis_e2e.ps1 -Song "Ultralight Beam" -Artist "Kanye West" -Section "chorus" -Track 0 -Mode full

# If auto-detect fails, pass explicit Ableton path:
.\scripts\run_jarvis_e2e.ps1 -Song "Ultralight Beam" -Artist "Kanye West" -Section "chorus" -Track 0 -Mode full -AbletonExe "C:\ProgramData\Ableton\Live 11 Suite\Program\Ableton Live 11 Suite.exe"
```

## 3) Outputs
- `logs\e2e_state.json`
- `logs\e2e_summary.json`
- `logs\librarian_full_chain_test.json`

## 4) If Ableton crashes
- Watchdog attempts restart (2 tries).
- Unknown dialog => blocked for manual confirmation.

## 5) Node/screen automation (next)
- Pair OpenClaw node for actual visual dialog detection/clicking.
- Then wire `ableton_watchdog.py` with node/browser snapshot + click actions.
