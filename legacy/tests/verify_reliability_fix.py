
import time
import random
from ableton_controls import ableton
from ableton_controls.reliable_params import ReliableParameterController

def verify_reliability_fix():
    print("Initializing ReliableParameterController...")
    reliable = ReliableParameterController(ableton, verbose=True)
    
    track_index = 0
    device_index = 0
    
    print(f"\nTargeting Track {track_index + 1}, Device {device_index + 1}")
    
    # Wait for device to be ready
    print("Waiting for device to be ready...")
    if not reliable.wait_for_device_ready(track_index, device_index):
        print("ERROR: Device not ready or not found.")
        return

    # Find a suitable parameter to test (normalized 0-1 param preferred)
    # Let's try to find "Dry/Wet" or similar, or just pick the first one
    info = reliable.get_device_info(track_index, device_index)
    if not info or not info.param_names:
        print("ERROR: No parameters found.")
        return

    test_param_idx = 1 # Default to param 1
    
    # Try to find a specific parameter that is usually safe to modulate
    search_params = ["dry/wet", "amount", "drive", "frequency", "gain", "threshold"]
    for name in search_params:
        idx = reliable.find_parameter_index(track_index, device_index, name)
        if idx is not None:
            test_param_idx = idx
            break
            
    param_name = info.param_names[test_param_idx]
    pmin = info.param_mins[test_param_idx]
    pmax = info.param_maxs[test_param_idx]
    
    print(f"\nTesting Parameter: '{param_name}' (Index {test_param_idx})")
    print(f"Range: {pmin} to {pmax}")
    
    num_tests = 20
    success_count = 0
    retry_count = 0
    
    print(f"\nStarting Stress Test ({num_tests} iterations)...")
    
    for i in range(num_tests):
        # Generate random value within range
        target_val = random.uniform(pmin, pmax)
        
        print(f"\n--- Iteration {i+1}/{num_tests}: Set to {target_val:.4f} ---")
        
        start_time = time.time()
        result = reliable.set_parameter_verified(
            track_index, device_index, test_param_idx, target_val
        )
        duration = time.time() - start_time
        
        if result["success"]:
            print(f"SUCCESS in {duration:.3f}s (Attempts: {result['attempts']})")
            success_count += 1
            if result["attempts"] > 1:
                retry_count += 1
                print("  -> REQUIRED RETRIES")
        else:
            print(f"FAILURE: {result['message']}")
            
        time.sleep(0.1) # Short gap
        
    print("\n" + "="*50)
    print("RESULTS")
    print("="*50)
    print(f"Total Tests: {num_tests}")
    print(f"Successes: {success_count}")
    print(f"Failures: {num_tests - success_count}")
    print(f"Retries Required: {retry_count}")
    print(f"Success Rate: {(success_count/num_tests)*100:.1f}%")
    print(f"First-Try Success Rate: {((success_count - retry_count)/num_tests)*100:.1f}%")

if __name__ == "__main__":
    verify_reliability_fix()
