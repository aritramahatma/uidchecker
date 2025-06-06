
#!/usr/bin/env python3
"""
Automated dependency setup script to prevent telegram package conflicts
Run this before starting the bot to ensure correct packages are installed
"""

import subprocess
import sys
import os

def run_command(cmd):
    """Run shell command and return success status"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        print(f"Running: {cmd}")
        if result.stdout:
            print(result.stdout)
        if result.stderr and result.returncode != 0:
            print(f"Error: {result.stderr}")
        return result.returncode == 0
    except Exception as e:
        print(f"Command failed: {e}")
        return False

def fix_telegram_packages():
    """Fix telegram package installation issues"""
    print("🔧 Fixing telegram package dependencies...")
    
    # Step 1: Remove any conflicting packages aggressively
    print("\n1. Removing ALL conflicting packages...")
    run_command("pip uninstall -y telegram python-telegram-bot")
    
    # Step 2: Clean pip cache completely
    print("\n2. Cleaning pip cache...")
    run_command("pip cache purge")
    
    # Step 3: Install ONLY the correct package
    print("\n3. Installing ONLY python-telegram-bot (no conflicting packages)...")
    success = run_command("pip install python-telegram-bot==13.15 --no-cache-dir --force-reinstall")
    
    if not success:
        print("❌ Failed to install python-telegram-bot, trying alternative method...")
        run_command("pip install --upgrade pip")
        run_command("pip install python-telegram-bot==13.15 --no-cache-dir --force-reinstall")
    
    # Step 4: Verify installation and check for conflicts
    print("\n4. Verifying installation...")
    try:
        import telegram
        from telegram import Update
        print("✅ python-telegram-bot installed correctly!")
        print(f"📍 Package location: {telegram.__file__}")
        
        # Check if the bad telegram package is installed
        try:
            result = subprocess.run(['pip', 'show', 'telegram'], capture_output=True, text=True)
            if result.returncode == 0 and "telegram 0.0.1" in result.stdout:
                print("⚠️ Detected conflicting telegram 0.0.1 package - removing...")
                run_command("pip uninstall -y telegram")
        except:
            pass
            
        return True
    except ImportError as e:
        print(f"❌ Installation verification failed: {e}")
        return False

def install_other_dependencies():
    """Install other project dependencies (excluding telegram)"""
    print("📦 Installing other project dependencies...")
    
    # Install specific packages without the conflicting telegram package
    packages = [
        "pillow",
        "pymongo", 
        "requests"
    ]
    
    for package in packages:
        print(f"Installing {package}...")
        run_command(f"pip install {package} --no-cache-dir")

def main():
    print("🚀 Starting FINAL dependency setup...")
    print("=" * 50)
    
    # Fix telegram packages first
    if not fix_telegram_packages():
        print("❌ Failed to fix telegram packages. Exiting...")
        sys.exit(1)
    
    # Install other dependencies
    install_other_dependencies()
    
    # Final verification
    print("\n" + "=" * 50)
    print("🔍 Final verification...")
    try:
        from telegram.ext import Updater
        from telegram import Update
        print("✅ ALL PACKAGES WORKING CORRECTLY!")
        print("🤖 Your bot is ready to run!")
    except ImportError as e:
        print(f"❌ Final verification failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
