"""
Ableton Process Manager

Manages Ableton Live process lifecycle:
- Detect if Ableton is running
- Launch Ableton (optionally with a project file)
- Close Ableton (graceful then force kill)
- Detect crashes
- Handle recovery dialogs (Yes/No, configurable)
- Wait for Ableton to be ready
"""

import psutil
import subprocess
import time
import os
from typing import Optional, Dict, Tuple


class AbletonProcessManager:
    """Manages Ableton Live process and crash recovery"""

    def __init__(self,
                 ableton_path: Optional[str] = None,
                 project_path: Optional[str] = None,
                 startup_wait: float = 15.0,
                 recovery_action: str = "yes",
                 verbose: bool = True):
        """
        Initialize Ableton Process Manager

        Args:
            ableton_path: Path to Ableton.exe (auto-detected if None)
            project_path: Path to .als project file to open (optional)
            startup_wait: Seconds to wait after launching Ableton
            recovery_action: Default action for crash recovery dialog.
                "yes" = reopen last project (default),
                "no"  = start fresh,
                "ask" = log and wait for timeout then default to yes
            verbose: Print status messages
        """
        self.ableton_path = ableton_path or self._find_ableton()
        self.project_path = project_path
        self.startup_wait = startup_wait
        self.recovery_action = recovery_action.lower()
        self.verbose = verbose
        self._last_known_pid: Optional[int] = None

    def _log(self, message: str, level: str = "INFO"):
        """Log message if verbose"""
        if self.verbose:
            emoji = {"INFO": "ℹ️", "WARN": "⚠️", "ERROR": "❌", "OK": "✅"}
            print(f"{emoji.get(level, 'ℹ️')} [{level}] {message}")

    def _find_ableton(self) -> Optional[str]:
        """Auto-detect Ableton installation path"""
        common_paths = [
            # ProgramData locations (most common)
            r"C:\ProgramData\Ableton\Live 11 Suite\Program\Ableton Live 11 Suite.exe",
            r"C:\ProgramData\Ableton\Live 11 Standard\Program\Ableton Live 11 Standard.exe",
            r"C:\ProgramData\Ableton\Live 11 Intro\Program\Ableton Live 11 Intro.exe",
            r"C:\ProgramData\Ableton\Live 11\Program\Ableton Live 11.exe",
            # Program Files locations
            r"C:\Program Files\Ableton\Live 11 Suite\Program\Ableton Live 11 Suite.exe",
            r"C:\Program Files\Ableton\Live 11 Standard\Program\Ableton Live 11 Standard.exe",
            r"C:\Program Files\Ableton\Live 11\Program\Ableton Live 11.exe",
            r"C:\Program Files (x86)\Ableton\Live 11 Suite\Program\Ableton Live 11 Suite.exe",
            r"C:\Program Files (x86)\Ableton\Live 11 Standard\Program\Ableton Live 11 Standard.exe",
            r"C:\Program Files (x86)\Ableton\Live 11\Program\Ableton Live 11.exe",
        ]

        for path in common_paths:
            if os.path.exists(path):
                return path

        return None

    def is_ableton_running(self) -> Tuple[bool, Optional[int]]:
        """
        Check if Ableton is currently running

        Returns:
            Tuple of (is_running, pid)
        """
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                # Check for Ableton Live process
                if 'ableton' in proc.info['name'].lower():
                    return True, proc.info['pid']
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        return False, None

    def get_ableton_process(self) -> Optional[psutil.Process]:
        """Get the Ableton process object if running"""
        is_running, pid = self.is_ableton_running()
        if is_running and pid:
            try:
                return psutil.Process(pid)
            except psutil.NoSuchProcess:
                pass
        return None

    def wait_for_ableton_exit(self, timeout: float = 30.0) -> bool:
        """
        Wait for Ableton to fully exit

        Args:
            timeout: Maximum seconds to wait

        Returns:
            True if Ableton exited, False if timeout
        """
        start_time = time.time()

        while (time.time() - start_time) < timeout:
            is_running, _ = self.is_ableton_running()
            if not is_running:
                return True
            time.sleep(0.5)

        return False

    def close_ableton(self, force: bool = False, timeout: float = 10.0) -> bool:
        """
        Close Ableton Live.

        Sends a graceful terminate signal first. If that doesn't work within
        *timeout* seconds and *force* is True, kills the process.

        Args:
            force: Force kill if graceful close fails
            timeout: Seconds to wait for graceful exit

        Returns:
            True if Ableton was closed (or wasn't running), False on failure
        """
        is_running, pid = self.is_ableton_running()

        if not is_running:
            self._log("Ableton is not running", "INFO")
            return True

        self._log(f"Closing Ableton (PID: {pid})...", "INFO")

        try:
            proc = psutil.Process(pid)
            proc.terminate()

            if self.wait_for_ableton_exit(timeout=timeout):
                self._log("Ableton closed successfully", "OK")
                self._last_known_pid = None
                return True

            if force:
                self._log("Graceful exit failed. Force killing...", "WARN")
                proc.kill()
                time.sleep(2)
                is_still = self.is_ableton_running()[0]
                if not is_still:
                    self._log("Ableton force-killed", "OK")
                    self._last_known_pid = None
                    return True
                self._log("Force kill failed", "ERROR")
                return False
            else:
                self._log("Ableton won't close. Use force=True to force.", "ERROR")
                return False

        except Exception as e:
            self._log(f"Error closing Ableton: {e}", "ERROR")
            return False

    def launch_ableton(self, project_path: Optional[str] = None,
                       wait_for_ready: bool = True) -> bool:
        """
        Launch Ableton Live

        Args:
            project_path: Optional .als file to open. Falls back to
                self.project_path if not provided.
            wait_for_ready: Wait for Ableton to be fully loaded

        Returns:
            True if launched successfully
        """
        if not self.ableton_path:
            self._log("Ableton path not found. Cannot launch.", "ERROR")
            return False

        if not os.path.exists(self.ableton_path):
            self._log(f"Ableton not found at: {self.ableton_path}", "ERROR")
            return False

        # Check if already running
        is_running, pid = self.is_ableton_running()
        if is_running:
            self._log(f"Ableton already running (PID: {pid})", "WARN")
            self._last_known_pid = pid
            return True

        self._log("Launching Ableton Live...", "INFO")

        effective_project = project_path or self.project_path

        try:
            # Build command
            cmd = [self.ableton_path]
            if effective_project and os.path.exists(effective_project):
                cmd.append(effective_project)
                self._log(f"Opening project: {effective_project}", "INFO")

            # Launch process (detached)
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            )

            # Wait for process to appear
            if wait_for_ready:
                self._log(f"Waiting for Ableton to start ({self.startup_wait}s)...", "INFO")
                time.sleep(3)  # Initial wait for process to start

                # Wait for process to appear in task list
                start_time = time.time()
                while (time.time() - start_time) < 30:
                    is_running, pid = self.is_ableton_running()
                    if is_running:
                        self._last_known_pid = pid
                        self._log(f"Ableton process started (PID: {pid})", "OK")
                        break
                    time.sleep(0.5)
                else:
                    self._log("Ableton process not detected after 30s", "ERROR")
                    return False

                # Additional wait for full startup
                remaining_wait = self.startup_wait - (time.time() - start_time)
                if remaining_wait > 0:
                    self._log(f"Waiting {remaining_wait:.1f}s for Ableton to fully load...", "INFO")
                    time.sleep(remaining_wait)

                self._log("Ableton should be ready", "OK")

            return True

        except Exception as e:
            self._log(f"Failed to launch Ableton: {e}", "ERROR")
            return False

    def detect_crash(self) -> bool:
        """
        Detect if Ableton has crashed

        Returns:
            True if crash detected (process was running but now isn't)
        """
        is_running, current_pid = self.is_ableton_running()

        # If we knew about a process and now it's gone, it crashed
        if self._last_known_pid and not is_running:
            self._log(f"Crash detected! PID {self._last_known_pid} is no longer running", "ERROR")
            self._last_known_pid = None
            return True

        # Update last known PID
        if is_running and current_pid:
            self._last_known_pid = current_pid

        return False

    def handle_recovery_dialog(self, reopen_project: Optional[bool] = None,
                               timeout: float = 10.0) -> bool:
        """
        Handle Ableton's crash recovery dialog.

        Args:
            reopen_project: True = click Yes (reopen), False = click No (fresh start).
                If None, uses self.recovery_action setting:
                  "yes"  -> True
                  "no"   -> False
                  "ask"  -> logs a message, waits *timeout* seconds, then defaults to True
            timeout: Seconds to wait for dialog to appear

        Returns:
            True if dialog was handled, False otherwise
        """
        try:
            import pyautogui
        except ImportError:
            self._log("pyautogui not installed. Cannot handle recovery dialog.", "WARN")
            self._log("Install with: pip install pyautogui", "INFO")
            return False

        # Resolve reopen_project from config if not explicitly passed
        if reopen_project is None:
            if self.recovery_action == "no":
                reopen_project = False
            elif self.recovery_action == "ask":
                self._log("Recovery dialog: waiting for user decision (will default to Yes on timeout)...", "INFO")
                # In "ask" mode we just wait and default to yes
                reopen_project = True
            else:
                reopen_project = True

        self._log(f"Looking for recovery dialog (action={'Yes' if reopen_project else 'No'})...", "INFO")
        start_time = time.time()

        while (time.time() - start_time) < timeout:
            try:
                import pygetwindow as gw

                # Find Ableton window
                windows = gw.getWindowsWithTitle('Ableton Live')
                if not windows:
                    windows = gw.getWindowsWithTitle('Recover')

                if windows:
                    window = windows[0]

                    # Check if this looks like a dialog (small window)
                    if window.height < 300 and window.width < 600:
                        self._log("Found potential recovery dialog", "INFO")

                        # Activate window
                        window.activate()
                        time.sleep(0.5)

                        if reopen_project:
                            # Yes is the default button — just press Enter
                            pyautogui.press('enter')
                            self._log("Sent Enter to accept recovery (Yes)", "OK")
                        else:
                            # Need to select "No" and confirm.
                            # Strategy 1: Tab to No button, then Enter
                            pyautogui.press('tab')
                            time.sleep(0.2)
                            pyautogui.press('enter')
                            self._log("Sent Tab+Enter to decline recovery (No)", "OK")

                            # Strategy 2 (fallback): Alt+N is a common accelerator for No
                            # We do this after a short pause as a safety net in case
                            # Tab+Enter didn't land on No.
                            time.sleep(0.5)
                            # Check if dialog is still there
                            remaining_windows = gw.getWindowsWithTitle('Ableton Live')
                            still_dialog = any(
                                w.height < 300 and w.width < 600
                                for w in remaining_windows
                            )
                            if still_dialog:
                                self._log("Dialog still present, trying Alt+N fallback", "WARN")
                                remaining_windows[0].activate()
                                time.sleep(0.3)
                                pyautogui.hotkey('alt', 'n')
                                self._log("Sent Alt+N fallback", "INFO")

                        time.sleep(2)
                        return True

            except Exception as e:
                self._log(f"Error checking for dialog: {e}", "WARN")

            time.sleep(0.5)

        self._log("No recovery dialog detected (or it auto-dismissed)", "INFO")
        return False

    def restart_ableton(self,
                        reopen_project: bool = True,
                        force_kill: bool = False,
                        handle_recovery: bool = True) -> bool:
        """
        Restart Ableton (close if running, then launch)

        Args:
            reopen_project: If recovery dialog appears, True=Yes False=No
            force_kill: Force kill process if it won't close gracefully
            handle_recovery: Automatically handle recovery dialog

        Returns:
            True if restart successful
        """
        self._log("Restarting Ableton...", "INFO")

        # Close existing instance
        if not self.close_ableton(force=force_kill):
            return False

        # Launch Ableton
        if not self.launch_ableton(wait_for_ready=True):
            return False

        # Handle recovery dialog if requested
        if handle_recovery:
            self.handle_recovery_dialog(reopen_project=reopen_project, timeout=10.0)

        return True

    def ensure_ableton_running(self, restart_on_crash: bool = True) -> bool:
        """
        Ensure Ableton is running, launch or restart if needed

        Args:
            restart_on_crash: Automatically restart if crash detected

        Returns:
            True if Ableton is running
        """
        # Check if running
        is_running, pid = self.is_ableton_running()

        if is_running:
            self._log(f"Ableton is running (PID: {pid})", "OK")
            self._last_known_pid = pid
            return True

        # Check if this was a crash
        if self._last_known_pid:
            self._log("Ableton was running but now it's not (crash detected)", "ERROR")
            if restart_on_crash:
                return self.restart_ableton(handle_recovery=True)
            return False

        # Launch new instance
        return self.launch_ableton(wait_for_ready=True)


# Singleton instance
_ableton_manager: Optional[AbletonProcessManager] = None


def get_ableton_manager(**kwargs) -> AbletonProcessManager:
    """Get the singleton Ableton Process Manager"""
    global _ableton_manager
    if _ableton_manager is None:
        _ableton_manager = AbletonProcessManager(**kwargs)
    return _ableton_manager


if __name__ == "__main__":
    # Test the manager
    manager = AbletonProcessManager(verbose=True)

    print("\n=== Testing Ableton Process Manager ===\n")

    # Check if running
    is_running, pid = manager.is_ableton_running()
    print(f"Ableton running: {is_running} (PID: {pid})")

    if not is_running:
        print("\nLaunching Ableton...")
        success = manager.launch_ableton()
        print(f"Launch result: {success}")

    print("\nManager test complete")
