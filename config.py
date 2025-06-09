
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

ADMIN_UIDS = get_admin_uids()

def is_admin(user_id):
    """Check if user is an admin"""
    return user_id in ADMIN_UIDS

GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', 'AIzaSyAGDi2WslEe8VvBc7v3-dwpEmJobE6df1o')

# Database Configuration
MONGO_URI = 'mongodb+srv://404movie:404moviepass@cluster0.fca76c9.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0'

# Conversation States
MODE_SELECT, SINGLE_UID, BULK_IMG = range(3)

# Global Settings
restrict_mode = True  # Global restriction mode (ON by default)
last_extractions = []  # Store last bulk extractions for deletion
