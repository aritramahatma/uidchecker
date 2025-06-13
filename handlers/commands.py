
"""
Command handlers for the Telegram bot
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
from services.database import uids_col, update_user_stats, get_current_gift_code
from utils.helpers import safe_send_message

logger = logging.getLogger(__name__)


def start(update: Update, context: CallbackContext):
    """Welcome message for new users with image and buttons"""
    from services.database import user_stats_col
    from datetime import datetime
    
    # Track user activity
    user_id = update.message.from_user.id

    # If user was previously marked as blocked by user action, unblock them since they're using /start
    try:
        user_doc = user_stats_col.find_one({'user_id': user_id})
        if user_doc and user_doc.get('is_blocked', False) and user_doc.get(
                'blocked_by_user', False):
            # User is back, unblock them
            user_stats_col.update_one({'user_id': user_id}, {
                '$set': {
                    'is_blocked': False,
                    'blocked_by_user': False,
                    'unblocked_date': datetime.now()
                }
            })
            # Update global counts - add back to total users and remove from blocked
            user_stats_col.update_one(
                {'_id': 'global_stats'},
                {
                    '$inc': {
                        'blocked_users': -1,
                        'total_users':
                        1  # Add back to total user count when unblocked
                    }
                },
                upsert=True)
            logger.info(
                f"User {user_id} automatically unblocked and added back to total users - they used /start command"
            )
    except Exception as e:
        logger.error(f"Error checking/updating unblock status in start: {e}")

    update_user_stats(user_id, 'start_command')

    msg = (
        "*Welcome To Tashan Win Prediction Bot !! 🧞‍♂*\n\n"
        "*× To Access Premium Prediction ⚡+ Gift Code 🎁 + High Deposit Bonus 💰*\n\n"
        "*1. Register With Official Link 🔗\n"
        "2. Deposit ₹100 Atleast 📥\n"
        "3. Send UID & Screenshot 📃\n"
        "4. Wait For Admin Approval ⏰*\n\n"
        "*टशन विन प्रेडिक्शन बॉट में आपका स्वागत है !! 🧞‍♂*\n\n"
        "*× प्रीमियम प्रेडिक्शन तक पहुँचने के लिए ⚡+ गिफ्ट कोड 🎁 + हाई डिपॉज़िट बोनस 💰*\n\n"
        "*1. आधिकारिक लिंक के साथ रजिस्टर करें 🔗\n"
        "2. कम से कम ₹100 जमा करें 📥\n"
        "3. यूआईडी और स्क्रीनशॉट भेजें 📃\n"
        "4. एडमिन की स्वीकृति का इंतज़ार करें ⏰*")

    # Create inline keyboard with buttons
    keyboard = [[
        InlineKeyboardButton(
            "Registration Link",
            url="https://www.jalwa.fun/#/register?invitationCode=66385106362")
    ],
                [
                    InlineKeyboardButton("Send Screenshot",
                                         callback_data="send_screenshot")
                ]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Send photo with caption and buttons
    try:
        update.message.reply_photo(photo="https://files.catbox.moe/7zg38j.jpg",
                                   caption=msg,
                                   parse_mode='Markdown',
                                   reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Error sending photo in start command: {e}")
        # Fallback to text message if photo fails
        update.message.reply_text(msg,
                                  parse_mode='Markdown',
                                  reply_markup=reply_markup)


def claim_command(update: Update, context: CallbackContext):
    """Handle /claim command for gift codes"""
    from services.database import user_stats_col
    from datetime import datetime
    
    user_id = update.message.from_user.id

    # Track user activity
    update_user_stats(user_id, 'claim_command')

    # Check if user is blocked
    try:
        user_doc = user_stats_col.find_one({'user_id': user_id})
        if user_doc and user_doc.get('is_blocked', False):
            update.message.reply_text(
                "🚫 You have been blocked from using this bot.")
            return
    except Exception as e:
        logger.error(f"Error checking blocked status in claim: {e}")

    # If user was previously marked as blocked by user action, unblock them
    try:
        user_doc = user_stats_col.find_one({'user_id': user_id})
        if user_doc and user_doc.get('is_blocked', False) and user_doc.get(
                'blocked_by_user', False):
            # User is back, unblock them
            user_stats_col.update_one({'user_id': user_id}, {
                '$set': {
                    'is_blocked': False,
                    'blocked_by_user': False,
                    'unblocked_date': datetime.now()
                }
            })
            # Update global counts
            user_stats_col.update_one(
                {'_id': 'global_stats'},
                {'$inc': {
                    'blocked_users': -1,
                    'total_users': 1
                }},
                upsert=True)
            logger.info(
                f"User {user_id} automatically unblocked in claim command")
    except Exception as e:
        logger.error(f"Error checking/updating unblock status in claim: {e}")

    try:
        # Check if user is fully verified
        user_uid_doc = uids_col.find_one({
            'user_id': user_id,
            'fully_verified': True
        })

        if user_uid_doc:
            # User is fully verified - show gift code directly
            try:
                # Get current gift code from database
                gift_code_data = get_current_gift_code()

                gift_code_msg = (
                    "*🎁 GIFT CODE UNLOCKED – Get Up to ₹500!*\n\n"
                    f"`{gift_code_data['code']}`\n\n"
                    f"*🕒 Updated: {gift_code_data['updated_date']}*\n"
                    "*🔄 Next Update: 24 hours Later*\n\n"
                    "*⚠️ Condition:*\n"
                    "*➠ Must register using the official link to claim!*\n\n"
                    "*🥷 ENJOY & WIN BIG! 🦋*")

                # Create keyboard with back to main menu option
                keyboard = [[
                    InlineKeyboardButton("🏠 Main Menu", callback_data="back")
                ]]
                reply_markup = InlineKeyboardMarkup(keyboard)

                # Send photo with gift code
                try:
                    update.message.reply_photo(
                        photo="https://files.catbox.moe/gyeskx.webp",
                        caption=gift_code_msg,
                        parse_mode='Markdown',
                        reply_markup=reply_markup)
                except Exception as e:
                    logger.error(f"Error sending photo in claim command: {e}")
                    # Fallback to text message if photo fails
                    update.message.reply_text(gift_code_msg,
                                              parse_mode='Markdown',
                                              reply_markup=reply_markup)
            except Exception as e:
                logger.error(f"Error getting gift code in claim command: {e}")
                update.message.reply_text(
                    "❌ Error retrieving gift code. Please try again.")
        else:
            # User is not verified - show verification required message
            # Get current gift code (partial) for teasing
            gift_code_data = get_current_gift_code()
            # Format code like: 677AFD5E6F79-XXXX-75FH
            code = gift_code_data['code']
            if len(code) >= 16:
                # For long codes, show first 12 characters, then -XXXX-, then last 4
                partial_code = code[:12] + "-XXXX-" + code[-4:]
            elif len(code) >= 8:
                # For shorter codes, show first 4, then -XXXX-, then last 2
                partial_code = code[:4] + "-XXXX-" + code[-2:]
            else:
                # For very short codes, just show XXXX
                partial_code = "XXXX-" + code[-2:] if len(
                    code) >= 2 else "XXXXXX"

            verification_msg = (
                "*🎁 Ready to Grab Your Reward ⁉️*\n\n"
                f"📥 Code : `{partial_code}`\n"
                "*🔐 Verify your ID & Wallet to unlock the surprise!*\n"
                "*💸 Up to ₹500 Gift Code is waiting just for YOU!*\n\n"
                "*⏳ Hurry Up !! Limited codes Available 🦋*")

            # Create inline keyboard with register button
            keyboard = [[
                InlineKeyboardButton(
                    "Verify Now",
                    url=
                    "https://www.jalwagames2.com/#/register?invitationCode=542113286414"
                )
            ]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            update.message.reply_text(verification_msg,
                                      parse_mode='Markdown',
                                      reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Error in claim command: {e}")
        update.message.reply_text(
            "❌ Error processing your claim request. Please try again.")
