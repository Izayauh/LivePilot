"""
Crash-Resilient Wrapper for Ableton OSC Operations

Wraps OSC operations to detect Ableton crashes and automatically recover.
"""

import time
import socket
from typing import Callable, Dict, Any, Optional
from ableton_controls.process_manager import get_ableton_manager


class AbletonCrashDetector:
    """Detects Ableton crashes from OSC errors and manages recovery"""
    
    # Error patterns that indicate Ableton has crashed or Remote Script has failed
    CRASH_INDICATORS = [
        "WinError 10054",  # Connection forcibly closed (socket died)
        "WinError 10061",  # Connection refused (no listener)
        "Connection refused",
        "No response from Ableton",
        "No response from JarvisDeviceLoader",  # Remote Script not responding
        "OSC error",
        "Timeout: No response",
        "unidentifiable C++ exception",  # Thread safety issue in Remote Script
        "C++ exception",  # Generic C++ crash
        "Remote Script",  # Generic Remote Script error
        "Failed to schedule",  # Failed to schedule on main thread
    ]
    
    def __init__(self, 
                 auto_recover: bool = True,
                 max_recovery_attempts: int = 3,
                 recovery_wait: float = 20.0,
                 verbose: bool = True):
        """
        Initialize crash detector
        
        Args:
            auto_recover: Automatically restart Ableton on crash
            max_recovery_attempts: Maximum recovery attempts before giving up
            recovery_wait: Seconds to wait after recovery before retrying operation
            verbose: Print status messages
        """
        self.auto_recover = auto_recover
        self.max_recovery_attempts = max_recovery_attempts
        self.recovery_wait = recovery_wait
        self.verbose = verbose
        
        self.ableton_manager = get_ableton_manager(verbose=verbose)
        self.crash_count = 0
        self.last_crash_time = 0
        
    def _log(self, message: str, level: str = "INFO"):
        """Log message if verbose"""
        if self.verbose:
            emoji = {"INFO": "ℹ️", "WARN": "⚠️", "ERROR": "❌", "OK": "✅", "CRASH": "💥"}
            print(f"{emoji.get(level, 'ℹ️')} [{level}] {message}")
    
    def is_crash_error(self, error: Exception) -> bool:
        """
        Check if an error indicates an Ableton crash
        
        Args:
            error: Exception to check
            
        Returns:
            True if error indicates crash
        """
        error_str = str(error)
        return any(indicator in error_str for indicator in self.CRASH_INDICATORS)
    
    def is_crash_result(self, result: Dict[str, Any]) -> bool:
        """
        Check if a result dictionary indicates a crash
        
        Args:
            result: Result dictionary to check
            
        Returns:
            True if result indicates crash
        """
        if not isinstance(result, dict):
            return False
        
        # Check success flag
        if not result.get("success", True):
            message = result.get("message", "")
            error = result.get("error", "")
            combined = f"{message} {error}"
            return any(indicator in combined for indicator in self.CRASH_INDICATORS)
        
        return False
    
    def verify_ableton_running(self) -> bool:
        """
        Verify Ableton is actually running
        
        Returns:
            True if Ableton is running
        """
        is_running, pid = self.ableton_manager.is_ableton_running()
        if not is_running:
            self._log("Ableton is not running!", "CRASH")
            return False
        return True
    
    def recover_from_crash(self) -> bool:
        """
        Attempt to recover from an Ableton crash
        
        Returns:
            True if recovery successful
        """
        self.crash_count += 1
        self.last_crash_time = time.time()
        
        self._log(f"💥 CRASH DETECTED (attempt {self.crash_count}/{self.max_recovery_attempts})", "CRASH")
        
        if self.crash_count > self.max_recovery_attempts:
            self._log(f"Maximum recovery attempts ({self.max_recovery_attempts}) exceeded", "ERROR")
            return False
        
        if not self.auto_recover:
            self._log("Auto-recovery disabled. Please restart Ableton manually.", "WARN")
            return False
        
        # Attempt recovery
        self._log("Attempting to restart Ableton...", "INFO")
        
        success = self.ableton_manager.restart_ableton(
            force_kill=True,
            handle_recovery=True
        )
        
        if not success:
            self._log("Failed to restart Ableton", "ERROR")
            return False
        
        # Wait for Ableton to be fully ready
        self._log(f"Waiting {self.recovery_wait}s for Ableton to stabilize...", "INFO")
        time.sleep(self.recovery_wait)
        
        # Verify it's running
        if not self.verify_ableton_running():
            self._log("Ableton still not running after recovery attempt", "ERROR")
            return False
        
        # Test OSC connection
        self._log("Testing OSC connection...", "INFO")
        try:
            from tests.chain_test_utils import create_reliable_controller
            reliable = create_reliable_controller(verbose=False)
            # Try a simple operation
            from tests.chain_test_utils import get_device_count
            count = get_device_count(0)
            self._log(f"OSC connection OK (device count: {count})", "OK")
        except Exception as e:
            self._log(f"OSC connection test failed: {e}", "ERROR")
            return False
        
        self._log("✅ Recovery successful!", "OK")
        self.crash_count = 0  # Reset counter on successful recovery
        return True
    
    def execute_with_recovery(self, 
                              operation: Callable,
                              *args,
                              operation_name: str = "operation",
                              **kwargs) -> Any:
        """
        Execute an operation with automatic crash recovery
        
        Args:
            operation: Function to execute
            *args: Arguments for the function
            operation_name: Name for logging
            **kwargs: Keyword arguments for the function
            
        Returns:
            Result of the operation
            
        Raises:
            Exception: If operation fails after all recovery attempts
        """
        attempts = 0
        max_attempts = self.max_recovery_attempts + 1
        
        while attempts < max_attempts:
            try:
                # Check Ableton is running before attempting
                if not self.verify_ableton_running():
                    if not self.recover_from_crash():
                        raise Exception("Ableton not running and recovery failed")
                
                # Execute operation
                result = operation(*args, **kwargs)
                
                # Check if result indicates crash
                if self.is_crash_result(result):
                    self._log(f"{operation_name} returned crash indicator", "WARN")
                    
                    # Verify if actually crashed
                    if not self.verify_ableton_running():
                        if not self.recover_from_crash():
                            return result  # Return failure result
                        attempts += 1
                        continue  # Retry after recovery
                
                # Success!
                return result
                
            except Exception as e:
                self._log(f"{operation_name} raised exception: {e}", "ERROR")
                
                # Check if this is a crash error
                if self.is_crash_error(e):
                    # Verify if actually crashed
                    if not self.verify_ableton_running():
                        if not self.recover_from_crash():
                            raise
                        attempts += 1
                        continue  # Retry after recovery
                
                # Not a crash error, re-raise
                raise
        
        raise Exception(f"{operation_name} failed after {max_attempts} attempts including recovery")
    
    def wrap_osc_call(self, func: Callable, operation_name: str = None) -> Callable:
        """
        Create a crash-resilient wrapper for an OSC function
        
        Args:
            func: Function to wrap
            operation_name: Name for logging (defaults to function name)
            
        Returns:
            Wrapped function with automatic recovery
        """
        op_name = operation_name or func.__name__
        
        def wrapped(*args, **kwargs):
            return self.execute_with_recovery(
                func, *args, 
                operation_name=op_name,
                **kwargs
            )
        
        wrapped.__name__ = f"crash_resilient_{func.__name__}"
        wrapped.__doc__ = f"Crash-resilient wrapper for {func.__name__}"
        
        return wrapped


