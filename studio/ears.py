"""Ears: always listening, hands back one transcript each time Isaiah stops talking.

Silero VAD (from onnx_asr) runs on every 32 ms frame to find where speech starts
and ends; Parakeet transcribes the finished utterance on the CPU.

When the mic fails (none plugged in, unplugged, or Windows handing over pure silence) or
speech recognition fails, on_state("error") is called and the reason, in plain words, is in self.error.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Callable

import numpy as np
import onnx_asr
import sounddevice as sd

from studio import config

log = logging.getLogger("studio.ears")

RATE = 16000
HOP = 512            # silero frame at 16 kHz (32 ms)
CONTEXT = 64         # silero needs the previous 64 samples with each frame
START_PROB = 0.5
END_PROB = 0.35
START_FRAMES = 3     # ~100 ms of speech opens an utterance
END_SILENCE_S = 0.7  # this much quiet closes it
PREROLL_S = 0.3
MIN_SPEECH_S = 0.35
MAX_SPEECH_S = 30.0
SILENT_S = 3.0       # this much exact digital silence means Windows is not giving us the mic
DEAD_S = 3.0         # this long with no audio at all means the mic went away

RESTART = "Then close and reopen Live Pilot Studio: it only looks for microphones when it starts."
NO_MIC = ("No microphone found. Plug one in and make it the default input "
          "(Windows Settings > System > Sound > Input). " + RESTART)
MIC_FAILED = "The microphone {name}stopped working ({why}). Check that it is plugged in. " + RESTART
ASR_FAILED = "I could not make out that last part (speech recognition failed: {why}). Say it again."
ASR_GONE = ("Speech recognition stopped working ({why}). You can still type below. "
            "Close and reopen Live Pilot Studio to get the mic back.")
ASR_GIVE_UP = 3      # this many failures in a row means the speech model itself is gone
MIC_PRIVACY = ("The microphone is sending only silence. Windows may be blocking it: open Settings > "
               "Privacy & security > Microphone and turn on microphone access, including for desktop apps.")


class Ears:
    def __init__(self, on_state: Callable[[str], None], on_text: Callable[[str, dict], None]):
        self.on_state = on_state
        self.on_text = on_text
        self.muted = False
        self.talking = False  # mid-utterance; the server holds a cut-off line while this is true
        self.device_name = ""
        self.error = ""             # why the mic is not working, in plain words; blank when it is
        self.silent_input = False   # frames arrive but are all exact zeros (Windows privacy setting)
        self._vad = onnx_asr.load_vad("silero")._model
        self._asr = onnx_asr.load_model("nemo-parakeet-tdt-0.6b-v2")
        self._asr.recognize(np.zeros(RATE, dtype=np.float32), sample_rate=RATE)  # first call is ~10x slower
        self._frames: queue.Queue[np.ndarray] = queue.Queue()
        self._jobs: queue.Queue[tuple[np.ndarray, float]] = queue.Queue()

    def start(self) -> None:
        threading.Thread(target=self._listen, daemon=True).start()
        threading.Thread(target=self._transcribe, daemon=True).start()

    def _open_stream(self) -> tuple[sd.InputStream, int]:
        wanted = config.mic().lower()
        device = None
        if wanted:
            for i, d in enumerate(sd.query_devices()):
                if d["max_input_channels"] > 0 and wanted in d["name"].lower():
                    device = i
                    break
        info = sd.query_devices(device, kind="input")
        self.device_name = info["name"]
        rate = int(info["default_samplerate"])
        block = int(round(HOP * rate / RATE))
        stream = sd.InputStream(device=device, channels=1, samplerate=rate, blocksize=block, dtype="float32",
                                callback=lambda data, *_: self._frames.put(data[:, 0].copy()))
        return stream, rate

    def _listen(self) -> None:
        """Runs until the mic fails; then says why (on_state("error") plus self.error) and stops."""
        try:
            self._listen_until_failure()
        except Exception as e:  # noqa: BLE001 - any mic failure ends the same way for the user
            log.exception("the mic stopped")
            no_device = isinstance(e, sd.PortAudioError) and not self.device_name
            self.error = NO_MIC if no_device else MIC_FAILED.format(name=f"{self.device_name} " if self.device_name else "", why=e)
            self.on_state("error")

    def _listen_until_failure(self) -> None:
        stream, rate = self._open_stream()
        state = np.zeros((2, 1, 128), dtype=np.float32)
        tail = np.zeros(CONTEXT, dtype=np.float32)
        preroll: list[np.ndarray] = []
        speech: list[np.ndarray] = []
        voiced = quiet = 0
        end_frames = int(END_SILENCE_S * RATE / HOP)
        silent_frames = int(SILENT_S * RATE / HOP)
        zeros = 0
        with stream:
            self.on_state("listening")
            while True:
                try:
                    raw = self._frames.get(timeout=DEAD_S)
                except queue.Empty:
                    raise RuntimeError(f"no audio from {self.device_name} for {DEAD_S:.0f} seconds") from None
                frame = raw if rate == RATE else np.interp(
                    np.linspace(0, len(raw) - 1, HOP), np.arange(len(raw)), raw).astype(np.float32)
                if self.muted:
                    self.talking, speech, preroll, voiced, zeros = False, [], [], 0, 0
                    self.silent_input, self.error = False, ""  # check again after unmute
                    continue
                if raw.any():
                    zeros = 0
                    if self.silent_input:
                        self.silent_input, self.error = False, ""
                        self.on_state("listening")
                else:
                    zeros += 1
                    if zeros >= silent_frames and not self.silent_input:
                        self.silent_input, self.error = True, MIC_PRIVACY
                        log.warning("mic %s sends only exact zeros", self.device_name)
                        self.on_state("error")
                prob, state = self._vad.run(["output", "stateN"], {
                    "input": np.concatenate([tail, frame])[None, :], "state": state, "sr": np.array([RATE], dtype=np.int64)})
                prob = float(prob[0, 0])
                tail = frame[-CONTEXT:]
                if not self.talking:
                    preroll = (preroll + [frame])[-int(PREROLL_S * RATE / HOP):]
                    voiced = voiced + 1 if prob >= START_PROB else 0
                    if voiced >= START_FRAMES:
                        self.talking, speech, quiet = True, list(preroll), 0
                        self.on_state("hearing")
                    continue
                speech.append(frame)
                quiet = quiet + 1 if prob < END_PROB else 0
                if quiet >= end_frames or len(speech) * HOP / RATE >= MAX_SPEECH_S:
                    self.talking, voiced, preroll = False, 0, []
                    audio = np.concatenate(speech[: len(speech) - quiet + 3] if quiet else speech)
                    if len(audio) / RATE >= MIN_SPEECH_S:
                        self._jobs.put((audio, time.time()))
                        self.on_state("transcribing")
                    else:
                        self.on_state("listening")

    def _transcribe(self) -> None:
        """One utterance at a time. A failed one is said and skipped; after ASR_GIVE_UP failures in a row
        the model is taken as gone, which is said too, and this thread stops."""
        failures = 0
        while True:
            audio, ended = self._jobs.get()
            try:
                text = str(self._asr.recognize(audio, sample_rate=RATE)).strip()
            except Exception as e:  # noqa: BLE001 - a crash here would end the thread and leave him unheard
                failures += 1
                log.exception("transcribing failed (%d in a row)", failures)
                gone = failures >= ASR_GIVE_UP
                said = self.error = (ASR_GONE if gone else ASR_FAILED).format(why=e)
                self.on_state("error")
                if gone:
                    return
                if self.error == said:  # unless the mic itself failed meanwhile: that message stays
                    self.error = ""
                    self.on_state("listening")
                continue
            failures = 0
            done = time.time()
            if text:
                self.on_text(text, {"speech_end": ended, "transcribed": done, "speech_s": round(len(audio) / RATE, 2)})
            else:
                self.on_state("listening")
