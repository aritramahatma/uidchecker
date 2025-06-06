"""
Callback handlers for the Telegram bot with comprehensive error handling
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import CallbackContext
from utils.error_handler import handle_telegram_errors, safe_edit_message, safe_reply

logger = logging.getLogger(__name__)


@handle_telegram_errors
def handle_callback_query_safe(update: Update, context: CallbackContext):
    """Safely handle callback queries with error handling"""
    query = update.callback_query
    
    # Always answer callback query to remove loading state
    try:
        query.answer()
    except Exception as e:
        logger.warning(f"Failed to answer callback query: {e}")
    
    # Route to appropriate handler based on callback data
    callback_data = query.data
    
    try:
        if callback_data == "send_screenshot":
            handle_screenshot_button_safe(update, context)
        elif callback_data == "bonus":
            handle_bonus_button_safe(update, context)
        elif callback_data == "back":
            handle_back_button_safe(update, context)
        # Add more callback handlers as needed
        else:
            logger.warning(f"Unknown callback data: {callback_data}")
            safe_reply(update, "❌ Unknown action. Please try again.")
    except Exception as e:
        logger.error(f"Error handling callback {callback_data}: {e}")
        safe_reply(update, "❌ Error processing your request. Please try again.")


def handle_screenshot_button_safe(update: Update, context: CallbackContext):
    """Handle screenshot button with error handling"""
    query = update.callback_query
    
    msg = (
        "*Welcome To Tashan Win Prediction Bot !! 🧞‍♂*\n\n"
        "*× To Access Premium Prediction ⚡+ Gift Code 🎁 + High Deposit Bonus 💰*\n\n"
        "*1. Register With Official Link 🔗\n"
        "2. Deposit ₹100 Atleast 📥\n"
        "3. Send UID & Screenshot 📃\n"
        "4. Wait For Admin Approval ⏰*\n\n"
        "*Note : Access will expire in 7 Days 🗓️*\n\n"
        "*📝 Please send your UID for verification (6-12 digits):*"
    )
    
    safe_edit_message(query, caption=msg, parse_mode='Markdown')


def handle_bonus_button_safe(update: Update, context: CallbackContext):
    """Handle bonus button with error handling"""
    query = update.callback_query
    
    # Example implementation
    hack_msg = ("*🚀Click on 'GET HACK' & Start Earning Lakhs Daily!*\n"
                "*🎯 One Click Can Change Everything*\n"
                "*🔥 Don't Miss Out – Limited Slots Only!*\n"
                "*⚡️ Tap Now & Be the Next Big Earner!*")

    keyboard = [[
        InlineKeyboardButton("Hack", callback_data="get_hack"),
        InlineKeyboardButton("Tutorial", callback_data="tutorial")
    ], [InlineKeyboardButton("🔙 Back", callback_data="back")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    media = InputMediaPhoto(
        media="https://files.catbox.moe/0oy4gu.png",
        caption=hack_msg,
        parse_mode='Markdown'
    )
    
    safe_edit_message(query, media=media, reply_markup=reply_markup)


def handle_back_button_safe(update: Update, context: CallbackContext):
    """Handle back button with error handling"""
    query = update.callback_query
    
    # Create main menu
    keyboard = [[
        InlineKeyboardButton("Prediction", callback_data="prediction"),
        InlineKeyboardButton("Gift Codes", callback_data="gift_codes")
    ], [
        InlineKeyboardButton("Get Hack", callback_data="bonus"),
        InlineKeyboardButton("Support", callback_data="support")
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    msg = (
        f"*✅ Verification Successful! 🎯*\n\n"
        f"*You're now eligible for VIP AI Predictions ⚡️& Daily Gift Codes worth up to ₹500 🎁*\n\n"
        f"*📋 UID: 9413264*\n"
        f"*💰 Balance: ₹607.56*\n"
        f"*🏆 Status: Fully Verified*\n\n"
        f"*👤Approved by Admin!*\n"
        f"*⚠️ Note: Your access is valid for 7 days 📆*"
    )

    media = InputMediaPhoto(
        media="https://files.catbox.moe/4hd1vl.png",
        caption=msg,
        parse_mode='Markdown'
    )
    
    safe_edit_message(query, media=media, reply_markup=reply_markup)