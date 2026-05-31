import pyautogui
import pygetwindow as gw
import time
import os
import sys

# 1. Fix Unicode Output Issues on Windows Console
try:
    sys.stdout.reconfigure(encoding='utf-8')
except:
    pass

def safe_print(text):
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('ascii', 'replace').decode())

def capture_ableton():
    safe_print("--- ABLETON CAPTURE PROTOCOL ---")
    
    # 2. Find Window
    target_title = "Ableton Live"
    window = None
    
    try:
        all_windows = gw.getAllWindows()
        for w in all_windows:
            # safe_print(f"Checking: {w.title}")
            if target_title in w.title:
                window = w
                break
    except Exception as e:
        safe_print(f"Window search error: {e}")

    if not window:
        safe_print("❌ Ableton window not found.")
        # Fallback: Capture full desktop anyway
        safe_print("Capturing full desktop as fallback...")
    else:
        safe_print(f"✅ Found: {window.title}")
        try:
            if window.isMinimized:
                window.restore()
                time.sleep(0.5)
            
            window.activate()
            # safe_print("Window activated.")
            time.sleep(1.0) # Wait for fade-in/repaint
        except Exception as e:
            safe_print(f"Focus warning: {e}")

    # 3. Take Screenshot
    timestamp = int(time.time())
    filename = f"ableton_verify_{timestamp}.png"
    screenshots_dir = os.path.join(os.getcwd(), "screenshots")
    os.makedirs(screenshots_dir, exist_ok=True)
    filepath = os.path.join(screenshots_dir, filename)
    
    try:
        screenshot = pyautogui.screenshot()
        screenshot.save(filepath)
        
        # Convert to WSL path for the agent
        wsl_path = filepath.replace("C:\\", "/mnt/c/").replace("\\", "/")
        safe_print(f"SNAPSHOT_SAVED: {wsl_path}")
        
    except Exception as e:
        safe_print(f"Screenshot error: {e}")

if __name__ == "__main__":
    capture_ableton()
