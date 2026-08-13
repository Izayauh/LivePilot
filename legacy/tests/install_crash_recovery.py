"""
Installation and Verification Script for Crash Recovery System

This script:
1. Checks if required dependencies are installed
2. Installs missing dependencies
3. Verifies the crash recovery system works
4. Tests Ableton detection
"""

import subprocess
import sys
import os


def check_package_installed(package_name):
    """Check if a package is installed"""
    try:
        __import__(package_name)
        return True
    except ImportError:
        return False


def install_dependencies():
    """Install required dependencies"""
    print("\n" + "=" * 60)
    print("CRASH RECOVERY SYSTEM - DEPENDENCY INSTALLATION")
    print("=" * 60 + "\n")
    
    required = {
        "psutil": "Process management",
        "pyautogui": "GUI automation",
        "pygetwindow": "Window management (for recovery dialogs)"
    }
    
    missing = []
    
    print("Checking dependencies...")
    for package, description in required.items():
        installed = check_package_installed(package)
        status = "✅ INSTALLED" if installed else "❌ MISSING"
        print(f"  {status} - {package:15} ({description})")
        if not installed:
            missing.append(package)
    
    if not missing:
        print("\n✅ All dependencies are installed!\n")
        return True
    
    print(f"\n⚠️  Missing {len(missing)} package(s): {', '.join(missing)}")
    print("\nInstalling missing dependencies...\n")
    
    try:
        # Install from requirements file
        requirements_file = "requirements_crash_recovery.txt"
        if os.path.exists(requirements_file):
            subprocess.check_call([
                sys.executable, "-m", "pip", "install", 
                "-r", requirements_file,
                "--quiet"
            ])
        else:
            # Install individually
            for package in missing:
                print(f"Installing {package}...")
                subprocess.check_call([
                    sys.executable, "-m", "pip", "install", 
                    package,
                    "--quiet"
                ])
        
        print("\n✅ Installation complete!\n")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Installation failed: {e}")
        print("\nTry manually:")
        print(f"  pip install {' '.join(missing)}")
        return False


def verify_system():
    """Verify the crash recovery system works"""
    print("\n" + "=" * 60)
    print("CRASH RECOVERY SYSTEM - VERIFICATION")
    print("=" * 60 + "\n")
    
    # Add parent directory to path
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    print("1. Testing imports...")
    try:
        from tests.ableton_process_manager import AbletonProcessManager, get_ableton_manager
        print("   ✅ AbletonProcessManager imported")
        
        from tests.crash_resilient_wrapper import AbletonCrashDetector, get_crash_detector
        print("   ✅ AbletonCrashDetector imported")
        
    except ImportError as e:
        print(f"   ❌ Import failed: {e}")
        return False
    
    print("\n2. Testing Ableton detection...")
    try:
        manager = get_ableton_manager(verbose=False)
        is_running, pid = manager.is_ableton_running()
        
        if is_running:
            print(f"   ✅ Ableton is running (PID: {pid})")
        else:
            print(f"   ⚠️  Ableton is not currently running")
            print(f"      (This is OK - system can launch it automatically)")
        
        # Check if Ableton path was found
        if manager.ableton_path:
            print(f"   ✅ Ableton path detected:")
            print(f"      {manager.ableton_path}")
        else:
            print(f"   ⚠️  Ableton path not auto-detected")
            print(f"      You can specify it manually if needed")
            
    except Exception as e:
        print(f"   ❌ Detection failed: {e}")
        return False
    
    print("\n3. Testing crash detector...")
    try:
        detector = get_crash_detector(verbose=False)
        
        # Test error detection
        test_error = Exception("OSC error: [WinError 10054] Connection closed")
        is_crash = detector.is_crash_error(test_error)
        
        if is_crash:
            print("   ✅ Crash detection logic works")
        else:
            print("   ❌ Crash detection failed")
            return False
            
    except Exception as e:
        print(f"   ❌ Crash detector test failed: {e}")
        return False
    
    print("\n" + "=" * 60)
    print("✅ ALL VERIFICATIONS PASSED!")
    print("=" * 60)
    print("\nThe crash recovery system is ready to use!")
    print("\nNext steps:")
    print("  1. Read: docs/CRASH_RECOVERY_GUIDE.md")
    print("  2. Run:  python tests/run_incremental_test.py")
    print("  3. Watch it automatically recover from crashes!\n")
    
    return True


def main():
    """Main installation and verification routine"""
    print("\n🛡️  Ableton Crash Recovery System Installer\n")
    
    # Step 1: Install dependencies
    if not install_dependencies():
        print("\n❌ Installation failed. Please fix errors and try again.\n")
        return 1
    
    # Step 2: Verify system
    if not verify_system():
        print("\n❌ Verification failed. Please check the errors above.\n")
        return 1
    
    print("=" * 60)
    print("🎉 INSTALLATION AND VERIFICATION COMPLETE!")
    print("=" * 60 + "\n")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

