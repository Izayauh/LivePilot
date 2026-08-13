"""Test the custom EQ parameter parsing."""
import sys
try:
    sys.stdout.reconfigure(encoding='utf-8')
except:
    pass

from discovery.device_intelligence import get_device_intelligence

di = get_device_intelligence()

tests = [
    "presence boost at 7kHz +3dB",
    "high pass at 80Hz",
    "cut 300Hz by 4dB with narrow Q",
    "+3dB at 7k",
    "boost 2.5kHz +2dB wide Q",
    "high shelf at 10kHz +2dB",
]

for test in tests:
    print(f"\n{'='*60}")
    print(f"INPUT: {test}")
    result = di.parse_eq_request(test)
    print(f"SUCCESS: {result.get('success')}")
    if result.get('success'):
        print(f"DESCRIPTION: {result.get('description')}")
        print(f"BANDS USED: {result.get('bands_used')}")
        print(f"SETTINGS: {result.get('settings')}")
    else:
        print(f"ERROR: {result.get('message')}")
        print(f"HINT: {result.get('hint', '')}")
