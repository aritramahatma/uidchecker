# UID Verification Telegram Bot (Gemini OCR + MongoDB)
# Author: Aritra Mahatma

import os
import re
import logging
import requests
import base64
from PIL import Image
from io import BytesIO
from pymongo import MongoClient
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, ConversationHandler

# CONFIG - Using environment variables with fallbacks
BOT_TOKEN = os.getenv('BOT_TOKEN', '8019817575:AAF5XlqAzVP2p5xakApDxQTxx96UqXoH79M')
ADMIN_UID = int(os.getenv('ADMIN_UID', '6490401448'))
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', 'AIzaSyAGDi2WslEe8VvBc7v3-dwpEmJobE6df1o')
# Updated MongoDB URL as requested
MONGO_URI = 'mongodb+srv://404movie:404moviepass@cluster0.fca76c9.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0'

# SETUP
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# MongoDB connection with error handling
try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000, connectTimeoutMS=10000, socketTimeoutMS=10000)
    db = client['uidchecker']
    uids_col = db['uids']
    # Test connection
    client.admin.command('ping')
    logger.info("MongoDB connection successful")
except Exception as e:
    logger.error(f"MongoDB connection failed: {e}")
    raise

def ensure_db_connection():
    """Ensure database connection is active"""
    try:
        client.admin.command('ping')
        return True
    except Exception as e:
        logger.error(f"Database connection lost: {e}")
        return False

# Global variables
last_extractions = []

# Conversation states for dual mode update
MODE_SELECT, SINGLE_UID, BULK_IMG = range(3)

# GEMINI OCR FUNCTION
def gemini_ocr(image_bytes):
    """
    Process image using Gemini OCR to extract text
    """
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        img_base64 = base64.b64encode(image_bytes).decode('utf-8')

        data = {
            "contents": [{
                "parts": [
                    {"text": "Extract all text from this image, especially focusing on UIDs and balance amounts:"},
                    {"inline_data": {
                        "mime_type": "image/jpeg",
                        "data": img_base64
                    }}
                ]
            }]
        }

        response = requests.post(url, json=data, timeout=30)

        if response.ok:
            try:
                result = response.json()
                return result['candidates'][0]['content']['parts'][0]['text']
            except (KeyError, IndexError) as e:
                logger.error(f"Error parsing Gemini response: {e}")
                return ''
        else:
            logger.error(f"Gemini API error: {response.status_code} - {response.text}")
            return ''

    except Exception as e:
        logger.error(f"Error in gemini_ocr: {e}")
        return ''

# BOT COMMAND HANDLERS

def start(update: Update, context: CallbackContext):
    """
    Welcome message for new users
    """
    msg = (
        "👋 *Welcome to UID Verifier Bot!*\n\n"
        "📋 How to use:\n"
        "• Send your UID as text or screenshot\n"
        "• If found in DB, send wallet screenshot\n"
        "• Min balance ₹100 required for full verification\n\n"
        "🔧 Admin commands: /stats, /verified, /nonverified, /all, /update, /dustbin, /del"
    )
    update.message.reply_text(msg, parse_mode='Markdown')

