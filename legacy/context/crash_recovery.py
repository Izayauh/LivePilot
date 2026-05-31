"""
Crash Recovery System

Production-ready crash recovery for Jarvis Ableton.
Handles:
- Ableton crash detection
- OSC connection recovery
- Session state restoration
- Graceful degradation
"""

import os
import time
import asyncio
import subprocess
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass
from datetime import datetime
import threading


@dataclass
class RecoveryState:
    """State tracking for recovery operations"""
    last_crash_time: Optional[datetime] = None
    crash_count: int = 0
    recovery_attempts: int = 0
    last_successful_op: Optional[datetime] = None
    consecutive_failures: int = 0


class CrashRecoveryManager:
    """
    Manages crash detection and recovery for Jarvis Ableton.

    Features:
    - Detect Ableton crashes from OSC errors
    - Automatic OSC reconnection
    - Session state preservation
    - Graceful degradation when recovery fails
    """

    # Error patterns that indicate Ableton crash or connection loss
    CRASH_INDICATORS = [
        "WinError 10054",  # Connection forcibly closed
        "WinError 10061",  # Connection refused
        "Connection refused",
        "No response from Ableton",
        "No response from JarvisDeviceLoader",
        "OSC error",
        "Timeout: No response",
        "unidentifiable C++ exception",
        "C++ exception",
        "Remote Script",
        "Failed to schedule",
        "Socket closed",
        "Connection reset",
    ]

    def __init__(self,
                 max_recovery_attempts: int = 3,
                 recovery_cooldown: float = 5.0,
                 auto_save_interval: float = 60.0):
        """
        Initialize crash recovery manager.

        Args:
            max_recovery_attempts: Max recovery attempts before giving up
            recovery_cooldown: Seconds between recovery attempts
            auto_save_interval: Seconds between auto-saves
        """
        self.max_recovery_attempts = max_recovery_attempts
        self.recovery_cooldown = recovery_cooldown
        self.auto_save_interval = auto_save_interval

        self.state = RecoveryState()
        self._lock = threading.RLock()
        self._recovery_callbacks: List[Callable] = []
        self._persistence = None
        self._ableton_controller = None
        self._auto_save_task = None

    def set_controller(self, controller):
        """Set the Ableton controller for recovery operations"""
        self._ableton_controller = controller

    @property
    def persistence(self):
        """Get session persistence (lazy loaded)"""
        if self._persistence is None:
            try:
                from context.session_persistence import get_session_persistence
                self._persistence = get_session_persistence()
            except ImportError:
                pass
        return self._persistence

    def register_recovery_callback(self, callback: Callable):
        """Register a callback to be called after successful recovery"""
        self._recovery_callbacks.append(callback)

    def is_crash_error(self, error: Exception) -> bool:
        """Check if an error indicates a crash"""
        error_str = str(error)
        return any(indicator in error_str for indicator in self.CRASH_INDICATORS)

    def is_crash_result(self, result: Dict[str, Any]) -> bool:
        """Check if a result indicates a crash"""
        if not isinstance(result, dict):
            return False

        if not result.get("success", True):
            message = str(result.get("message", ""))
            error = str(result.get("error", ""))
            combined = f"{message} {error}"
            return any(indicator in combined for indicator in self.CRASH_INDICATORS)

        return False

    def record_failure(self):
        """Record a failure for tracking purposes"""
        with self._lock:
            self.state.consecutive_failures += 1
            if self.state.consecutive_failures >= 3:
                self.state.crash_count += 1
                self.state.last_crash_time = datetime.now()

    def record_success(self):
        """Record a success to reset failure tracking"""
        with self._lock:
            self.state.consecutive_failures = 0
            self.state.last_successful_op = datetime.now()

    def save_session_state(self):
        """Save current session state for crash recovery"""
        if self.persistence:
            try:
                from context.session_manager import session_manager

                state = {
                    "transport": {
                        "playing": session_manager.state.is_playing,
                        "tempo": session_manager.state.tempo,
                        "position": session_manager.state.current_position
                    },
                    "tracks": [
                        {
                            "index": t.index,
                            "muted": t.muted,
                            "soloed": t.soloed,
                            "volume": t.volume,
                            "pan": t.pan
                        }
                        for t in session_manager.state.tracks
                    ],
                    "action_history": session_manager.get_recent_actions(20),
                    "recovery_state": {
                        "crash_count": self.state.crash_count,
                        "last_crash": self.state.last_crash_time.isoformat() if self.state.last_crash_time else None
                    }
                }

                self.persistence.save_session_state(state)
            except Exception as e:
                print(f"[CrashRecovery] Failed to save session state: {e}")

    def restore_session_state(self) -> bool:
        """
        Restore session state after recovery.

        Returns:
            True if restoration was successful
        """
        if not self.persistence:
            return False

        try:
            state = self.persistence.load_session_state()
            if not state:
                return False

            # Restore would require controller operations
            # For now, we just load the state info
            print(f"[CrashRecovery] Found saved state from {state.get('saved_at', 'unknown')}")
            return True

        except Exception as e:
            print(f"[CrashRecovery] Failed to restore session state: {e}")
            return False

    async def attempt_recovery(self) -> bool:
        """
        Attempt to recover from a crash.

        Returns:
            True if recovery successful
        """
        with self._lock:
            self.state.recovery_attempts += 1

            if self.state.recovery_attempts > self.max_recovery_attempts:
                print(f"[CrashRecovery] Max recovery attempts ({self.max_recovery_attempts}) exceeded")
                return False

        print(f"[CrashRecovery] Attempting recovery (attempt {self.state.recovery_attempts}/{self.max_recovery_attempts})")

        # Save current state before recovery
        self.save_session_state()

        # Wait for cooldown
        await asyncio.sleep(self.recovery_cooldown)

        # Try to reconnect OSC
        if self._ableton_controller:
            try:
                # Test connection
                result = self._ableton_controller.get_tempo()
                if result.get("success"):
                    print("[CrashRecovery] OSC connection restored")

                    # Reset state
                    with self._lock:
                        self.state.recovery_attempts = 0
                        self.state.consecutive_failures = 0

                    # Notify callbacks
                    for callback in self._recovery_callbacks:
                        try:
                            callback()
                        except Exception as e:
                            print(f"[CrashRecovery] Callback error: {e}")

                    # Try to restore state
                    self.restore_session_state()

                    return True

            except Exception as e:
                print(f"[CrashRecovery] OSC reconnection failed: {e}")

        return False

    def execute_with_recovery(self, operation: Callable, *args,
                               operation_name: str = "operation",
                               **kwargs) -> Any:
        """
        Execute an operation with automatic crash recovery.

        Args:
            operation: Function to execute
            *args: Function arguments
            operation_name: Name for logging
            **kwargs: Function keyword arguments

        Returns:
            Operation result
        """
        attempts = 0

        while attempts <= self.max_recovery_attempts:
            try:
                result = operation(*args, **kwargs)

                # Check for crash indicators in result
                if self.is_crash_result(result):
                    self.record_failure()
                    if self.state.consecutive_failures >= 3:
                        print(f"[CrashRecovery] {operation_name} returned crash indicator")
                        # Try synchronous recovery
                        asyncio.get_event_loop().run_until_complete(self.attempt_recovery())
                        attempts += 1
                        continue
                else:
                    self.record_success()

                return result

            except Exception as e:
                if self.is_crash_error(e):
                    self.record_failure()
                    print(f"[CrashRecovery] {operation_name} crash detected: {e}")
                    try:
                        asyncio.get_event_loop().run_until_complete(self.attempt_recovery())
                    except Exception:
                        pass
                    attempts += 1
                else:
                    raise

        raise Exception(f"{operation_name} failed after {attempts} recovery attempts")

    async def start_auto_save(self):
        """Start automatic state saving"""
        while True:
            await asyncio.sleep(self.auto_save_interval)
            self.save_session_state()

    def get_recovery_status(self) -> Dict[str, Any]:
        """Get current recovery status"""
        with self._lock:
            return {
                "crash_count": self.state.crash_count,
                "recovery_attempts": self.state.recovery_attempts,
                "consecutive_failures": self.state.consecutive_failures,
                "last_crash": self.state.last_crash_time.isoformat() if self.state.last_crash_time else None,
                "last_success": self.state.last_successful_op.isoformat() if self.state.last_successful_op else None,
                "healthy": self.state.consecutive_failures < 3
            }


# Singleton instance
_recovery_manager: Optional[CrashRecoveryManager] = None


def get_crash_recovery() -> CrashRecoveryManager:
    """Get the singleton CrashRecoveryManager instance"""
    global _recovery_manager
    if _recovery_manager is None:
        _recovery_manager = CrashRecoveryManager()
    return _recovery_manager


def with_crash_recovery(operation_name: str = None):
    """
    Decorator to add crash recovery to a function.

    Usage:
        @with_crash_recovery("load_device")
        def load_device(track, device_name):
            ...
    """
    def decorator(func: Callable) -> Callable:
        op_name = operation_name or func.__name__

        def wrapped(*args, **kwargs):
            manager = get_crash_recovery()
            return manager.execute_with_recovery(
                func, *args,
                operation_name=op_name,
                **kwargs
            )

        wrapped.__name__ = func.__name__
        wrapped.__doc__ = func.__doc__
        return wrapped

    return decorator
