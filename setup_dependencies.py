
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
    
    # Step 1: Remove any conflicting packages
    print("\n1. Removing conflicting packages...")
    run_command("pip uninstall -y telegram python-telegram-bot")
    
    # Step 2: Clean pip cache
    print("\n2. Cleaning pip cache...")
    run_command("pip cache purge")
    
    # Step 3: Install correct package with specific version
    print("\n3. Installing correct python-telegram-bot package...")
    success = run_command("pip install python-telegram-bot==13.15 --no-cache-dir --force-reinstall")
    
    if not success:
        print("❌ Failed to install python-telegram-bot, trying alternative method...")
        run_command("pip install --upgrade pip")
        run_command("pip install python-telegram-bot==13.15 --no-cache-dir --force-reinstall")
    
    # Step 4: Verify installation
    print("\n4. Verifying installation...")
    try:
        import telegram
        from telegram import Update
        print("✅ python-telegram-bot installed correctly!")
        print(f"📍 Package location: {telegram.__file__}")
        return True
    except ImportError as e:
        print(f"❌ Installation verification failed: {e}")
        return False

def install_all_dependencies():
    """Install all project dependencies"""
    print("📦 Installing all project dependencies...")
    
    # Install from requirements.txt
    if os.path.exists("requirements.txt"):
        run_command("pip install -r requirements.txt --no-cache-dir")
    
    # Install from pyproject.toml if exists
    if os.path.exists("pyproject.toml"):
        run_command("pip install -e . --no-cache-dir")

def main():
    print("🚀 Starting automated dependency setup...")
    print("=" * 50)
    
    # Fix telegram packages first
    if not fix_telegram_packages():
        print("❌ Failed to fix telegram packages. Exiting...")
        sys.exit(1)
    
    # Install other dependencies
    install_all_dependencies()
    
    print("\n" + "=" * 50)
    print("✅ Dependency setup completed successfully!")
    print("🤖 Your bot is ready to run!")

if __name__ == "__main__":
    main()
