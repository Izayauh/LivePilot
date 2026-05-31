import pyautogui
import pygetwindow as gw
import time
import os
import sys

# 1. Fix Console Output
try:
    sys.stdout.reconfigure(encoding='utf-8')
except:
    pass

def safe_print(text):
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('ascii', 'replace').decode())

def capture_target_monitor():
    safe_print("--- TARGETED CAPTURE PROTOCOL ---")
    
    # 2. Find Window Geometry
    target_title = "Ableton Live"
    window = None
    
    try:
        all_windows = gw.getAllWindows()
        for w in all_windows:
            if target_title in w.title:
                window = w
                break
    except Exception as e:
        safe_print(f"Search error: {e}")

    if not window:
        safe_print("❌ Ableton window not found.")
        return

    safe_print(f"✅ Found: {window.title}")
    safe_print(f"   Geometry: Left={window.left}, Top={window.top}, Width={window.width}, Height={window.height}")

    # 3. Capture SPECIFIC Region
    # If the user says it's on Monitor 3, the 'left' coordinate is likely large (e.g., 3840 or -1920).
    # pyautogui.screenshot(region=(x, y, w, h))
    
    timestamp = int(time.time())
    filename = f"ableton_monitor3_{timestamp}.png"
    screenshots_dir = os.path.join(os.getcwd(), "screenshots")
    os.makedirs(screenshots_dir, exist_ok=True)
    filepath = os.path.join(screenshots_dir, filename)
    
    try:
        # Capture exactly where the window says it is
        safe_print(f"   Capturing Region: ({window.left}, {window.top}, {window.width}, {window.height})")
        
        screenshot = pyautogui.screenshot(region=(window.left, window.top, window.width, window.height))
        screenshot.save(filepath)
        
        wsl_path = filepath.replace("C:\\", "/mnt/c/").replace("\\", "/")
        safe_print(f"SNAPSHOT_SAVED: {wsl_path}")
        
    except Exception as e:
        safe_print(f"Capture error: {e}")
        # Fallback: Try capturing specific multi-monitor offsets if window geometry is misleading
        # (Sometimes minimized windows report weird coords)

if __name__ == "__main__":
    capture_target_monitor()
