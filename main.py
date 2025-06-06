# UID Verification Telegram Bot (Gemini OCR + MongoDB)
# Author: Aritra Mahatma

import os
import re
import logging
import requests
import base64
from datetime import datetime
from PIL import Image
from io import BytesIO
from pymongo import MongoClient
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, ConversationHandler, CallbackQueryHandler

# CONFIG - Using environment variables with fallbacks
BOT_TOKEN = os.getenv('BOT_TOKEN', '8019817575:AAF5XlqAzVP2p5xakApDxQTxx96UqXoH79M')
ADMIN_UID = int(os.getenv('ADMIN_UID', '6490401448'))
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', 'AIzaSyAGDi2WslEe8VvBc7v3-dwpEmJobE6df1o')
# Updated MongoDB URL as requested
MONGO_URI = 'mongodb+srv://404movie:404moviepass@cluster0.fca76c9.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0'

# SETUP
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO)
logger = logging.getLogger(__name__)

# MongoDB connection with error handling
try:
    client = MongoClient(MONGO_URI,
                         serverSelectionTimeoutMS=5000,
                         connectTimeoutMS=10000,
                         socketTimeoutMS=10000)
    db = client['uidchecker']
    uids_col = db['uids']
    gift_codes_col = db['gift_codes']
    user_stats_col = db['user_stats']
    # Test connection
    client.admin.command('ping')
    logger.info("MongoDB connection successful")
except Exception as e:
    logger.error(f"MongoDB connection failed: {e}")
    raise

# Global variables
restrict_mode = False
last_extractions = []
MODE_SELECT, SINGLE_UID, BULK_IMG = range(3)

def start(update: Update, context: CallbackContext):
    """Welcome message for new users with image and buttons"""
    user_id = update.message.from_user.id
    username = update.message.from_user.username or "Unknown"
    
    # Track user activity
    try:
        user_stats_col.update_one(
            {'user_id': user_id},
            {'$set': {'last_seen': datetime.now()}, '$setOnInsert': {
                'first_seen': datetime.now(),
                'is_blocked': False,
                'actions': []
            }},
            upsert=True
        )
    except Exception as e:
        logger.error(f"Error updating user stats: {e}")
    
    welcome_message = (
        "*🎉 Welcome to UID Verification Bot! 🎉*\n\n"
        "*🔐 Get instant access to premium features:*\n"
        "*📱 Gaming predictions (Wingo, Aviator)*\n"
        "*🎁 Daily gift codes*\n"
        "*💰 Bonus rewards*\n\n"
        "*📋 Quick verification required - takes 30 seconds!*\n"
        "*🚀 Click buttons below to get started*"
    )
    
    # Create inline keyboard with buttons
    keyboard = [
        [InlineKeyboardButton("📸 Send Screenshot", callback_data="send_screenshot")],
        [InlineKeyboardButton("🎁 Gift Codes", callback_data="gift_codes")],
        [InlineKeyboardButton("🎯 Prediction", callback_data="prediction")],
        [InlineKeyboardButton("💎 Bonus", callback_data="bonus")],
        [InlineKeyboardButton("🛠 Support", callback_data="support")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Send welcome image with message
    image_url = "https://files.catbox.moe/h5bgxo.jpg"
    try:
        update.message.reply_photo(
            photo=image_url,
            caption=welcome_message,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"Error sending start photo: {e}")
        # Fallback to text message
        update.message.reply_text(
            welcome_message,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )

def handle_all(update: Update, context: CallbackContext):
    """Handle all incoming messages (text and photos)"""
    user_id = update.message.from_user.id
    
    if update.message.text and update.message.text.startswith('/'):
        return  # Let command handlers process commands
    
    if update.message.photo:
        # Handle photo messages
        update.message.reply_text("📸 Screenshot received! Processing...")
    elif update.message.text:
        # Handle text messages
        update.message.reply_text("✅ Message received! Use /start to access the bot features.")

def main():
    """Main function to start the bot"""
    try:
        # Create updater and dispatcher
        updater = Updater(BOT_TOKEN, use_context=True)
        dp = updater.dispatcher
        
        # Initialize bot data
        if 'pending_wallets' not in dp.bot_data:
            dp.bot_data['pending_wallets'] = {}
        if 'digits_message_id' not in dp.bot_data:
            dp.bot_data['digits_message_id'] = {}
        
        # Add handlers
        dp.add_handler(CommandHandler("start", start))
        dp.add_handler(MessageHandler(Filters.all, handle_all))
        
        # Error handler
        def error_handler(update, context):
            logger.error(f"Update {update} caused error {context.error}")
        
        dp.add_error_handler(error_handler)
        
        # Start bot
        logger.info("Starting UID Verification Bot...")
        updater.start_polling(drop_pending_updates=True)
        logger.info("Bot is running! Press Ctrl+C to stop.")
        updater.idle()
        
    except Exception as e:
        logger.error(f"Error starting bot: {e}")
        raise

if __name__ == '__main__':
    main()