def stats(update: Update, context: CallbackContext):
    """
    Show database statistics (Admin only)
    """
    if update.message.from_user.id != ADMIN_UID:
        update.message.reply_text("❌ Unauthorized access.")
        return

    try:
        total = uids_col.count_documents({})
        verified = uids_col.count_documents({'fully_verified': True})
        not_verified = uids_col.count_documents({'fully_verified': False})
        users = len(uids_col.distinct('user_id'))

        msg = (
            f"📊 *Database Statistics*\n\n"
            f"👥 Unique Users: {users}\n"
            f"📂 Total UIDs: {total}\n"
            f"✅ Fully Verified: {verified}\n"
            f"❌ Not Verified: {not_verified}\n"
            f"📈 Verification Rate: {(verified/total*100) if total > 0 else 0:.1f}%"
        )
        update.message.reply_text(msg, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Error in stats command: {e}")
        update.message.reply_text("❌ Error retrieving statistics.")

def check_newly_verified_uids_silent(update: Update, context: CallbackContext):
    """
    Silently check for UIDs that became verified after admin updates and notify users
    """
    try:
        # Find UIDs that are verified but users haven't been notified yet
        newly_verified = list(uids_col.find({
            'verified': True,
            'fully_verified': False,
            'user_id': {'$exists': True, '$ne': None},
            'notified_for_wallet': {'$ne': True}
        }))

        if not newly_verified:
            return

        notified_count = 0
        for doc in newly_verified:
            try:
                user_id = doc['user_id']
                uid = doc['uid']
                username = doc.get('username', 'User')

                # Send notification to user
                message = (
                    f"🎉 *Great news!*\n\n"
                    f"✅ Your UID {uid} has been verified and found in our database!\n\n"
                    f"📸 Please send your wallet screenshot for balance verification.\n"
                    f"💰 Minimum balance required: ₹100.00"
                )

                context.bot.send_message(
                    chat_id=user_id,
                    text=message,
                    parse_mode='Markdown'
                )

                # Mark as notified and set up for wallet verification
                uids_col.update_one(
                    {'_id': doc['_id']},
                    {'$set': {'notified_for_wallet': True}}
                )

                # Add to pending wallets
                if 'pending_wallets' not in context.bot_data:
                    context.bot_data['pending_wallets'] = {}
                context.bot_data['pending_wallets'][user_id] = uid

                notified_count += 1

            except Exception as e:
                logger.error(f"Error notifying user {doc.get('user_id', 'Unknown')}: {e}")

        if notified_count > 0:
            logger.info(f"Automatically notified {notified_count} users about newly verified UIDs")

    except Exception as e:
        logger.error(f"Error checking newly verified UIDs: {e}")

def check_newly_verified_uids(update: Update, context: CallbackContext):
    """
    Check for UIDs that became verified after admin updates and notify users
    """
    try:
        # Find UIDs that are verified but users haven't been notified yet
        newly_verified = list(uids_col.find({
            'verified': True,
            'fully_verified': False,
            'user_id': {'$exists': True, '$ne': None},
            'notified_for_wallet': {'$ne': True}
        }))

        if not newly_verified:
            update.message.reply_text("ℹ️ No newly verified UIDs found.")
            return

        notified_count = 0
        for doc in newly_verified:
            try:
                user_id = doc['user_id']
                uid = doc['uid']
                username = doc.get('username', 'User')

                # Send notification to user
                message = (
                    f"🎉 *Great news!*\n\n"
                    f"✅ Your UID {uid} has been verified and found in our database!\n\n"
                    f"📸 Please send your wallet screenshot for balance verification.\n"
                    f"💰 Minimum balance required: ₹100.00"
                )

                context.bot.send_message(
                    chat_id=user_id,
                    text=message,
                    parse_mode='Markdown'
                )

                # Mark as notified and set up for wallet verification
                uids_col.update_one(
                    {'_id': doc['_id']},
                    {'$set': {'notified_for_wallet': True}}
                )

                # Add to pending wallets
                if 'pending_wallets' not in context.bot_data:
                    context.bot_data['pending_wallets'] = {}
                context.bot_data['pending_wallets'][user_id] = uid

                notified_count += 1

            except Exception as e:
                logger.error(f"Error notifying user {doc.get('user_id', 'Unknown')}: {e}")

        update.message.reply_text(
            f"📢 *Notification Summary*\n\n"
            f"✅ Notified {notified_count} users about verified UIDs\n"
            f"📸 They have been asked to send wallet screenshots",
            parse_mode='Markdown'
        )

    except Exception as e:
        logger.error(f"Error checking newly verified UIDs: {e}")
        update.message.reply_text("❌ Error checking for newly verified UIDs.")

def check_uid(update, context, uid, user_id, username):
    """
    Check if UID exists in database and update user info
    """
    max_retries = 3
    retry_count = 0

    while retry_count < max_retries:
        try:
            # Check connection first
            if not ensure_db_connection():
                retry_count += 1
                if retry_count >= max_retries:
                    break
                continue

            found = uids_col.find_one({'uid': uid})

            if found:
                # UID found in database
                uids_col.update_one(
                    {'uid': uid}, 
                    {'$set': {
                        'user_id': user_id, 
                        'username': username, 
                        'verified': True,
                        'last_checked': update.message.date
                    }}, 
                    upsert=True
                )
                update.message.reply_text(
                    f"✅ UID {uid} found in database!\n"
                    "📸 Please send your wallet screenshot for balance verification."
                )

                # Store pending wallet verification
                if 'pending_wallets' not in context.bot_data:
                    context.bot_data['pending_wallets'] = {}
                context.bot_data['pending_wallets'][user_id] = uid
                return

            else:
                # UID not found
                uids_col.update_one(
                    {'uid': uid}, 
                    {'$set': {
                        'user_id': user_id, 
                        'username': username, 
                        'verified': False, 
                        'fully_verified': False,
                        'added_date': update.message.date
                    }}, 
                    upsert=True
                )
                update.message.reply_text(f"❌ UID {uid} not found in database. Admin has been notified.")

                # Notify admin
                try:
                    update.message.bot.send_message(
                        chat_id=ADMIN_UID, 
                        text=f"⚠️ New UID verification attempt:\n"
                             f"UID: {uid}\n"
                             f"User: @{username} (ID: {user_id})\n"
                             f"Status: NOT FOUND"
                    )
                except Exception as e:
                    logger.error(f"Error notifying admin: {e}")
                return

        except Exception as e:
            logger.error(f"Error in check_uid (attempt {retry_count + 1}): {e}")
            retry_count += 1
            if retry_count < max_retries:
                import time
                time.sleep(1)  # Wait 1 second before retry

    # If we get here, all retries failed
    update.message.reply_text(
        "❌ Database temporarily unavailable. Please try again in a few minutes.\n"
        f"If the problem persists, contact admin."
    )

def handle_wallet(update: Update, context: CallbackContext):
    """
    Process wallet screenshot for balance verification
    """
    user_id = update.message.from_user.id

    # Check if user has pending wallet verification
    if ('pending_wallets' not in context.bot_data or 
        user_id not in context.bot_data['pending_wallets']):
        update.message.reply_text("❌ No pending UID verification. Please send your UID first.")
        return

    uid = context.bot_data['pending_wallets'][user_id]

    try:
        # Get the highest resolution photo
        photo = update.message.photo[-1]
        img_file = photo.get_file()
        img_bytes = img_file.download_as_bytearray()

        # Process image with Gemini OCR
        update.message.reply_text("🔄 Processing wallet screenshot...")
        extracted_text = gemini_ocr(img_bytes)

        if not extracted_text:
            update.message.reply_text("❌ Could not process image. Please try again with a clearer screenshot.")
            return

        # Extract balance and UID from OCR text
        balance = None
        matched_uid = None

        # Look for balance (₹ or Rs followed by digits)
        balance_patterns = [
            r'(?:₹|Rs\.?|INR)\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)',
            r'(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)\s*(?:₹|Rs\.?|INR)',
            r'Balance[:\s]*(?:₹|Rs\.?|INR)?\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)',
        ]

        for pattern in balance_patterns:
            balance_match = re.search(pattern, extracted_text, re.IGNORECASE)
            if balance_match:
                balance_str = balance_match.group(1).replace(',', '')
                try:
                    balance = float(balance_str)
                    break
                except ValueError:
                    continue

        # Look for UID in the screenshot
        uid_patterns = [
            r'(?:UID|User\s*ID)[:\s]*(\d{6,12})',
            r'(\d{6,12})',  # Any 6-12 digit number
        ]

        for pattern in uid_patterns:
            uid_match = re.search(pattern, extracted_text)
            if uid_match:
                matched_uid = uid_match.group(1)
                if matched_uid == uid:  # Match with expected UID
                    break

        # Verify wallet
        if matched_uid == uid and balance and balance >= 100.0:
            # Successful verification
            uids_col.update_one(
                {'uid': uid}, 
                {'$set': {
                    'fully_verified': True,
                    'wallet_balance': balance,
                    'verification_date': update.message.date
                }}
            )
            update.message.reply_text(
                f"🎉 *Verification Successful!*\n\n"
                f"✅ UID: {uid}\n"
                f"💰 Balance: ₹{balance:.2f}\n"
                f"🏆 Status: Fully Verified"
            , parse_mode='Markdown')

            # Notify admin of successful verification
            try:
                context.bot.send_message(
                    chat_id=ADMIN_UID,
                    text=f"✅ Successful verification:\n"
                         f"UID: {uid}\n"
                         f"User: @{update.message.from_user.username}\n"
                         f"Balance: ₹{balance:.2f}"
                )
            except Exception as e:
                logger.error(f"Error notifying admin: {e}")

        else:
            # Verification failed
            failure_reasons = []
            if matched_uid != uid:
                failure_reasons.append(f"UID mismatch (found: {matched_uid}, expected: {uid})")
            if not balance:
                failure_reasons.append("Could not detect balance")
            elif balance < 100.0:
                failure_reasons.append(f"Insufficient balance (₹{balance:.2f} < ₹100.00)")

            update.message.reply_text(
                f"❌ Wallet verification failed.\n"
                f"Reason: {', '.join(failure_reasons)}\n"
                f"Admin has been notified."
            )

            # Notify admin of failed verification
            try:
                balance_text = f"₹{balance:.2f}" if balance else "Not detected"
                context.bot.send_message(
                    chat_id=ADMIN_UID,
                    text=f"❌ Failed wallet verification:\n"
                         f"UID: {uid}\n"
                         f"User: @{update.message.from_user.username}\n"
                         f"Extracted UID: {matched_uid}\n"
                         f"Balance: {balance_text}\n"
                         f"OCR Text: {extracted_text[:200]}..."
                )
            except Exception as e:
                logger.error(f"Error notifying admin: {e}")

        # Remove from pending wallets
        del context.bot_data['pending_wallets'][user_id]

    except Exception as e:
        logger.error(f"Error in handle_wallet: {e}")
        update.message.reply_text("❌ Error processing wallet screenshot. Please try again.")

# ADMIN UPDATE COMMANDS

def update_cmd(update: Update, context: CallbackContext):
    """
    Start dual mode update conversation (Admin only)
    """
    logger.info(f"Update command called by user {update.message.from_user.id}")

    if update.message.from_user.id != ADMIN_UID:
        logger.warning(f"Unauthorized update access by user {update.message.from_user.id}")
        update.message.reply_text("❌ Unauthorized access.")
        return ConversationHandler.END

    try:
        buttons = [
            [KeyboardButton("Single UID")], 
            [KeyboardButton("Bulk Screenshot")],
            [KeyboardButton("Cancel")]
        ]
        reply_markup = ReplyKeyboardMarkup(buttons, one_time_keyboard=True, resize_keyboard=True)

        update.message.reply_text(
            "🔧 *Admin Update Mode*\n\n"
            "Choose update method:\n"
            "• Single UID: Add one UID at a time\n"
            "• Bulk Screenshot: Extract UIDs from images\n"
            "• Cancel: Exit update mode",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        logger.info("Update command keyboard sent successfully")
        return MODE_SELECT

    except Exception as e:
        logger.error(f"Error in update_cmd: {e}")
        update.message.reply_text("❌ Error starting update mode.")
        return ConversationHandler.END

def handle_mode(update: Update, context: CallbackContext):
    """
    Handle mode selection in update conversation
    """
    logger.info(f"Mode selection: {update.message.text}")

    if update.message.text == "Single UID":
        update.message.reply_text(
            "📝 *Single UID Mode*\n\n"
            "Send the UID to add/update (6-12 digits).\n"
            "Type /done when finished.",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode='Markdown'
        )
        logger.info("Switched to SINGLE_UID mode")
        return SINGLE_UID
    elif update.message.text == "Bulk Screenshot":
        update.message.reply_text(
            "📸 *Bulk Screenshot Mode*\n\n"
            "Send screenshot(s) containing UIDs.\n"
            "Type /done when finished.",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode='Markdown'
        )
        logger.info("Switched to BULK_IMG mode")
        return BULK_IMG
    elif update.message.text == "Cancel":
        update.message.reply_text(
            "❌ Update mode cancelled.",
            reply_markup=ReplyKeyboardRemove()
        )
        logger.info("Update mode cancelled by user")
        return ConversationHandler.END
    else:
        logger.warning(f"Invalid mode selection: {update.message.text}")
        update.message.reply_text(
            "❌ Invalid option. Please select from the buttons provided.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

def handle_single_uid(update: Update, context: CallbackContext):
    """
    Handle single UID update
    """
    # Check if user wants to finish
    if update.message.text and update.message.text.strip().lower() in ['/done', 'done']:
        logger.info(f"Single UID mode completed by user {update.message.from_user.id}")
        update.message.reply_text(
            "✅ Single UID update completed.",
            reply_markup=ReplyKeyboardRemove()
        )
        # Check for newly verified UIDs
        check_newly_verified_uids(update, context)
        return ConversationHandler.END

    uid = update.message.text.strip()

    # Validate UID format
    if not re.match(r'^\d{6,12}$', uid):
        update.message.reply_text(
            "❌ Invalid UID format. Must be 6-12 digits.\n"
            "Send another UID or type /done to finish."
        )
        return SINGLE_UID

    try:
        result = uids_col.update_one(
            {'uid': uid}, 
            {'$set': {
                'verified': True,  # UID is verified since admin added it to database
                'fully_verified': False,
                'admin_added': True,
                'added_date': update.message.date
            }}, 
            upsert=True
        )

        if result.upserted_id:
            update.message.reply_text(
                f"✅ UID {uid} added to database.\n"
                f"Send another UID or type /done to finish."
            )
        else:
            update.message.reply_text(
                f"✅ UID {uid} updated in database.\n"
                f"Send another UID or type /done to finish."
            )
        
        # Check for newly verified UIDs after each single UID update
        check_newly_verified_uids_silent(update, context)

    except Exception as e:
        logger.error(f"Error updating single UID: {e}")
        update.message.reply_text("❌ Database error. Please try again.")

    return SINGLE_UID

def handle_bulk_images(update: Update, context: CallbackContext):
    """
    Handle bulk image processing for UID extraction
    """
    if update.message.text and update.message.text == '/done':
        logger.info(f"Bulk image mode completed by user {update.message.from_user.id}")
        update.message.reply_text(
            "✅ Bulk update completed.",
            reply_markup=ReplyKeyboardRemove()
        )
        # Check for newly verified UIDs
        check_newly_verified_uids(update, context)
        return ConversationHandler.END

    if not update.message.photo:
        update.message.reply_text("📸 Please send an image or /done to finish.")
        return BULK_IMG

    try:
        photo = update.message.photo[-1]
        img_file = photo.get_file()
        img_bytes = img_file.download_as_bytearray()

        # Process image with Gemini OCR
        update.message.reply_text("🔄 Processing image...")
        extracted_text = gemini_ocr(img_bytes)

        if not extracted_text:
            update.message.reply_text("❌ Could not process image. Try another image.")
            return BULK_IMG

        # Extract UIDs from text
        found_uids = re.findall(r'\b\d{6,12}\b', extracted_text)
        found_uids = list(set(found_uids))  # Remove duplicates

        # Store for potential deletion
        last_extractions.append(found_uids)
        if len(last_extractions) > 10:  # Keep only last 10 extractions
            last_extractions.pop(0)

        # Update database
        updated_count = 0
        for uid in found_uids:
            try:
                uids_col.update_one(
                    {'uid': uid}, 
                    {'$set': {
                        'verified': True,  # UID is verified since admin added it to database
                        'fully_verified': False,
                        'admin_added': True,
                        'bulk_added': True,
                        'added_date': update.message.date
                    }}, 
                    upsert=True
                )
                updated_count += 1
            except Exception as e:
                logger.error(f"Error updating UID {uid}: {e}")

        update.message.reply_text(
            f"✅ Processed {updated_count} UID(s) from image.\n"
            f"Found UIDs: {', '.join(found_uids[:10])}{'...' if len(found_uids) > 10 else ''}\n\n"
            f"Send another image or /done to finish."
        )
        
        # Check for newly verified UIDs after each bulk update
        check_newly_verified_uids_silent(update, context)

    except Exception as e:
        logger.error(f"Error in bulk image processing: {e}")
        update.message.reply_text("❌ Error processing image. Please try again.")

    return BULK_IMG

# ADMIN VIEW COMMANDS

def verified(update: Update, context: CallbackContext):
    """
    Show all verified UIDs (Admin only)
    """
    if update.message.from_user.id != ADMIN_UID:
        update.message.reply_text("❌ Unauthorized access.")
        return

    try:
        uids = list(uids_col.find({'fully_verified': True}, {'uid': 1, 'username': 1, 'wallet_balance': 1}))

        if not uids:
            update.message.reply_text("📭 No verified UIDs found.")
            return

        uid_list = []
        for doc in uids[:50]:  # Limit to 50 to avoid message length issues
            balance = doc.get('wallet_balance', 'N/A')
            username = doc.get('username', 'Unknown')
            # Escape markdown characters in username
            safe_username = username.replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace('`', '\\`')
            balance_str = f"{balance:.2f}" if isinstance(balance, (int, float)) and balance != 'N/A' else balance
            uid_list.append(f"✅ {doc['uid']} (@{safe_username}, ₹{balance_str})")

        message = f"🎉 *Verified UIDs ({len(uids)} total)*\n\n" + "\n".join(uid_list)
        if len(uids) > 50:
            message += f"\n\n... and {len(uids) - 50} more"

        update.message.reply_text(message, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Error in verified command: {e}")
        update.message.reply_text("❌ Error retrieving verified UIDs.")

def nonverified(update: Update, context: CallbackContext):
    """
    Show all non-verified UIDs (Admin only)
    """
    if update.message.from_user.id != ADMIN_UID:
        update.message.reply_text("❌ Unauthorized access.")
        return

    try:
        uids = list(uids_col.find({'fully_verified': False}, {'uid': 1, 'username': 1}))

        if not uids:
            update.message.reply_text("📭 No non-verified UIDs found.")
            return

        uid_list = []
        for doc in uids[:50]:  # Limit to 50
            username = doc.get('username', 'Unknown')
            # Escape markdown characters in username
            safe_username = username.replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace('`', '\\`')
            uid_list.append(f"❌ {doc['uid']} (@{safe_username})")

        message = f"⏳ *Non-Verified UIDs ({len(uids)} total)*\n\n" + "\n".join(uid_list)
        if len(uids) > 50:
            message += f"\n\n... and {len(uids) - 50} more"

        update.message.reply_text(message, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Error in nonverified command: {e}")
        update.message.reply_text("❌ Error retrieving non-verified UIDs.")

def all_uids(update: Update, context: CallbackContext):
    """
    Show all UIDs in database (Admin only)
    """
    if update.message.from_user.id != ADMIN_UID:
        update.message.reply_text("❌ Unauthorized access.")
        return

    try:
        total_count = uids_col.count_documents({})
        uids = list(uids_col.find({}, {'uid': 1, 'fully_verified': 1}).limit(50))

        if not uids:
            update.message.reply_text("📭 No UIDs found in database.")
            return

        uid_list = []
        for doc in uids:
            status = "✅" if doc.get('fully_verified') else "❌"
            uid_list.append(f"{status} {doc['uid']}")

        message = f"📂 *All UIDs ({total_count} total)*\n\n" + "\n".join(uid_list)
        if total_count > 50:
            message += f"\n\n... and {total_count - 50} more"

        update.message.reply_text(message, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Error in all command: {e}")
        update.message.reply_text("❌ Error retrieving UIDs.")

# ADMIN DELETE COMMANDS

def dustbin(update: Update, context: CallbackContext):
    """
    Delete specific UIDs from database (Admin only)
    Usage: /dustbin uid1,uid2,uid3
    """
    if update.message.from_user.id != ADMIN_UID:
        update.message.reply_text("❌ Unauthorized access.")
        return

    if not context.args:
        update.message.reply_text(
            "🗑️ *Dustbin Command*\n\n"
            "Usage: `/dustbin uid1,uid2,uid3`\n"
            "Example: `/dustbin 123456,789012,345678`",
            parse_mode='Markdown'
        )
        return

    try:
        # Parse UIDs from arguments
        uid_string = ' '.join(context.args)
        uids = [uid.strip() for uid in uid_string.split(',') if uid.strip()]

        if not uids:
            update.message.reply_text("❌ No valid UIDs provided.")
            return

        # Delete UIDs from database
        result = uids_col.delete_many({"uid": {"$in": uids}})

        update.message.reply_text(
            f"🗑️ *Deletion Complete*\n\n"
            f"Deleted: {result.deleted_count} UID(s)\n"
            f"Requested: {len(uids)} UID(s)",
            parse_mode='Markdown'
        )

        # Log deletion
        logger.info(f"Admin {update.message.from_user.username} deleted {result.deleted_count} UIDs")

    except Exception as e:
        logger.error(f"Error in dustbin command: {e}")
        update.message.reply_text("❌ Error deleting UIDs.")

def del_command(update: Update, context: CallbackContext):
    """
    Delete UIDs from last extractions (Admin only)
    Usage: /del 1-5 (number of last extractions to delete)
    """
    if update.message.from_user.id != ADMIN_UID:
        update.message.reply_text("❌ Unauthorized access.")
        return

    if not context.args:
        update.message.reply_text(
            "🗑️ *Delete Last Extractions*\n\n"
            "Usage: `/del <number>`\n"
            "Example: `/del 2` (deletes UIDs from last 2 extractions)\n\n"
            f"Available extractions: {len(last_extractions)}",
            parse_mode='Markdown'
        )
        return

    try:
        num = int(context.args[0])

        if num <= 0 or num > len(last_extractions):
            update.message.reply_text(f"❌ Invalid number. Available: 1-{len(last_extractions)}")
            return

        # Collect UIDs to delete
        to_delete = []
        for block in last_extractions[:num]:
            to_delete.extend(block)

        if not to_delete:
            update.message.reply_text("❌ No UIDs found in selected extractions.")
            return

        # Delete from database
        result = uids_col.delete_many({"uid": {"$in": to_delete}})

        # Remove from last_extractions
        for _ in range(num):
            if last_extractions:
                last_extractions.pop(0)

        update.message.reply_text(
            f"🗑️ *Deletion Complete*\n\n"
            f"Deleted: {result.deleted_count} UID(s)\n"
            f"From: {num} extraction(s)\n"
            f"Remaining extractions: {len(last_extractions)}",
            parse_mode='Markdown'
        )

    except ValueError:
        update.message.reply_text("❌ Invalid number format.")
    except Exception as e:
        logger.error(f"Error in del command: {e}")
        update.message.reply_text("❌ Error deleting UIDs.")

def done_command(update: Update, context: CallbackContext):
    """
    Standalone done command to check for newly verified UIDs (Admin only)
    """
    if update.message.from_user.id != ADMIN_UID:
        update.message.reply_text("❌ Unauthorized access.")
        return

    update.message.reply_text("🔍 Checking for newly verified UIDs...")
    
    try:
        # Find UIDs that are in database (admin_added=True) and have user_id but users haven't been notified for wallet verification
        newly_verified = list(uids_col.find({
            'admin_added': True,
            'fully_verified': False,
            'user_id': {'$exists': True, '$ne': None},
            'notified_for_wallet': {'$ne': True}
        }))

        if not newly_verified:
            update.message.reply_text("ℹ️ No newly verified UIDs found in non-verified list.")
            return

        notified_count = 0
        for doc in newly_verified:
            try:
                user_id = doc['user_id']
                uid = doc['uid']
                username = doc.get('username', 'User')

                # Send notification to user
                message = (
                    f"🎉 *Great news!*\n\n"
                    f"✅ Your UID {uid} has been verified and found in our database!\n\n"
                    f"📸 Please send your wallet screenshot for balance verification.\n"
                    f"💰 Minimum balance required: ₹100.00"
                )

                context.bot.send_message(
                    chat_id=user_id,
                    text=message,
                    parse_mode='Markdown'
                )

                # Mark as notified and set up for wallet verification
                uids_col.update_one(
                    {'_id': doc['_id']},
                    {'$set': {'notified_for_wallet': True}}
                )

                # Add to pending wallets
                if 'pending_wallets' not in context.bot_data:
                    context.bot_data['pending_wallets'] = {}
                context.bot_data['pending_wallets'][user_id] = uid

                notified_count += 1

            except Exception as e:
                logger.error(f"Error notifying user {doc.get('user_id', 'Unknown')}: {e}")

        # Now check for UIDs that are still unverified and notify users of rejection
        still_unverified = list(uids_col.find({
            'verified': False,
            'fully_verified': False,
            'user_id': {'$exists': True, '$ne': None},
            'rejection_notified': {'$ne': True}
        }))

        rejected_count = 0
        for doc in still_unverified:
            try:
                user_id = doc['user_id']
                uid = doc['uid']

                # Send rejection message to user
                rejection_message = (
                    "*❌ Your UID Got Rejected !*\n\n"
                    "*⚠️ Again Register With Official Link To Get Vip Hack Prediction & Gift Codes At Free !!*\n\n"
                    "*✅ Official Register Link ::*\n"
                    "*https://www.jalwagame4.com/#/register?invitationCode=16887113053*"
                )

                context.bot.send_message(
                    chat_id=user_id,
                    text=rejection_message,
                    parse_mode='Markdown'
                )

                # Mark as rejection notified
                uids_col.update_one(
                    {'_id': doc['_id']},
                    {'$set': {'rejection_notified': True}}
                )

                rejected_count += 1

            except Exception as e:
                logger.error(f"Error sending rejection to user {doc.get('user_id', 'Unknown')}: {e}")

        update.message.reply_text(
            f"📢 *Notification Summary*\n\n"
            f"✅ Found {len(newly_verified)} newly verified UIDs in non-verified list\n"
            f"✅ Notified {notified_count} users about verified UIDs\n"
            f"📸 They have been asked to send wallet screenshots\n\n"
            f"❌ Found {len(still_unverified)} still unverified UIDs\n"
            f"❌ Sent rejection messages to {rejected_count} users",
            parse_mode='Markdown'
        )

    except Exception as e:
        logger.error(f"Error checking newly verified UIDs: {e}")
        update.message.reply_text("❌ Error checking for newly verified UIDs.")

# MESSAGE HANDLERS

def handle_all(update: Update, context: CallbackContext):
    """
    Handle all incoming messages (text and photos)
    """
    user_id = update.message.from_user.id
    username = update.message.from_user.username or 'NoUsername'

    try:
        if update.message.text:
            # Handle text messages - look for UID
            text = update.message.text.upper()
            uid_match = re.search(r'(?:UID\s*)?(\d{6,12})', text)

            if uid_match:
                uid = uid_match.group(1)
                check_uid(update, context, uid, user_id, username)
            else:
                update.message.reply_text(
                    "❓ Please send a valid UID (6-12 digits) or screenshot.\n\n"
                    "Examples:\n"
                    "• 123456789\n"
                    "• UID 123456789\n"
                    "• Screenshot of your UID"
                )

        elif update.message.photo:
            # Handle photo messages - wallet verification or UID extraction
            handle_wallet(update, context)

    except Exception as e:
        logger.error(f"Error in handle_all: {e}")
        update.message.reply_text("❌ Error processing your message. Please try again.")

def cancel_conversation(update: Update, context: CallbackContext):
    """
    Cancel any ongoing conversation
    """
    logger.info(f"Conversation cancelled by user {update.message.from_user.id}")
    update.message.reply_text("❌ Operation cancelled.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# MAIN FUNCTION

def main():
    """
    Main function to start the bot
    """
    try:
        # Create updater and dispatcher with conflict resolution
        updater = Updater(BOT_TOKEN, use_context=True)
        dp = updater.dispatcher
        
        # Clear any pending updates to prevent conflicts
        try:
            updater.bot.get_updates(offset=-1, timeout=1)
        except Exception as e:
            logger.warning(f"Could not clear pending updates: {e}")

        # Initialize bot data
        if 'pending_wallets' not in dp.bot_data:
            dp.bot_data['pending_wallets'] = {}

        # Conversation handler for update command with proper state management
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('update', update_cmd)],
            states={
                MODE_SELECT: [MessageHandler(Filters.text & ~Filters.command, handle_mode)],
                SINGLE_UID: [
                    MessageHandler(Filters.text & ~Filters.command, handle_single_uid),
                    CommandHandler('done', handle_single_uid)
                ],
                BULK_IMG: [
                    MessageHandler(Filters.photo, handle_bulk_images),
                    MessageHandler(Filters.text & ~Filters.command, handle_bulk_images),
                    CommandHandler('done', handle_bulk_images)
                ]
            },
            fallbacks=[
                CommandHandler('cancel', cancel_conversation),
                CommandHandler('done', cancel_conversation),
                CommandHandler('start', cancel_conversation),
                CommandHandler('stats', cancel_conversation),
                CommandHandler('update', cancel_conversation)  # Handle new update command during conversation
            ],
            persistent=False,
            name="update_conversation",
            per_chat=True,
            per_user=True,
            per_message=False
        )

        # Add handlers
        dp.add_handler(CommandHandler("start", start))
        dp.add_handler(CommandHandler("stats", stats))
        dp.add_handler(CommandHandler("verified", verified))
        dp.add_handler(CommandHandler("nonverified", nonverified))
        dp.add_handler(CommandHandler("all", all_uids))
        dp.add_handler(CommandHandler("dustbin", dustbin))
        dp.add_handler(CommandHandler("del", del_command))
        dp.add_handler(CommandHandler("done", done_command))
        dp.add_handler(conv_handler)
        dp.add_handler(MessageHandler(Filters.all, handle_all))

        # Error handler with conflict detection
        def error_handler(update, context):
            error_msg = str(context.error)
            if "Conflict" in error_msg and "getUpdates" in error_msg:
                logger.error("Bot conflict detected - another instance may be running")
                logger.error("Please stop all other bot instances and restart")
            else:
                logger.error(f"Update {update} caused error {context.error}")

        dp.add_error_handler(error_handler)

        # Start bot
        logger.info("Starting UID Verification Bot...")
        updater.start_polling(drop_pending_updates=True)
        logger.info("Bot is running! Press Ctrl+C to stop.")
        updater.idle()
        
        # Graceful shutdown
        logger.info("Bot stopped gracefully")
        updater.stop()

    except Exception as e:
        logger.error(f"Error starting bot: {e}")
        raise

if __name__ == '__main__':
    main()