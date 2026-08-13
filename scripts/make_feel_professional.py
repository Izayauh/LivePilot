import time
import sys
from ableton_controls import ableton

# Force UTF-8 output encoding for stdout
sys.stdout.reconfigure(encoding='utf-8')

def parse_freq(s):
    s = s.strip().lower()
    if "khz" in s:
        return float(s.replace("khz", "").strip()) * 1000.0
    if "hz" in s:
        return float(s.replace("hz", "").strip())
    return float(s)

def parse_db(s):
    s = s.strip().lower()
    if "db" in s:
        s = s.replace("db", "").strip()
    if s == "-inf":
        return -100.0
    return float(s)

def parse_pct(s):
    s = s.strip().lower()
    if "%" in s:
        s = s.replace("%", "").strip()
    return float(s)

def calibrate_parameter(track_idx, device_idx, param_idx, target_val, parse_fn, unit_name, tolerance_pct=0.05):
    low = 0.0
    high = 1.0
    best_val = 0.5
    
    print(f"Calibrating Track {track_idx} Device {device_idx} Param {param_idx} to {target_val} {unit_name}...")
    for i in range(12):
        mid = (low + high) / 2
        ableton.set_device_parameter(track_idx, device_idx, param_idx, mid)
        time.sleep(0.04)
        ableton._last_response.clear()
        res = ableton.get_device_parameter_value_string_sync(track_idx, device_idx, param_idx)
        val_str = res.get('value_string', '')
        if not val_str:
            continue
        try:
            curr_val = parse_fn(val_str)
            # Handle 0.0 target edge case
            diff = abs(curr_val - target_val)
            threshold = max(tolerance_pct * abs(target_val), 0.1)
            
            if diff <= threshold:
                best_val = mid
                print(f"  Reached target: '{val_str}' (norm: {mid:.4f})")
                break
                
            if curr_val < target_val:
                low = mid
            else:
                high = mid
        except Exception as e:
            pass
    return best_val

def main():
    print("--- STARTING PROFESSIONAL MIX ENHANCEMENT ---")
    
    # 1. Rhodes EQ & Gloss (Track 0, Device 1 - EQ Eight)
    print("\n[Track 0 - Rhodes EQ]")
    # Enable Band 1
    ableton.set_device_parameter(0, 1, 4, 1.0) # 1 Filter On A -> On
    # Calibrate Band 1 Freq to 110 Hz (Low Cut)
    calibrate_parameter(0, 1, 6, 110.0, parse_freq, "Hz")
    
    # Enable Band 3
    ableton.set_device_parameter(0, 1, 24, 1.0) # 3 Filter On A -> On
    # Calibrate Band 3 Freq to 6000 Hz (Air Boost)
    calibrate_parameter(0, 1, 26, 6000.0, parse_freq, "Hz")
    # Calibrate Band 3 Gain to +2.0 dB
    calibrate_parameter(0, 1, 27, 2.0, parse_db, "dB")
    
    # 2. Bass Saturation & Harmonics (Track 1, Device 0 - Saturator)
    print("\n[Track 1 - Bass Saturation]")
    # Enable Soft Clip for warm analog peak limiting
    ableton.set_device_parameter(1, 0, 10, 1.0) # Soft Clip -> On
    # Calibrate Drive to +5.5 dB (subtle growl)
    calibrate_parameter(1, 0, 2, 5.5, parse_db, "dB")
    # Calibrate Output to -2.5 dB (gain staging)
    calibrate_parameter(1, 0, 3, -2.5, parse_db, "dB")
    
    # 3. Drums Dynamic Glue & Compression (Track 3, Device 0 - Glue Compressor)
    print("\n[Track 3 - Drums Glue Compressor]")
    # Set Attack to 30ms (let transients snap through)
    ableton.set_device_parameter(3, 0, 4, 1.0) 
    # Set Ratio to 4
    ableton.set_device_parameter(3, 0, 5, 0.5) 
    # Set Release to 0.1s (fast recovery for energetic groove)
    ableton.set_device_parameter(3, 0, 6, 0.0) 
    # Calibrate Dry/Wet to 80% (parallel compression for body + dynamics)
    calibrate_parameter(3, 0, 7, 80.0, parse_pct, "%")
    # Calibrate Threshold to -15.0 dB (gluing the kick and rimshot)
    calibrate_parameter(3, 0, 1, -15.0, parse_db, "dB")
    # Calibrate Makeup to +3.0 dB (boost the parallel compressed weight)
    calibrate_parameter(3, 0, 3, 3.0, parse_db, "dB")

    print("\n--- PROFESSIONAL MIX ENHANCEMENT COMPLETE ---")

if __name__ == "__main__":
    main()
