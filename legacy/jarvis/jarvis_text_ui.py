import asyncio
import json
import os
import queue
import subprocess
import threading
import tkinter as tk
from tkinter import scrolledtext, ttk

import jarvis_engine


class GeminiFunctionBackend:
    """Stateful text-mode backend that mirrors jarvis_engine text command flow."""

    def __init__(self):
        self._contents = []
        self._lock = asyncio.Lock()
        from google.genai import types
        self._config = types.GenerateContentConfig(
            system_instruction=jarvis_engine.build_system_instruction(),
            tools=jarvis_engine.ABLETON_TOOLS,
        )

    async def warmup(self):
        """Warm model context and return an optional greeting."""
        async with self._lock:
            greeting = "Jarvis text mode is ready."
            self._contents.append(
                {"role": "user", "parts": [{"text": "Hello, I'm ready to control Ableton."}]}
            )

            try:
                response = await jarvis_engine.generate_content_with_retry(
                    jarvis_engine.client,
                    jarvis_engine.MODEL_ID_TEXT,
                    self._contents,
                    self._config,
                )
            except Exception as exc:
                jarvis_engine.log(f"Text UI warmup failed (continuing): {exc}", "DEBUG")
                self._contents = []
                return greeting

            if response.candidates and response.candidates[0].content:
                warmup_content = response.candidates[0].content
                if warmup_content.parts:
                    self._contents.append(jarvis_engine._content_to_dict(warmup_content))
                    for part in warmup_content.parts:
                        if part.text and part.text.strip():
                            greeting = part.text.strip()
                            break

            return greeting

    async def send_message(self, user_text):
        """Send one user message and return assistant text messages."""
        async with self._lock:
            responses = []
            self._contents.append({"role": "user", "parts": [{"text": user_text}]})

            try:
                response = await jarvis_engine.generate_content_with_retry(
                    jarvis_engine.client,
                    jarvis_engine.MODEL_ID_TEXT,
                    self._contents,
                    self._config,
                )

                retry_count = 0
                max_retries = 2

                while True:
                    if not response.candidates or not response.candidates[0].content:
                        break

                    model_content = response.candidates[0].content
                    parts_count = len(model_content.parts) if model_content.parts else 0

                    if parts_count == 0:
                        retry_count += 1
                        if retry_count <= max_retries:
                            await asyncio.sleep(0.5)
                            response = await jarvis_engine.generate_content_with_retry(
                                jarvis_engine.client,
                                jarvis_engine.MODEL_ID_TEXT,
                                self._contents,
                                self._config,
                            )
                            continue

                        if self._contents and self._contents[-1].get("role") == "user":
                            self._contents.pop()
                        break

                    self._contents.append(jarvis_engine._content_to_dict(model_content))

                    function_calls = []
                    for part in model_content.parts:
                        if part.function_call:
                            function_calls.append(part.function_call)
                        elif part.text:
                            text_out = part.text.strip()
                            if text_out:
                                responses.append(text_out)

                    if not function_calls:
                        break

                    function_response_parts = []
                    for call in function_calls:
                        jarvis_engine.conversation_state["tool_calls_executed"] += 1
                        call_args = dict(call.args) if call.args else {}

                        result = jarvis_engine.execute_ableton_function(call.name, call_args)
                        jarvis_engine.session_manager.record_action(
                            action=call.name, params=call_args
                        )
                        jarvis_engine.update_session_state(call.name, call_args, result)

                        function_response_parts.append(
                            {
                                "functionResponse": {
                                    "name": call.name,
                                    "response": result,
                                }
                            }
                        )

                    self._contents.append({"role": "user", "parts": function_response_parts})
                    response = await jarvis_engine.generate_content_with_retry(
                        jarvis_engine.client,
                        jarvis_engine.MODEL_ID_TEXT,
                        self._contents,
                        self._config,
                    )

                jarvis_engine.conversation_state["turns_completed"] += 1
                return responses if responses else ["Command complete."]

            except Exception:
                if self._contents and self._contents[-1].get("role") == "user":
                    self._contents.pop()
                raise


