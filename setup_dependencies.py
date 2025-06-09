#!/usr/bin/env python3
"""
Replit-compatible dependency checker
This script checks if dependencies are properly installed
"""

import sys
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def check_dependencies():
    """Check if all required dependencies are available"""
    print("🔍 Checking dependencies in Replit environment...")

    required_packages = [
        ('telegram', 'python-telegram-bot'),
        ('pymongo', 'pymongo'),
        ('PIL', 'pillow'),
        ('requests', 'requests')
    ]

    missing_packages = []

    for package, pip_name in required_packages:
        try:
            __import__(package)
            print(f"✅ {pip_name} - OK")
        except ImportError as e:
            print(f"❌ {pip_name} - MISSING")
            missing_packages.append(pip_name)
            logger.error(f"Missing package: {pip_name} - {e}")

    if missing_packages:
        print(f"\n❌ Missing packages: {', '.join(missing_packages)}")
        print("\n🔧 To fix this in Replit:")
        print("1. Make sure your requirements.txt contains the correct packages")
        print("2. Use the 'Install Packages' button in the sidebar")
        print("3. Or run: pip install -r requirements.txt")
        return False
    else:
        print("\n✅ All dependencies are available!")
        return True

def check_telegram_specific():
    """Check telegram-specific imports"""
    print("\n🤖 Checking Telegram Bot imports...")

    try:
        from telegram import Update
        from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
        print("✅ Telegram Bot imports - OK")
        return True
    except ImportError as e:
        print(f"❌ Telegram Bot imports failed: {e}")
        print("\n🔧 This usually means:")
        print("1. Wrong telegram package installed (should be python-telegram-bot==13.15)")
        print("2. Conflicting packages")
        print("3. In Replit, try: pip install python-telegram-bot==13.15 --force-reinstall")
        return False

def main():
    """Main dependency check"""
    print("🔍 REPLIT DEPENDENCY CHECKER")
    print("=" * 50)

    # Check basic dependencies
    deps_ok = check_dependencies()

    # Check telegram-specific imports
    telegram_ok = check_telegram_specific()

    if deps_ok and telegram_ok:
        print("\n🎉 ALL CHECKS PASSED!")
        print("✅ Your bot should run without dependency issues")
        return True
    else:
        print("\n❌ DEPENDENCY ISSUES FOUND")
        print("🔧 Please fix the issues above before running the bot")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)