# Global crash detector instance
_crash_detector: Optional[AbletonCrashDetector] = None


def get_crash_detector(**kwargs) -> AbletonCrashDetector:
    """Get the singleton crash detector"""
    global _crash_detector
    if _crash_detector is None:
        _crash_detector = AbletonCrashDetector(**kwargs)
    return _crash_detector


def with_crash_recovery(operation_name: str = None):
    """
    Decorator to add crash recovery to a function
    
    Usage:
        @with_crash_recovery("load_device")
        def load_device(track, device_name):
            # ... operation ...
    """
    def decorator(func: Callable) -> Callable:
        op_name = operation_name or func.__name__
        
        def wrapped(*args, **kwargs):
            detector = get_crash_detector()
            return detector.execute_with_recovery(
                func, *args,
                operation_name=op_name,
                **kwargs
            )
        
        wrapped.__name__ = func.__name__
        wrapped.__doc__ = func.__doc__
        return wrapped
    
    return decorator


if __name__ == "__main__":
    # Test the crash detector
    detector = AbletonCrashDetector(verbose=True)
    
    print("\n=== Testing Crash Detector ===\n")
    
    # Test crash detection from error message
    test_error = Exception("OSC error: [WinError 10054] Connection forcibly closed")
    is_crash = detector.is_crash_error(test_error)
    print(f"Crash error detection: {is_crash}")
    
    # Test crash detection from result
    test_result = {"success": False, "message": "No response from Ableton"}
    is_crash = detector.is_crash_result(test_result)
    print(f"Crash result detection: {is_crash}")
    
    # Test verify Ableton running
    is_running = detector.verify_ableton_running()
    print(f"Ableton running: {is_running}")
    
    print("\nCrash detector test complete")

