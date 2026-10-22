"""Live Pilot diagnostic playbook.

The librarian indexes reference songs - how a finished record was built. This is
the other half: how to diagnose and fix what is wrong with THIS one, and how to
avoid the traps that make an agent confidently wrong about audio.

Every entry is written so an agent can act without re-deriving the lesson:

    symptom  -> what you would notice
    detect   -> how to MEASURE it, with the threshold that flags it
    why      -> the mechanism, so it generalises instead of being a rule to obey
    fix      -> concrete steps
    verify   -> how to know the fix worked
    evidence -> the run that produced the lesson, with real numbers

The library is meant to grow. Anything learned the hard way goes back in via
`record_finding` so it is never learned the hard way twice.
"""
from .playbook import (  # noqa: F401
    load_entries, search, get_entry, record_finding, brief,
)
