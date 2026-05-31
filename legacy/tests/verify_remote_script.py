"""
Verify JarvisDeviceLoader remote script is installed and accessible.

This checks:
1. If the remote script exists in the correct location
2. If Ableton can find it
3. Provides installation instructions if missing
"""

import os
import sys

def check_remote_script_installation():
    """Check if JarvisDeviceLoader is in the correct location"""

    print("="*80)
    print("JARVIS DEVICE LOADER - INSTALLATION VERIFICATION")
    print("="*80)

    # Check local remote script
    local_script = os.path.join(os.path.dirname(__file__), "ableton_remote_script", "JarvisDeviceLoader")

    print(f"\n1. Checking local remote script at:")
    print(f"   {local_script}")

    if os.path.exists(local_script):
        print("   [OK] Local remote script exists")

        # Check for __init__.py
        init_file = os.path.join(local_script, "__init__.py")
        if os.path.exists(init_file):
            print(f"   [OK] __init__.py exists ({os.path.getsize(init_file)} bytes)")
        else:
            print("   [FAIL] Missing __init__.py")
    else:
        print("   [FAIL] Local remote script NOT found!")
        return False

    # Check Ableton's Remote Scripts directory
    appdata = os.environ.get('APPDATA', '')
    if appdata:
        ableton_remote_scripts = os.path.join(appdata, "Ableton", "Live 11", "Preferences", "User Remote Scripts")

        print(f"\n2. Checking Ableton's User Remote Scripts at:")
        print(f"   {ableton_remote_scripts}")

        if os.path.exists(ableton_remote_scripts):
            print("   [OK] Ableton User Remote Scripts folder exists")

            # Check if JarvisDeviceLoader is installed there
            installed_script = os.path.join(ableton_remote_scripts, "JarvisDeviceLoader")
            if os.path.exists(installed_script):
                print("   [OK] JarvisDeviceLoader is installed in Ableton")

                # Check if __init__.py has recent changes
                init_file = os.path.join(installed_script, "__init__.py")
                if os.path.exists(init_file):
                    import time
                    mtime = os.path.getmtime(init_file)
                    mtime_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(mtime))
                    print(f"   [OK] __init__.py last modified: {mtime_str}")

                    # Check if it has the new track type endpoint
                    with open(init_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                        if '_handle_get_track_type' in content:
                            print("   [OK] Remote script has track type query endpoint (UPDATED)")
                        else:
                            print("   [FAIL] Remote script MISSING track type endpoint (NEEDS UPDATE)")
                            return False
            else:
                print("   [FAIL] JarvisDeviceLoader NOT installed in Ableton")
                return False
        else:
            print("   [FAIL] Ableton User Remote Scripts folder NOT found")
            print("\n   Alternative locations to check:")
            print("   - C:\\ProgramData\\Ableton\\Live 11\\Resources\\MIDI Remote Scripts")
            return False

    print("\n3. Checking Ableton configuration:")
    print("   Please manually verify in Ableton Live:")
    print("   - Open Preferences > MIDI")
    print("   - Check 'Control Surface' dropdown")
    print("   - Should see 'JarvisDeviceLoader' listed")
    print("   - If not, you need to restart Ableton")

    return True

def provide_installation_instructions():
    """Provide step-by-step installation instructions"""

    print("\n" + "="*80)
    print("INSTALLATION INSTRUCTIONS")
    print("="*80)

    local_script = os.path.join(os.path.dirname(__file__), "ableton_remote_script", "JarvisDeviceLoader")
    appdata = os.environ.get('APPDATA', '')
    dest = os.path.join(appdata, "Ableton", "Live 11", "Preferences", "User Remote Scripts", "JarvisDeviceLoader")

    print("\nTo install JarvisDeviceLoader:")
    print("\n1. Copy the entire folder:")
    print(f"   FROM: {local_script}")
    print(f"   TO:   {dest}")

    print("\n2. Or run this command in PowerShell/CMD:")
    print(f'   xcopy /E /I "{local_script}" "{dest}"')

    print("\n3. Restart Ableton Live completely (close and reopen)")

    print("\n4. In Ableton Live:")
    print("   - Go to Preferences > MIDI")
    print("   - In 'Control Surface' dropdown, select 'JarvisDeviceLoader'")
    print("   - Set Input/Output to 'None'")

    print("\n5. Verify installation:")
    print("   - The Log.txt in this directory should show OSC listener starting on port 11002")

    print("\n" + "="*80)

if __name__ == "__main__":
    print("\nVerifying JarvisDeviceLoader installation...\n")

    is_installed = check_remote_script_installation()

    if not is_installed:
        print("\n" + "!"*80)
        print("INSTALLATION REQUIRED")
        print("!"*80)
        provide_installation_instructions()
        sys.exit(1)
    else:
        print("\n" + "="*80)
        print("[OK] INSTALLATION VERIFIED")
        print("="*80)
        print("\nJarvisDeviceLoader appears to be correctly installed.")
        print("\nIf tests still fail:")
        print("1. Restart Ableton Live (close and reopen)")
        print("2. Check Ableton Preferences > MIDI > Control Surface")
        print("3. Run: python test_chain_execution_fixes.py")
        sys.exit(0)
