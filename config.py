
"""
Configuration settings for the Telegram bot
"""
import os

# Bot Configuration
BOT_TOKEN = os.getenv('BOT_TOKEN', '8019817575:AAF5XlqAzVP2p5xakApDxQTxx96UqXoH79M')
ADMIN_UID = int(os.getenv('ADMIN_UID', '6490401448'))
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', 'AIzaSyAGDi2WslEe8VvBc7v3-dwpEmJobE6df1o')

# Database Configuration
MONGO_URI = 'mongodb+srv://404movie:404moviepass@cluster0.fca76c9.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0'

# Conversation States
MODE_SELECT, SINGLE_UID, BULK_IMG = range(3)

# Global Settings
restrict_mode = True  # Global restriction mode (ON by default)
last_extractions = []  # Store last bulk extractions for deletion
