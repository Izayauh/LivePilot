
import argparse
import subprocess
import time
import os
import sys
import json
from datetime import datetime

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def take_screenshot(monitor_index=2, output_file="screenshot.png"):
    """
    Take a screenshot of a specific monitor using PowerShell.
    monitor_index is 0-based (0 = Monitor 1, 2 = Monitor 3).
    """
    ps_command = f"""
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    $screens = [System.Windows.Forms.Screen]::AllScreens
    if ($screens.Count -le {monitor_index}) {{
        Write-Error "Monitor index {monitor_index} out of range (Found $($screens.Count) screens)"
        exit 1
    }}
    $screen = $screens[{monitor_index}]
    $bmp = New-Object System.Drawing.Bitmap $screen.Bounds.Width, $screen.Bounds.Height
    $graphics = [System.Drawing.Graphics]::FromImage($bmp)
    $graphics.CopyFromScreen($screen.Bounds.X, $screen.Bounds.Y, 0, 0, $bmp.Size)
    $bmp.Save("{output_file}")
    """
    try:
        subprocess.run(["powershell", "-Command", ps_command], check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Screenshot failed: {e.stderr.decode().strip()}")
        return False

def run_test(track_index=0, dry_run=False):
    """Run the apply_vocal_preset script and capture output."""
    cmd = [
        sys.executable, 
        "scripts/apply_vocal_preset.py",
        "--track", str(track_index)
    ]
    if dry_run:
        cmd.append("--dry-run")
        
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result
    except Exception as e:
        return None

def main():
    parser = argparse.ArgumentParser(description="Live Verification Loop for Ableton Preset Testing")
    parser.add_argument("--track", type=int, default=0, help="Track index to test on")
    parser.add_argument("--monitor", type=int, default=2, help="Monitor index for screenshot (0-based, default 2 for Monitor 3)")
    args = parser.parse_args()

    print("=== Live Verification Loop ===")
    print(f"Target Track: {args.track}")
    print(f"Screenshot Monitor: {args.monitor} (Monitor {args.monitor + 1})")
    
    while True:
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"\n[{timestamp}] Running test...")
        
        result = run_test(track_index=args.track)
        
        if result and result.returncode == 0:
            print(f"[{timestamp}] SUCCESS - Preset Applied")
            status = "SUCCESS"
        else:
            print(f"[{timestamp}] FAILURE - Script Error")
            status = "FAILURE"
            if result:
                # Print the error output to help debugging
                print("\n--- Error Output ---")
                print(result.stdout) # often errors are in stdout due to print statements
                print(result.stderr)
                print("--------------------")

        # Take screenshot
        screenshot_filename = f"verification_{int(time.time())}.png"
        if take_screenshot(args.monitor, screenshot_filename):
            print(f"[{timestamp}] Screenshot saved: {screenshot_filename}")
        
        print(f"\n[{timestamp}] Status: {status}")
        input("Press Enter to re-run test (or Ctrl+C to exit)...")
        clear_screen()

if __name__ == "__main__":
    main()