class OpenClawRelayBackend:
    """OpenClaw-only backend (no direct Gemini calls)."""

    def __init__(self):
        self._lock = asyncio.Lock()
        self.agent_id = os.getenv("JARVIS_TEXT_OPENCLAW_AGENT", "jarvis-relay").strip() or "jarvis-relay"
        self.session_id = os.getenv("JARVIS_TEXT_OPENCLAW_SESSION_ID", "").strip()
        self.timeout_s = int(os.getenv("JARVIS_TEXT_OPENCLAW_TIMEOUT_SEC", "25"))
        # Windows-launched UI may not have `openclaw` on PATH.
        # You can force a binary with JARVIS_TEXT_OPENCLAW_BIN.
        self.openclaw_bin = os.getenv("JARVIS_TEXT_OPENCLAW_BIN", "").strip()

    async def warmup(self):
        return "Jarvis text mode is ready (OpenClaw relay)."

    async def _call_openclaw(self, message: str):
        base_args = ["agent", "--json", "--timeout", str(self.timeout_s), "--message", message]
        if self.session_id:
            base_args.extend(["--session-id", self.session_id])
        else:
            base_args.extend(["--agent", self.agent_id])

        candidates = []
        if self.openclaw_bin:
            candidates.append([self.openclaw_bin] + base_args)
        # Try direct PATH first
        candidates.append(["openclaw"] + base_args)
        # Then WSL bridge (Windows -> WSL OpenClaw install). Try explicit bin first.
        relay_args = " ".join([str(a).replace('"', '\\"') for a in base_args])
        relay_cmd_explicit = (
            "/home/isaiah/.local/share/fnm/node-versions/v22.22.0/installation/bin/node "
            "/home/isaiah/.local/share/fnm/node-versions/v22.22.0/installation/lib/node_modules/openclaw/openclaw.mjs "
            f"{relay_args}"
        )
        relay_cmd_path = f"openclaw {relay_args}"
        candidates.append([r"C:\Windows\System32\wsl.exe", "-e", "bash", "-lc", relay_cmd_explicit])
        candidates.append([r"C:\Windows\System32\wsl.exe", "-e", "bash", "-lc", relay_cmd_path])

        last_err = None
        proc = None
        for cmd in candidates:
            try:
                proc = await asyncio.to_thread(
                    subprocess.run,
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_s + 10,
                )
            except FileNotFoundError as exc:
                last_err = str(exc)
                continue

            if proc.returncode == 0:
                break

            err = (proc.stderr or proc.stdout or "").strip()
            last_err = err or f"openclaw agent failed ({proc.returncode})"
            # try next candidate if this one failed
            proc = None

        if proc is None:
            raise RuntimeError(last_err or "Failed to execute OpenClaw relay backend")

        raw = (proc.stdout or "").strip()
        if not raw:
            return "(empty response)"

        try:
            data = json.loads(raw)
            return (
                data.get("reply")
                or data.get("message")
                or data.get("output")
                or data.get("text")
                or (data.get("result", {}) if isinstance(data.get("result"), dict) else {}).get("reply")
                or (data.get("result", {}) if isinstance(data.get("result"), dict) else {}).get("message")
                or raw
            )
        except Exception:
            return raw

    async def send_message(self, user_text):
        async with self._lock:
            reply = await self._call_openclaw(user_text)
            return [reply or "Command complete."]


class JarvisTextApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Jarvis Ableton - Text Mode")
        self.root.geometry("900x620")
        self.root.minsize(700, 450)

        self.events = queue.Queue()
        self.backend = None
        self.ready = False
        self.busy = False

        self._build_ui()
        self._start_worker()
        self._set_status("Connecting to Jarvis text mode...")
        self.root.after(120, self._drain_events)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        frame = ttk.Frame(self.root, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        self.chat = scrolledtext.ScrolledText(
            frame,
            wrap=tk.WORD,
            state=tk.DISABLED,
            font=("Consolas", 11),
        )
        self.chat.pack(fill=tk.BOTH, expand=True)
        self.chat.tag_configure("user", foreground="#0b5ed7")
        self.chat.tag_configure("jarvis", foreground="#1f7a1f")
        self.chat.tag_configure("system", foreground="#5a5a5a")
        self.chat.tag_configure("error", foreground="#b00020")

        controls = ttk.Frame(frame)
        controls.pack(fill=tk.X, pady=(10, 0))

        self.input_var = tk.StringVar()
        self.entry = ttk.Entry(controls, textvariable=self.input_var)
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.entry.bind("<Return>", self._on_enter)
        self.entry.configure(state=tk.DISABLED)

        self.send_button = ttk.Button(
            controls,
            text="Send",
            command=self._send_message,
            state=tk.DISABLED,
        )
        self.send_button.pack(side=tk.LEFT, padx=(8, 0))

        self.status_var = tk.StringVar(value="Initializing...")
        self.status = ttk.Label(frame, textvariable=self.status_var)
        self.status.pack(anchor="w", pady=(8, 0))

    def _start_worker(self):
        self.loop = asyncio.new_event_loop()
        self.worker = threading.Thread(target=self._run_event_loop, daemon=True)
        self.worker.start()
        asyncio.run_coroutine_threadsafe(self._initialize_backend(), self.loop)

    def _run_event_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    async def _initialize_backend(self):
        try:
            backend_mode = os.getenv("JARVIS_TEXT_BACKEND", "openclaw").strip().lower()
            if backend_mode == "gemini":
                self.backend = GeminiFunctionBackend()
            else:
                self.backend = OpenClawRelayBackend()
            greeting = await self.backend.warmup()
            self.events.put(("ready", f"[{backend_mode}] {greeting}"))
        except Exception as exc:
            self.events.put(("error", f"Startup failed: {exc}"))

    def _on_enter(self, _event):
        self._send_message()
        return "break"

    def _send_message(self):
        if not self.ready or self.busy:
            return

        text = self.input_var.get().strip()
        if not text:
            return

        self.input_var.set("")
        self._append("You", text, "user")
        self._set_busy(True)

        future = asyncio.run_coroutine_threadsafe(
            self._backend_send(text), self.loop
        )
        future.add_done_callback(self._background_done)

    async def _backend_send(self, text):
        replies = await self.backend.send_message(text)
        for item in replies:
            self.events.put(("assistant", item))
        self.events.put(("done", None))

    def _background_done(self, future):
        try:
            future.result()
        except Exception as exc:
            self.events.put(("error", f"Request failed: {exc}"))
            self.events.put(("done", None))

    def _drain_events(self):
        while True:
            try:
                kind, payload = self.events.get_nowait()
            except queue.Empty:
                break

            if kind == "ready":
                self.ready = True
                self._set_busy(False)
                self._set_status("Ready")
                self._append("Jarvis", payload, "jarvis")
                self.entry.focus_set()
            elif kind == "assistant":
                self._append("Jarvis", payload, "jarvis")
            elif kind == "error":
                self._append("System", payload, "error")
                self._set_busy(False)
                self._set_status("Error")
            elif kind == "done":
                self._set_busy(False)
                if self.ready:
                    self._set_status("Ready")

        self.root.after(120, self._drain_events)

    def _set_status(self, text):
        self.status_var.set(text)

    def _set_busy(self, busy):
        self.busy = busy
        if not self.ready and not busy:
            return

        if busy:
            self.send_button.configure(state=tk.DISABLED)
            self.entry.configure(state=tk.DISABLED)
            self._set_status("Jarvis is thinking...")
        else:
            self.send_button.configure(state=tk.NORMAL if self.ready else tk.DISABLED)
            self.entry.configure(state=tk.NORMAL if self.ready else tk.DISABLED)

    def _append(self, speaker, message, tag):
        self.chat.configure(state=tk.NORMAL)
        self.chat.insert(tk.END, f"{speaker}: ", tag)
        self.chat.insert(tk.END, f"{message}\n\n")
        self.chat.configure(state=tk.DISABLED)
        self.chat.see(tk.END)

    def _on_close(self):
        if hasattr(self, "loop"):
            self.loop.call_soon_threadsafe(self.loop.stop)
        self.root.destroy()


def main():
    root = tk.Tk()
    JarvisTextApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
