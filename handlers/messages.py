
"""
Message handlers for the Telegram bot
"""
import logging
import re
from telegram import Update
from telegram.ext import CallbackContext
from services.database import update_user_stats, user_stats_col
from utils.validators import check_uid, handle_wallet
from services.predictions import generate_aviator_prediction
from datetime import datetime

logger = logging.getLogger(__name__)


def handle_aviator_round_id_input(update: Update, context: CallbackContext, round_id):
    """Handle user's round ID input and generate prediction"""
    user_id = update.message.from_user.id
    
    # Send sticker first before prediction
    try:
        aviator_sticker = update.message.reply_sticker(
            sticker="CAACAgEAAxkBAAEOpMhoQZoGuaWt7uRSTMj_Iqlok-VO_QACWgIAAqaQ2USiYhZ1luPyBDYE"
        )
    except Exception as e:
        logger.error(f"Error sending aviator sticker: {e}")
    
    # Generate prediction based on round ID
    prediction_multiplier = generate_aviator_prediction(round_id)
    
    # Create prediction message
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    
    prediction_msg = (
        "*🔐 VIP Hack Aviator Prediction ⏳*\n\n"
        "*🎮 Game: Aviator*\n"
        f"*📥 Period Number: {round_id}*\n"
        f"*💸 Cash Out Target: {prediction_multiplier}*\n\n"
        "*💡 Reminder: Always maintain Level 3 funds*"
    )
    
    # Create keyboard with Next Prediction and Back buttons
    keyboard = [[
        InlineKeyboardButton("Next Prediction", callback_data="aviator_signals")
    ], [InlineKeyboardButton("🔙 Back", callback_data="aviator_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Remove user from waiting state and clear error count
    if 'aviator_waiting_round_id' in context.bot_data and user_id in context.bot_data['aviator_waiting_round_id']:
        context.bot_data['aviator_waiting_round_id'].remove(user_id)
    
    # Clear error count on successful prediction
    if 'aviator_error_count' in context.bot_data and user_id in context.bot_data['aviator_error_count']:
        context.bot_data['aviator_error_count'][user_id] = 0
    
    # Delete the instruction message when user provides round ID
    if 'aviator_instruction_messages' in context.bot_data and user_id in context.bot_data['aviator_instruction_messages']:
        try:
            context.bot.delete_message(
                chat_id=user_id,
                message_id=context.bot_data['aviator_instruction_messages'][user_id]
            )
            # Remove from tracking after deletion
            del context.bot_data['aviator_instruction_messages'][user_id]
        except Exception as e:
            logger.error(f"Error deleting aviator instruction message: {e}")
    
    # Keep all prediction results - don't delete them
    if 'aviator_prediction_messages' not in context.bot_data:
        context.bot_data['aviator_prediction_messages'] = {}
    
    # Send new prediction with image
    try:
        sent_message = update.message.reply_photo(
            photo="https://files.catbox.moe/nvrvwg.png",
            caption=prediction_msg,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        # Store new message ID
        context.bot_data['aviator_prediction_messages'][user_id] = sent_message.message_id
    except Exception as e:
        logger.error(f"Error sending aviator prediction with photo: {e}")
        # Fallback to text message
        try:
            sent_message = update.message.reply_text(
                prediction_msg,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
            context.bot_data['aviator_prediction_messages'][user_id] = sent_message.message_id
        except Exception as e2:
            logger.error(f"Error sending aviator prediction text: {e2}")


def handle_all(update: Update, context: CallbackContext):
    """Handle all incoming messages (text and photos)"""
    user_id = update.message.from_user.id
    username = update.message.from_user.username or 'NoUsername'

    # Check if user is blocked
    try:
        user_doc = user_stats_col.find_one({'user_id': user_id})
        if user_doc and user_doc.get('is_blocked', False):
            update.message.reply_text(
                "🚫 You have been blocked from using this bot.")
            return
    except Exception as e:
        logger.error(f"Error checking blocked status: {e}")

    # If user was previously marked as blocked by user action, unblock them since they're messaging again
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
                f"User {user_id} automatically unblocked and added back to total users - they're messaging again"
            )
    except Exception as e:
        logger.error(f"Error checking/updating unblock status: {e}")

    # Track user activity
    update_user_stats(user_id, 'message_sent')

    try:
        if update.message.text:
            # Check if user is waiting for aviator round ID (3 digits)
            if ('aviator_waiting_round_id' in context.bot_data
                    and user_id in context.bot_data['aviator_waiting_round_id']):
                
                text = update.message.text.strip()
                
                # Check if it's exactly 3 digits
                if re.match(r'^\d{3}$', text):
                    handle_aviator_round_id_input(update, context, text)
                    return
                else:
                    # Invalid input for aviator - give specific error and clear the waiting state after 3 attempts
                    if 'aviator_error_count' not in context.bot_data:
                        context.bot_data['aviator_error_count'] = {}
                    
                    if user_id not in context.bot_data['aviator_error_count']:
                        context.bot_data['aviator_error_count'][user_id] = 0
                    
                    context.bot_data['aviator_error_count'][user_id] += 1
                    
                    if context.bot_data['aviator_error_count'][user_id] >= 3:
                        # Clear waiting state after 3 failed attempts
                        context.bot_data['aviator_waiting_round_id'].remove(user_id)
                        context.bot_data['aviator_error_count'][user_id] = 0
                        
                        update.message.reply_text(
                            "*❌ Aviator Signals Cancelled*\n"
                            "*🔄 Too many invalid attempts*\n\n"
                            "*🚀 Click 'Get Signals' again to restart*",
                            parse_mode='Markdown')
                    else:
                        attempts_left = 3 - context.bot_data['aviator_error_count'][user_id]
                        update.message.reply_text(
                            "*❌ Invalid Aviator Round ID*\n"
                            "*🎮 For Aviator Game: Send exactly 3 digits only*\n"
                            "*✅ Example: 123*\n"
                            "*⚙️ From 6456123 ➡️ Send 123*\n\n"
                            f"*⏰ Attempts left: {attempts_left}*",
                            parse_mode='Markdown')
                    return
            
            # Check if user is waiting for 3 digits (manual prediction)
            elif ('waiting_for_digits' in context.bot_data
                    and user_id in context.bot_data['waiting_for_digits']):

                text = update.message.text.strip()

                # Check if it's exactly 3 digits
                if re.match(r'^\d{3}$', text):
                    # Remove user from waiting state and clear error count
                    context.bot_data['waiting_for_digits'].discard(user_id)
                    
                    # Clear error count on successful prediction
                    if 'wingo_error_count' in context.bot_data and user_id in context.bot_data['wingo_error_count']:
                        context.bot_data['wingo_error_count'][user_id] = 0

                    # Send sticker first
                    try:
                        manual_sticker = update.message.reply_sticker(
                            sticker=
                            "CAACAgQAAxkBAAEOn6RoPTKiSte1vk8IStJRTBsfRYRdCwAC4xgAAoo2OVGWcfjhDFS9nTYE"
                        )
                    except Exception as e:
                        logger.error(f"Error sending sticker: {e}")

                    # Random BIG/SMALL selection with consecutive limit
                    import random
                    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

                    # Initialize tracking variables if they don't exist
                    if 'last_prediction' not in context.bot_data:
                        context.bot_data['last_prediction'] = None
                    if 'consecutive_count' not in context.bot_data:
                        context.bot_data['consecutive_count'] = 0

                    # Determine next prediction
                    if context.bot_data['consecutive_count'] >= 8:
                        # Force switch if we've had 8 consecutive same predictions
                        if context.bot_data['last_prediction'] == "BIG":
                            purchase_type = "SMALL"
                        else:
                            purchase_type = "BIG"
                        context.bot_data['consecutive_count'] = 1
                    else:
                        # Random selection
                        purchase_type = random.choice(["BIG", "SMALL"])

                        if purchase_type == context.bot_data[
                                'last_prediction']:
                            context.bot_data['consecutive_count'] += 1
                        else:
                            context.bot_data['consecutive_count'] = 1

                    # Update last prediction
                    context.bot_data['last_prediction'] = purchase_type

                    # Keep all prediction history - no automatic deletion

                    # Send VIP prediction message with image based on result
                    vip_prediction_msg = (
                        "*🔐 VIP Hack Manual Prediction ⏳*\n\n"
                        "*🎮 Game: Wingo 1 Minute*\n"
                        f"*🆔 Period Number : {text}*\n"
                        f"*💸 Purchase: {purchase_type}*\n\n"
                        "*⚠️ Important: Always maintain Level 5 funds*")

                    # Create keyboard with Next Prediction and Back buttons
                    keyboard = [[
                        InlineKeyboardButton("Next Prediction",
                                             callback_data="manual_prediction")
                    ], [InlineKeyboardButton("Back", callback_data="back")]]
                    reply_markup = InlineKeyboardMarkup(keyboard)

                    # Choose image based on prediction result
                    if purchase_type == "BIG":
                        image_url = "https://files.catbox.moe/h5bgxo.jpg"
                    else:  # SMALL
                        image_url = "https://files.catbox.moe/mstdso.jpg"

                    # Send photo with caption and buttons
                    try:
                        update.message.reply_photo(photo=image_url,
                                                   caption=vip_prediction_msg,
                                                   parse_mode='Markdown',
                                                   reply_markup=reply_markup)
                    except Exception as e:
                        logger.error(
                            f"Error sending photo in manual prediction: {e}")
                        # Fallback to text message if photo fails
                        update.message.reply_text(vip_prediction_msg,
                                                  parse_mode='Markdown',
                                                  reply_markup=reply_markup)
                    return
                else:
                    # Invalid input for manual Wingo prediction - give specific error and clear state after 3 attempts
                    if 'wingo_error_count' not in context.bot_data:
                        context.bot_data['wingo_error_count'] = {}
                    
                    if user_id not in context.bot_data['wingo_error_count']:
                        context.bot_data['wingo_error_count'][user_id] = 0
                    
                    context.bot_data['wingo_error_count'][user_id] += 1
                    
                    if context.bot_data['wingo_error_count'][user_id] >= 3:
                        # Clear waiting state after 3 failed attempts
                        context.bot_data['waiting_for_digits'].discard(user_id)
                        context.bot_data['wingo_error_count'][user_id] = 0
                        
                        update.message.reply_text(
                            "*❌ Wingo Manual Prediction Cancelled*\n"
                            "*🔄 Too many invalid attempts*\n\n"
                            "*🚀 Click 'Manual Prediction' again to restart*",
                            parse_mode='Markdown')
                    else:
                        attempts_left = 3 - context.bot_data['wingo_error_count'][user_id]
                        update.message.reply_text(
                            "*❌ Invalid Wingo Period Number*\n"
                            "*🎮 For Wingo Game: Send exactly 3 digits only*\n"
                            "*✅ Example: 789*\n"
                            "*🔢 Period format: XXX (3 digits)*\n\n"
                            f"*⏰ Attempts left: {attempts_left}*",
                            parse_mode='Markdown')
                    return

            # Handle text messages - look for UID (but exclude 3-digit numbers)
            text = update.message.text.upper().strip()

            # Check if it's exactly 3 digits but user is not in prediction mode
            if re.match(r'^\d{3}$', text):
                # If user is not waiting for digits, show UID request message
                if ('waiting_for_digits' not in context.bot_data or user_id
                        not in context.bot_data['waiting_for_digits']):
                    update.message.reply_text(
                        "*📩 Send Your UID or Screenshot to Proceed*\n\n"
                        "*☑️ Valid UID Format: 123456789 or UID 123456789*\n\n"
                        "*🖼 Or upload a clear screenshot showing UID*\n"
                        "*🔐 UID must be 6–12 digits only*\n"
                        "*🚀 Let's get you verified in seconds!*",
                        parse_mode='Markdown')
                else:
                    # User is in prediction mode but sent invalid 3 digits
                    update.message.reply_text(
                        "*❌ Invalid Input*\n"
                        "*🔢 Please send exactly 3 digits*\n"
                        "*✅ Example: 789*\n\n"
                        "*🧠 Let's keep it simple and accurate!*",
                        parse_mode='Markdown')
                return

            # Look for valid UIDs (6-12 digits, not exactly 3)
            uid_match = re.search(r'(?:UID\s*)?(\d{6,12})', text)

            if uid_match:
                uid = uid_match.group(1)
                # Double check it's not exactly 3 digits
                if len(uid) == 3:
                    update.message.reply_text(
                        "*📩 Send Your UID or Screenshot to Proceed*\n\n"
                        "*☑️ Valid UID Format: 123456789 or UID 123456789*\n\n"
                        "*🖼 Or upload a clear screenshot showing UID*\n"
                        "*🔐 UID must be 6–12 digits only*\n"
                        "*🚀 Let's get you verified in seconds!*",
                        parse_mode='Markdown')
                    return
                check_uid(update, context, uid, user_id, username)
            else:
                update.message.reply_text(
                    "*📩 Send Your UID or Screenshot to Proceed*\n\n"
                    "*☑️ Valid UID Format: 123456789 or UID 123456789*\n\n"
                    "*🖼 Or upload a clear screenshot showing UID*\n"
                    "*🔐 UID must be 6–12 digits only*\n"
                    "*🚀 Let's get you verified in seconds!*",
                    parse_mode='Markdown')

        elif update.message.photo:
            # Handle photo messages - wallet verification or UID extraction
            handle_wallet(update, context)

    except Exception as e:
        logger.error(f"Error in handle_all: {e}")
        update.message.reply_text(
            "❌ Error processing your message. Please try again.")
