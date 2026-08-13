# Jarvis Ableton E2E Autonomy Spec (v1)

## Goal
Enable Izzy to run Jarvis end-to-end with minimal human intervention:
1. launch with correct ENV
2. detect/recover from Ableton crashes
3. click safe/known dialogs automatically
4. execute Librarian chain tests
5. output machine-verifiable reports

---

## 1) Control Plane

### 1.1 Required capability
- Paired OpenClaw node with screen control and command execution.
- If node is unavailable, fallback mode still supports command-only tests (no UI clicking).

### 1.2 Screen actions (future integration)
- Detect dialog title/body by snapshot OCR/vision.
- Allowed actions:
  - click `Yes`, `No`, `OK`, `Continue` only for whitelisted dialog signatures.

### 1.3 Dialog whitelist
Allowed when window text contains any:
- `Ableton Live`
- `has unexpectedly quit`
- `Recover`
- `plugin scan`
- `audio engine`

Anything else => halt and request human review.

---

## 2) Runtime Plane

### 2.1 Canonical entrypoint
- `scripts/run_jarvis_e2e.ps1`
- Responsibilities:
  - assert project root
  - activate venv
  - load `.env`
  - run `scripts/e2e_orchestrator.py`

### 2.2 Deterministic run modes
- `full`: launch/recover + run tests + verify
- `verify-only`: skip apply, validate current track/plugin state
- `resume`: continue from checkpoint

---

## 3) Recovery Layer

### 3.1 Watchdog responsibilities
- Poll for Ableton process existence.
- Detect known crash/recovery dialogs.
- Attempt auto-resolution for whitelisted dialogs.
- Emit structured events to orchestrator.

### 3.2 Recovery strategy
- If process missing:
  1. try launch command
  2. wait for ready window timeout
  3. continue flow
- If repeated failures exceed threshold: stop + emit fatal state.

---

## 4) Verification Layer

### 4.1 Required artifacts
- `logs/e2e_state.json` checkpoint + progress
- `logs/librarian_full_chain_test.json` detailed apply/verify result
- `logs/e2e_summary.json` compact pass/fail summary

### 4.2 Verification checks
- Song lookup success from local librarian
- Chain apply success
- Expected plugin presence on track
- Parameter configure count + failures
- Mismatch report with expected vs observed

---

## 5) State/Checkpoint Contract

`logs/e2e_state.json` shape:
```json
{
  "run_id": "2026-02-15T05-30-00",
  "mode": "full",
  "step": "verify",
  "status": "running",
  "song": "Ultralight Beam",
  "artist": "Kanye West",
  "section": "chorus",
  "track_index": 0,
  "watchdog": {
    "restarts": 0,
    "dialogs_handled": 0,
    "last_event": "none"
  },
  "updated_at": "ISO-8601"
}
```

---

## 6) Security/Safety

- Never click unknown dialogs automatically.
- Never approve installers/system privilege prompts.
- Keep strict action whitelist.
- Preserve complete logs for auditability.

---

## 7) Open Items

1. Wire actual OpenClaw node/screen actions into watchdog adapter.
2. Add app-specific selectors for Ableton dialogs.
3. Add retry backoff policy tuned by real crash behavior.
4. Extend verification to per-parameter readback where available.
