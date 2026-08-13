"""
Test script for the centralized logging system.

This script tests that:
1. The logging system initializes correctly
2. Logs are written to logs/jarvis.log
3. Console output works
4. Different log levels work correctly
5. The custom log() function works
"""

import os
import sys
import logging
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Import logging configuration
from logging_config import setup_logging

# Setup logging
print("=" * 80)
print("Testing Jarvis Logging System")
print("=" * 80)

# Initialize logging
setup_logging()

# Test 1: Module-specific logger
print("\n[TEST 1] Testing module-specific logger...")
test_logger = logging.getLogger("jarvis.test")
test_logger.debug("This is a DEBUG message (should appear in file only)")
test_logger.info("This is an INFO message (should appear in both console and file)")
test_logger.warning("This is a WARNING message")
test_logger.error("This is an ERROR message")

# Test 2: Custom log() function from jarvis_engine
print("\n[TEST 2] Testing custom log() function...")

# Simulate the custom log function
def log(msg, level="INFO"):
    """Simulated log function from jarvis_engine"""
    logger = logging.getLogger("jarvis.engine")

    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARN": logging.WARNING,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "STATE": logging.INFO,
    }

    log_level = level_map.get(level.upper(), logging.INFO)

    if level == "ERROR":
        msg = f"❌ {msg}"
    elif level == "STATE":
        msg = f"📊 {msg}"
    elif level == "DEBUG":
        msg = f"[DBG] {msg}"
    elif level == "WARN":
        msg = f"[WARN] {msg}"

    logger.log(log_level, msg)

log("Testing custom log() function - INFO level")
log("Testing custom log() function - DEBUG level", "DEBUG")
log("Testing custom log() function - WARN level", "WARN")
log("Testing custom log() function - ERROR level", "ERROR")
log("Testing custom log() function - STATE level", "STATE")

# Test 3: Verify log file exists
print("\n[TEST 3] Verifying log file...")
log_file = project_root / "logs" / "jarvis.log"

if log_file.exists():
    print(f"✅ Log file created: {log_file}")

    # Count lines in log file
    with open(log_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    print(f"✅ Log file contains {len(lines)} lines")

    # Show last 10 lines
    print("\n[TEST 4] Last 10 lines of log file:")
    print("-" * 80)
    for line in lines[-10:]:
        print(line, end='')
    print("-" * 80)
else:
    print(f"❌ Log file NOT found: {log_file}")

# Test 5: Multiple module loggers
print("\n[TEST 5] Testing multiple module loggers...")
engine_logger = logging.getLogger("jarvis.engine")
research_logger = logging.getLogger("jarvis.research")
controls_logger = logging.getLogger("jarvis.ableton_controls")

engine_logger.info("Message from engine module")
research_logger.info("Message from research module")
controls_logger.info("Message from ableton_controls module")

print("\n" + "=" * 80)
print("Logging Test Complete!")
print("=" * 80)
print(f"\nLog file location: {log_file.absolute()}")
print("\nYou can view logs with:")
print("  python scripts/view_logs.py")
print("  python scripts/view_logs.py --level ERROR")
print("  python scripts/view_logs.py --follow")
