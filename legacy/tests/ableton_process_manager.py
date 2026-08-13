"""
Ableton Process Manager — backward-compatibility stub.

The implementation has moved to ``ableton_controls.process_manager``.
This module re-exports everything so existing imports keep working.
"""

from ableton_controls.process_manager import (  # noqa: F401
    AbletonProcessManager,
    get_ableton_manager,
)
