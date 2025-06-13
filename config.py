"""
Configuration settings for the Telegram bot
"""
import os

# Bot Configuration
BOT_TOKEN = os.getenv('BOT_TOKEN', '8019817575:AAF5XlqAzVP2p5xakApDxQTxx96UqXoH79M')

# Multiple Admin Support
# You can add admin IDs in environment variables or directly here
ADMIN_UIDS_ENV = os.getenv('ADMIN_UIDS', '6490401448')  # Comma-separated list
ADMIN_UID = int(os.getenv('ADMIN_UID', '6490401448'))  # Primary admin (for backward compatibility)

# Parse multiple admin IDs
def get_admin_uids():
    """Get list of admin user IDs"""
    admin_ids = set()

    # Add primary admin
    admin_ids.add(ADMIN_UID)

    # Add additional admins from environment variable
    if ADMIN_UIDS_ENV:
        for uid in ADMIN_UIDS_ENV.split(','):
            try:
                admin_ids.add(int(uid.strip()))
            except ValueError:
                pass

    return list(admin_ids)

# Parse additional admin UIDs from environment variable
ADMIN_UIDS_ENV = os.getenv('ADMIN_UIDS', '')
if ADMIN_UIDS_ENV:
    try:
        additional_admins = [int(uid.strip()) for uid in ADMIN_UIDS_ENV.split(',') if uid.strip()]
        ADMIN_UIDS = [ADMIN_UID] + additional_admins
    except ValueError:
        ADMIN_UIDS = [ADMIN_UID]
else:
    ADMIN_UIDS = [ADMIN_UID]  # List of admin user IDs

def is_admin(user_id):
    """Check if user is an admin"""
    return user_id in ADMIN_UIDS

GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', 'AIzaSyAGDi2WslEe8VvBc7v3-dwpEmJobE6df1o')

# Database Configuration
MONGO_URI = 'mongodb+srv://birbhaiyadb:birbhaiyadbpass@cluster0.eqi584o.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0'

# Conversation States
MODE_SELECT, SINGLE_UID, BULK_IMG = range(3)

# Global Settings
restrict_mode = True  # Global restriction mode (ON by default)
last_extractions = []  # Store last bulk extractions for deletion