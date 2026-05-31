"""Quick sanity test for the frequency normalization fix."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ableton_controls.reliable_params import smart_normalize_parameter

tests = [
    ("Band 1 Frequency", 95,    "EQ Eight"),
    ("Band 2 Frequency", 300,   "EQ Eight"),
    ("Band 5 Frequency", 4800,  "EQ Eight"),
    ("Band 8 Frequency", 12500, "EQ Eight"),
    ("Frequency",        7000,  "Saturator"),
    ("Filter Low",       220,   "Delay"),
    ("Filter High",      6500,  "Delay"),
]

print("=" * 60)
print("Frequency Normalization Fix - Sanity Test")
print("=" * 60)
for name, hz, device in tests:
    norm, method = smart_normalize_parameter(name, hz, device, 0.0, 1.0)
    ok = "PASS" if method == "freq_log" else "FAIL"
    print(f"  [{ok}] {device:15s} {name:20s} {hz:>6} Hz -> {norm:.4f}  ({method})")

print()
print("If all show 'freq_log' and normalized values between 0-1, the fix works.")
