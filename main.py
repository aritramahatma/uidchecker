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
BOT_TOKEN = os.getenv('BOT_TOKEN',
                      '8019817575:AAF5XlqAzVP2p5xakApDxQTxx96UqXoH79M')
ADMIN_UID = int(os.getenv('ADMIN_UID', '6490401448'))
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY',
                           'AIzaSyAGDi2WslEe8VvBc7v3-dwpEmJobE6df1o')
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


def ensure_db_connection():
    """Ensure database connection is active"""
    try:
        client.admin.command('ping')
        return True
    except Exception as e:
        logger.error(f"Database connection lost: {e}")
        return False


def update_user_stats(user_id, action):
    """Update user statistics in database"""
    try:
        # Get or create user stats document
        user_doc = user_stats_col.find_one({'user_id': user_id})

        if not user_doc:
            # New user - create document
            user_stats_col.insert_one({
                'user_id': user_id,
                'first_seen': datetime.now(),
                'last_seen': datetime.now(),
                'is_blocked': False,
                'actions': [action]
            })

            # Update global stats for new user
            global_stats = user_stats_col.find_one({'_id': 'global_stats'})
            if not global_stats:
                user_stats_col.insert_one({
                    '_id': 'global_stats',
                    'total_users': 1,
                    'blocked_users': 0
                })
            else:
                user_stats_col.update_one({'_id': 'global_stats'},
                                          {'$inc': {
                                              'total_users': 1
                                          }})
        else:
            # Update existing user
            user_stats_col.update_one({'user_id': user_id}, {
                '$set': {
                    'last_seen': datetime.now()
                },
                '$push': {
                    'actions': action
                }
            })
    except Exception as e:
        logger.error(f"Error updating user stats: {e}")


def check_blocked_users(context):
    """Check for blocked users by attempting to get their info and update stats"""
    try:
        # Get all users who are not marked as blocked
        unblocked_users = list(
            user_stats_col.find({
                '$or': [{
                    'is_blocked': {
                        '$ne': True
                    }
                }, {
                    'is_blocked': {
                        '$exists': False
                    }
                }],
                'user_id': {
                    '$ne': 'global_stats',
                    '$exists': True
                }
            }))

        newly_blocked = 0
        for user_doc in unblocked_users:
            user_id = user_doc['user_id']
            try:
                # Try to get basic info about the user
                context.bot.get_chat(user_id)
            except Exception as e:
                error_msg = str(e).lower()
                if any(keyword in error_msg for keyword in [
                        "blocked", "deactivated", "user is deactivated",
                        "bot was blocked", "forbidden"
                ]):
                    # User has blocked the bot, update stats
                    user_stats_col.update_one({'user_id': user_id}, {
                        '$set': {
                            'is_blocked': True,
                            'blocked_date': datetime.now(),
                            'blocked_by_user': True
                        }
                    })
                    newly_blocked += 1
                    logger.info(
                        f"Detected that user {user_id} has blocked the bot")

        if newly_blocked > 0:
            # Update global blocked count and decrease total users
            user_stats_col.update_one(
                {'_id': 'global_stats'},
                {
                    '$inc': {
                        'blocked_users': newly_blocked,
                        'total_users':
                        -newly_blocked  # Subtract newly blocked users from total
                    }
                },
                upsert=True)
            logger.info(
                f"Updated blocked users count by {newly_blocked} and decreased total users by {newly_blocked}"
            )

        return newly_blocked

    except Exception as e:
        logger.error(f"Error checking blocked users: {e}")
        return 0


def get_user_activity_stats():
    """Get comprehensive user activity statistics"""
    try:
        # Get global stats
        global_stats = user_stats_col.find_one({'_id': 'global_stats'})
        if not global_stats:
            global_stats = {'total_users': 0, 'blocked_users': 0}

        # Count current users (fallback if global stats not accurate)
        actual_total_users = user_stats_col.count_documents(
            {'user_id': {
                '$ne': 'global_stats'
            }})
        if actual_total_users > global_stats.get('total_users', 0):
            # Update global stats if count is higher
            user_stats_col.update_one(
                {'_id': 'global_stats'},
                {'$set': {
                    'total_users': actual_total_users
                }},
                upsert=True)
            global_stats['total_users'] = actual_total_users

        # Count blocked users - use actual count from database
        actual_blocked_users = user_stats_col.count_documents(
            {'is_blocked': True})

        # Update global stats if actual count differs
        if actual_blocked_users != global_stats.get('blocked_users', 0):
            user_stats_col.update_one(
                {'_id': 'global_stats'},
                {'$set': {
                    'blocked_users': actual_blocked_users
                }},
                upsert=True)

        # UID statistics
        total_uids = uids_col.count_documents({})
        verified_uids = uids_col.count_documents({'verified': True})
        fully_verified_users = uids_col.count_documents(
            {'fully_verified': True})
        non_verified_users = uids_col.count_documents(
            {'fully_verified': False})
        admin_updated_uids = uids_col.count_documents({'admin_added': True})
        pending_wallet_verifications = uids_col.count_documents({
            'verified':
            True,
            'fully_verified':
            False,
            'notified_for_wallet':
            True
        })
        users_with_valid_balance = uids_col.count_documents({
            'fully_verified': True,
            'wallet_balance': {
                '$gte': 100
            }
        })

        return {
            'total_users': global_stats.get('total_users', actual_total_users),
            'blocked_users': actual_blocked_users,
            'verified_uids': verified_uids,
            'fully_verified_users': fully_verified_users,
            'non_verified_users': non_verified_users,
            'admin_updated_uids': admin_updated_uids,
            'pending_wallet_verifications': pending_wallet_verifications,
            'users_with_valid_balance': users_with_valid_balance
        }
    except Exception as e:
        logger.error(f"Error getting user activity stats: {e}")
        return {
            'total_users': 0,
            'blocked_users': 0,
            'verified_uids': 0,
            'fully_verified_users': 0,
            'non_verified_users': 0,
            'admin_updated_uids': 0,
            'pending_wallet_verifications': 0,
            'users_with_valid_balance': 0
        }


# Global variables
last_extractions = []
restrict_mode = True  # Global restriction mode (ON by default)

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
                "parts": [{
                    "text":
                    "Extract all text from this image, especially focusing on UIDs and balance amounts:"
                }, {
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": img_base64
                    }
                }]
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
            logger.error(
                f"Gemini API error: {response.status_code} - {response.text}")
            return ''

    except Exception as e:
        logger.error(f"Error in gemini_ocr: {e}")
        return ''


def detect_fake_screenshot(image_bytes):
    """
    Use Gemini AI to detect if a screenshot has been digitally edited or manipulated
    Returns: (is_unedited, confidence_score, suspicious_elements, analysis)
    """
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        img_base64 = base64.b64encode(image_bytes).decode('utf-8')

        # Focused prompt for detecting digital editing and manipulation
        detection_prompt = """
DIGITAL EDITING DETECTION: Analyze this screenshot to detect if it has been digitally edited or manipulated using photo editing software.

IMPORTANT: Only flag as EDITED if you find CLEAR evidence of digital manipulation. Natural compression artifacts, normal screenshot quality variations, and typical mobile app interface elements should NOT be considered editing.

FOCUS ON THESE EDITING INDICATORS:

1. TEXT EDITING SIGNS:
   - Text that looks pasted or overlaid (not natural UI text)
   - Inconsistent fonts within similar elements
   - Text with different pixelation/quality than surroundings
   - Numbers that appear copied from elsewhere
   - Text with unnatural edges or artifacts
   - Inconsistent text alignment or spacing

2. DIGITAL MANIPULATION ARTIFACTS:
   - Copy-paste selection artifacts
   - Clone stamp tool marks
   - Brush tool evidence
   - Selection box remnants
   - Layer blend inconsistencies
   - Compression artifacts around edited areas (not normal JPEG compression)

3. VISUAL EDITING EVIDENCE:
   - Color mismatches in similar elements
   - Inconsistent lighting/shadows on text
   - Pixelation differences between areas (not normal compression)
   - Unnatural sharp edges around numbers/text
   - Background inconsistencies behind text
   - Different image quality in specific regions

4. PHOTO EDITING SOFTWARE TRACES:
   - Healing tool artifacts
   - Content-aware fill marks
   - Transform tool distortions
   - Filter inconsistencies
   - Digital watermark removal traces

PROVIDE ANALYSIS IN THIS FORMAT:
EDITING_STATUS: [UNEDITED/EDITED/HEAVILY_EDITED]
CONFIDENCE: [0-100]%
EDITING_EVIDENCE: [List specific editing signs found, or "None found" if unedited]
TEXT_ALTERED: [YES/NO - Details of text manipulation]
DIGITAL_ARTIFACTS: [YES/NO - Software editing traces]
RECOMMENDATION: [ACCEPT/REVIEW/REJECT]

If NO clear editing evidence is found, mark as UNEDITED with ACCEPT recommendation.
Focus ONLY on whether the image has been digitally modified/edited, not on whether the content is "real" or "fake".
"""

        data = {
            "contents": [{
                "parts": [{
                    "text": detection_prompt
                }, {
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": img_base64
                    }
                }]
            }],
            "generationConfig": {
                "temperature": 0.1,  # Low temperature for consistent analysis
                "maxOutputTokens": 1000
            }
        }

        response = requests.post(url, json=data, timeout=30)

        if response.ok:
            try:
                result = response.json()
                analysis = result['candidates'][0]['content']['parts'][0][
                    'text']

                # Parse the analysis
                is_unedited = True
                confidence_score = 100
                suspicious_elements = []

                # Check editing status
                if "EDITING_STATUS:" in analysis:
                    edit_line = [
                        line for line in analysis.split('\n')
                        if 'EDITING_STATUS:' in line
                    ][0]
                    if "UNEDITED" in edit_line.upper():
                        is_unedited = True
                    elif any(word in edit_line.upper()
                             for word in ['EDITED', 'HEAVILY_EDITED']):
                        is_unedited = False

                # Get confidence score
                if "CONFIDENCE:" in analysis:
                    conf_line = [
                        line for line in analysis.split('\n')
                        if 'CONFIDENCE:' in line
                    ][0]
                    conf_match = re.search(r'(\d+)', conf_line)
                    if conf_match:
                        confidence_score = int(conf_match.group(1))

                # Get evidence only if editing was detected
                if "EDITING_EVIDENCE:" in analysis and not is_unedited:
                    evidence_line = [
                        line for line in analysis.split('\n')
                        if 'EDITING_EVIDENCE:' in line
                    ]
                    if evidence_line:
                        evidence_text = evidence_line[0].replace(
                            'EDITING_EVIDENCE:', '').strip()
                        if evidence_text and evidence_text.lower() not in [
                                'none', 'no evidence', 'not found'
                        ]:
                            suspicious_elements.append(evidence_text)

                # Only check for specific editing indicators if not already marked as unedited
                if is_unedited:
                    # Additional checks for definitive editing indicators
                    if any(keyword in analysis.upper() for keyword in [
                            'TEXT_ALTERED: YES', 'DIGITAL_ARTIFACTS: YES',
                            'RECOMMENDATION: REJECT'
                    ]):
                        is_unedited = False

                return is_unedited, confidence_score, suspicious_elements, analysis

            except (KeyError, IndexError) as e:
                logger.error(f"Error parsing editing detection response: {e}")
                return False, 0, ["Error parsing AI response"], ""
        else:
            logger.error(
                f"Gemini editing detection API error: {response.status_code} - {response.text}"
            )
            return False, 0, ["API Error"], ""

    except Exception as e:
        logger.error(f"Error in detect_fake_screenshot: {e}")
        return False, 0, [f"Detection error: {str(e)}"], ""


def handle_bonus_button(update: Update, context: CallbackContext):
    """
    Handle the 'Bonus' button callback
    """
    query = update.callback_query
    query.answer()

    # Create bonus message in bold mode
    bonus_msg = ("*😱 OMG! Highest Ever — TRIPLE Deposit Bonus Offer 🛍*\n\n"
                 "*⚡️ Register Now & Claim Your Bonus:*\n\n"
                 "*♙ Deposit ₹100 ⮕ Get ₹28 Bonus*\n"
                 "*♙ Deposit ₹300 ⮕ Get ₹48 Bonus*\n"
                 "*♙Deposit ₹500 ⮕ Get ₹108 Bonus*\n"
                 "*♙ Deposit ₹1000 ⮕ Get ₹188 Bonus*\n"
                 "*♙ Deposit ₹5000 ⮕ Get ₹488 Bonus*\n\n"
                 "*💎 PLUS — Daily Gift Codes Worth ₹50!*\n"
                 "*🎳 ₹20 + ₹20 + ₹10 — Every Day for All Users*\n\n"
                 "*⏳ Limited-Time Offer — Grab It Before It's Gone!*")

    # Create inline keyboard with Register Here and Back buttons
    keyboard = [[
        InlineKeyboardButton(
            "Register Here",
            url="https://www.jalwa.fun/#/register?invitationCode=66385106362")
    ], [InlineKeyboardButton("🔙 Back", callback_data="back")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Edit existing message with new photo and content
    try:
        query.edit_message_media(media=InputMediaPhoto(
            media="https://files.catbox.moe/iaooec.webp",
            caption=bonus_msg,
            parse_mode='Markdown'),
                                 reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Error editing message in bonus button: {e}")
        # Fallback to editing just caption if photo edit fails
        try:
            query.edit_message_caption(caption=bonus_msg,
                                       parse_mode='Markdown',
                                       reply_markup=reply_markup)
        except Exception as e2:
            logger.error(f"Error editing caption in bonus button: {e2}")


def handle_gift_codes_button(update: Update, context: CallbackContext):
    """
    Handle the 'Gift Codes' button callback
    """
    query = update.callback_query
    query.answer()

    # Create gift codes message in bold mode
    gift_codes_msg = (
        "*📋 Join All Channels To Unlock the Gift Code!*\n\n"
        "*🎁 Earn More Exclusive Gift Codes From Here*\n\n"
        "*⚠️ You must join ALL 4 channels below to unlock gift codes:*")

    # Create inline keyboard with JOIN buttons for all 4 channels and unlock button
    keyboard = [[
        InlineKeyboardButton("JOIN", url="https://t.me/+vge9Lu_k4wUyYTY9"),
        InlineKeyboardButton("JOIN", url="https://t.me/+7io6Ktb7WwQzZjll")
    ],
                [
                    InlineKeyboardButton("JOIN",
                                         url="https://t.me/+mm3dF_L31cg2NjA1"),
                    InlineKeyboardButton("JOIN",
                                         url="https://t.me/+2u_ekSv7S71lZTll")
                ],
                [
                    InlineKeyboardButton("🔐 Unlock Gift Code",
                                         callback_data="unlock_gift_code")
                ], [InlineKeyboardButton("🔙 Back", callback_data="back")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Edit existing message with new photo and content
    try:
        query.edit_message_media(media=InputMediaPhoto(
            media="https://files.catbox.moe/zk8ir9.webp",
            caption=gift_codes_msg,
            parse_mode='Markdown'),
                                 reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Error editing message in gift codes button: {e}")
        # Fallback to editing just caption if photo edit fails
        try:
            query.edit_message_caption(caption=gift_codes_msg,
                                       parse_mode='Markdown',
                                       reply_markup=reply_markup)
        except Exception as e2:
            logger.error(f"Error editing caption in gift codes button: {e2}")


def get_current_gift_code():
    """
    Get the current gift code from database
    """
    try:
        gift_code_doc = gift_codes_col.find_one({'active': True})
        if gift_code_doc:
            return gift_code_doc
        else:
            # Create default gift code if none exists
            from datetime import timezone, timedelta
            ist = timezone(timedelta(hours=5, minutes=30))
            current_time = datetime.now(ist).strftime(
                "%d/%m/%YYYY at %I:%M %p IST")
            default_code = {
                'code': 'F0394C76A4CC0B6716EED375826CAEB',
                'updated_date': current_time,
                'active': True,
                'created_at': datetime.now()
            }
            gift_codes_col.insert_one(default_code)
            return default_code
    except Exception as e:
        logger.error(f"Error getting gift code: {e}")
        from datetime import timezone, timedelta
        ist = timezone(timedelta(hours=5, minutes=30))
        current_time = datetime.now(ist).strftime(
            "%d/%m/%YYYY at %I:%M %p IST")
        return {
            'code': 'F0394C76A4CC0B6716EED375826CAEB',
            'updated_date': current_time
        }


def handle_verify_membership(update: Update, context: CallbackContext):
    """
    Handle the 'I Joined All Channels' verification button with real channel verification
    """
    query = update.callback_query
    user_id = query.from_user.id

    # Channel IDs to check (replace with your actual channel IDs)
    # For private channels, you need the numeric ID (e.g., -1001234567890)
    # For public channels, you can use @channelname or numeric ID
    channels_to_check = [
        "-1002192358931",  # Your first private channel ID
        "-1002573774872",  # Your second private channel ID
        "-1002586023209",  # Your third private channel ID
        "-1002646737506",  # Your fourth private channel ID
    ]

    try:
        # Check membership for each channel
        all_joined = True
        failed_channels = []
        verification_errors = []

        for channel_id in channels_to_check:
            try:
                member = context.bot.get_chat_member(chat_id=channel_id,
                                                     user_id=user_id)
                # Only allow actual members, administrators, and creators
                # Exclude: left, kicked, restricted, and pending join requests
                if member.status in ['member', 'administrator', 'creator']:
                    logger.info(
                        f"User {user_id} successfully verified in channel {channel_id}: status = {member.status}"
                    )
                else:
                    # User is not an actual member (could be left, kicked, restricted, or pending)
                    all_joined = False
                    failed_channels.append(channel_id)
                    logger.info(
                        f"User {user_id} not properly joined channel {channel_id}: status = {member.status}"
                    )

            except Exception as e:
                error_msg = str(e).lower()
                logger.error(
                    f"Error checking membership for channel {channel_id}: {e}")

                # Check if it's a bot permission issue
                if "bot was kicked" in error_msg or "forbidden" in error_msg or "chat not found" in error_msg:
                    logger.error(
                        f"Bot permission issue for channel {channel_id}: Bot needs to be admin with proper permissions"
                    )
                    verification_errors.append(
                        f"Bot access denied to channel {channel_id}")
                    all_joined = False
                    failed_channels.append(channel_id)
                else:
                    # Other errors - log but don't fail verification
                    logger.warning(
                        f"Bot cannot access channel {channel_id}, allowing user {user_id} anyway: {e}"
                    )
                    verification_errors.append(str(e))

        # Grant access if no definitive failures (allowing bot access issues)
        if len(failed_channels) == 0:
            # Store user as verified
            if 'verified_members' not in context.bot_data:
                context.bot_data['verified_members'] = set()

            context.bot_data['verified_members'].add(user_id)
            query.answer(
                "✅ Membership verified! You can now unlock gift codes.",
                show_alert=True)

            logger.info(
                f"User {user_id} successfully verified membership in all channels"
            )

            # Update the message to show verification success
            verification_msg = (
                "*🎉 CONGRATULATIONS! 🎉*\n\n"
                "*✅ Membership Verified Successfully!*\n\n"
                "*🎁 You can now unlock exclusive gift codes!*\n\n"
                "*🙏 Thank you for joining all our channels!*\n"
                "*🎊 Welcome to our VIP community! 🎊*")

            keyboard = [[
                InlineKeyboardButton("🔐 Unlock Gift Code",
                                     callback_data="unlock_gift_code")
            ], [InlineKeyboardButton("🔙 Back", callback_data="back")]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            try:
                query.edit_message_caption(caption=verification_msg,
                                           parse_mode='Markdown',
                                           reply_markup=reply_markup)
            except Exception as e:
                logger.error(f"Error updating verification message: {e}")
        else:
            # Verification failed - show which channels they haven't joined
            query.answer("❌ Please join all channels first!", show_alert=True)

            logger.warning(
                f"User {user_id} failed membership verification. Failed channels: {failed_channels}, Errors: {verification_errors}"
            )

            failed_msg = (
                "*❌ Membership Verification Failed!*\n\n"
                "*🔒 You haven't joined all required channels yet.*\n\n"
                "*Please join ALL 4 channels below and try again.*\n\n"
                "*⚠️ Note: It may take a few seconds for the system to detect your membership.*"
            )

            keyboard = [
                [
                    InlineKeyboardButton("JOIN",
                                         url="https://t.me/+vge9Lu_k4wUyYTY9"),
                    InlineKeyboardButton("JOIN",
                                         url="https://t.me/+7io6Ktb7WwQzZjll")
                ],
                [
                    InlineKeyboardButton("JOIN",
                                         url="https://t.me/+mm3dF_L31cg2NjA1"),
                    InlineKeyboardButton("JOIN",
                                         url="https://t.me/+2u_ekSv7S71lZTll")
                ],
                [
                    InlineKeyboardButton("🔐 Unlock Gift Code",
                                         callback_data="unlock_gift_code")
                ], [InlineKeyboardButton("🔙 Back", callback_data="back")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            try:
                query.edit_message_caption(caption=failed_msg,
                                           parse_mode='Markdown',
                                           reply_markup=reply_markup)
            except Exception as e:
                logger.error(f"Error showing failed verification message: {e}")

            # Make sure user is NOT added to verified members
            if 'verified_members' in context.bot_data and user_id in context.bot_data[
                    'verified_members']:
                context.bot_data['verified_members'].discard(user_id)
            return

    except Exception as e:
        logger.error(
            f"Critical error in membership verification for user {user_id}: {e}"
        )
        # Fallback - show error message and deny access
        query.answer("❌ Error checking membership. Please try again later.",
                     show_alert=True)

        # Make sure user is NOT added to verified members on error
        if 'verified_members' in context.bot_data and user_id in context.bot_data[
                'verified_members']:
            context.bot_data['verified_members'].discard(user_id)
        return


def handle_unlock_gift_code(update: Update, context: CallbackContext):
    """
    Handle the 'Unlock Gift Code' button callback - only allow verified users who joined channels
    """
    query = update.callback_query
    user_id = query.from_user.id

    # Channel IDs to check - make sure these are correct
    channels_to_check = [
        "-1002192358931",  # Your first private channel ID
        "-1002573774872",  # Your second private channel ID
        "-1002586023209",  # Your third private channel ID
        "-1002646737506",  # Your fourth private channel ID
    ]

    try:
        # Check membership for each channel with strict verification
        all_joined = True
        failed_channels = []
        verification_details = []

        for channel_id in channels_to_check:
            member_verified = False

            try:
                # Get member info from Telegram API - single attempt, no retries to avoid confusion
                member = context.bot.get_chat_member(chat_id=channel_id,
                                                     user_id=user_id)
                member_status = member.status

                verification_details.append(
                    f"Channel {channel_id}: Status = {member_status}")
                logger.info(
                    f"🔍 User {user_id} status in channel {channel_id}: {member_status}"
                )

                # STRICT verification - ONLY allow confirmed members
                if member_status == 'member':
                    member_verified = True
                    logger.info(
                        f"✅ User {user_id} is CONFIRMED MEMBER in channel {channel_id}"
                    )
                elif member_status == 'administrator':
                    member_verified = True
                    logger.info(
                        f"✅ User {user_id} is ADMIN in channel {channel_id}")
                elif member_status == 'creator':
                    member_verified = True
                    logger.info(
                        f"✅ User {user_id} is CREATOR of channel {channel_id}")
                else:
                    # ANY other status means NOT a proper member
                    logger.warning(
                        f"❌ User {user_id} status '{member_status}' = NOT A MEMBER of channel {channel_id}"
                    )
                    if member_status == 'left':
                        logger.warning(
                            f"❌ User {user_id} LEFT the channel {channel_id}")
                    elif member_status == 'kicked':
                        logger.warning(
                            f"❌ User {user_id} was BANNED from channel {channel_id}"
                        )
                    elif member_status == 'restricted':
                        logger.warning(
                            f"❌ User {user_id} is RESTRICTED in channel {channel_id}"
                        )

            except Exception as e:
                error_msg = str(e).lower()
                verification_details.append(
                    f"Channel {channel_id}: Error = {str(e)}")
                logger.error(
                    f"❌ Error checking membership for channel {channel_id}: {e}"
                )

                # Handle specific error cases - be strict about errors
                if "user not found" in error_msg:
                    logger.error(
                        f"❌ User {user_id} NOT FOUND in channel {channel_id} - DEFINITELY not a member"
                    )
                elif "chat not found" in error_msg:
                    logger.error(
                        f"❌ Channel {channel_id} NOT FOUND - check channel ID")
                elif "forbidden" in error_msg or "bot was kicked" in error_msg:
                    logger.error(
                        f"❌ Bot has NO ACCESS to channel {channel_id} - check bot permissions"
                    )
                    # DO NOT allow access for bot permission issues - this could be exploited
                else:
                    logger.error(
                        f"❌ Unknown error for channel {channel_id}: {e}")

                # Any error = user is NOT verified
                member_verified = False

            # If user is not verified for this channel
            if not member_verified:
                all_joined = False
                failed_channels.append(channel_id)

        # Log detailed verification results
        logger.info(f"🔍 FINAL VERIFICATION RESULT for user {user_id}:")
        logger.info(f"   All joined: {all_joined}")
        logger.info(f"   Failed channels: {failed_channels}")
        for detail in verification_details:
            logger.info(f"   {detail}")

        # If user hasn't joined all channels, DENY access
        if not all_joined:
            query.answer("❌ ACCESS DENIED! You must join our channels first!",
                         show_alert=True)

            not_joined_msg = (
                "*🚫 ACCESS DENIED - NOT A CHANNEL MEMBER!*\n\n"
                "*❌ You are NOT a confirmed member of our private channels!*\n\n"
                "*🔒 TO UNLOCK GIFT CODES:*\n"
                "*1️⃣ You must join ALL 4 private channels first*\n"
                "*2️⃣ Actually JOIN the channels (not just visit)*\n"
                "*3️⃣ Try unlocking again*\n\n"
                "*⚠️ IMPORTANT: You must be a CONFIRMED MEMBER of ALL 4 channels!*\n"
                "*🚫 Visiting or previewing the channels is NOT enough!*")

            keyboard = [[
                InlineKeyboardButton("🔙 Back to Menu", callback_data="back")
            ]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            try:
                query.edit_message_caption(caption=not_joined_msg,
                                           parse_mode='Markdown',
                                           reply_markup=reply_markup)
            except Exception as e:
                logger.error(
                    f"Error showing channel membership required message: {e}")
                # Fallback - send new message
                try:
                    query.message.reply_text(not_joined_msg,
                                             parse_mode='Markdown',
                                             reply_markup=reply_markup)
                except Exception as e2:
                    logger.error(f"Error sending fallback message: {e2}")
            return

    except Exception as e:
        logger.error(f"💥 CRITICAL ERROR checking channel membership: {e}")
        query.answer("❌ System error checking membership. Please try again.",
                     show_alert=True)
        return

    # User has joined all channels, proceed to show gift code
    query.answer("✅ MEMBERSHIP VERIFIED! Unlocking gift code...",
                 show_alert=True)
    logger.info(f"🎉 User {user_id} SUCCESSFULLY VERIFIED - showing gift code")

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

        # Create back button
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Edit existing message with gift code
        try:
            query.edit_message_media(media=InputMediaPhoto(
                media="https://files.catbox.moe/gyeskx.webp",
                caption=gift_code_msg,
                parse_mode='Markdown'),
                                     reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Error editing message with gift code photo: {e}")
            # Fallback to editing just caption
            try:
                query.edit_message_caption(caption=gift_code_msg,
                                           parse_mode='Markdown',
                                           reply_markup=reply_markup)
            except Exception as e2:
                logger.error(f"Error editing caption with gift code: {e2}")

    except Exception as e:
        logger.error(f"Error in unlock gift code handler: {e}")
        query.answer("❌ Error processing request. Please try again.",
                     show_alert=True)


def handle_back_button(update: Update, context: CallbackContext):
    """
    Handle the 'Back' button callback - return to verification success main menu
    """
    query = update.callback_query
    query.answer()

    # Create inline keyboard with 4 buttons (verification success menu)
    keyboard = [[
        InlineKeyboardButton("Prediction", callback_data="prediction"),
        InlineKeyboardButton("Gift Codes", callback_data="gift_codes")
    ],
                [
                    InlineKeyboardButton("Bonus", callback_data="bonus"),
                    InlineKeyboardButton("Support", callback_data="support")
                ]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Main menu verification success message
    msg = (
        f"*✅ Verification Successful! 🎯*\n\n"
        f"*You're now eligible for VIP AI Predictions ⚡️& Daily Gift Codes worth up to ₹500 🎁*\n\n"
        f"*📋 UID: 9413264*\n"
        f"*💰 Balance: ₹607.56*\n"
        f"*🏆 Status: Fully Verified*\n\n"
        f"*👤Approved by Admin!*\n"
        f"*⚠️ Note: Your access is valid for 7 days 📆*")

    # Edit the current message to show main menu instead of sending new one
    try:
        query.edit_message_media(media=InputMediaPhoto(
            media="https://files.catbox.moe/4hd1vl.png",
            caption=msg,
            parse_mode='Markdown'),
                                 reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Error editing message in back button: {e}")
        # Fallback to editing just caption if photo edit fails
        try:
            query.edit_message_caption(caption=msg,
                                       parse_mode='Markdown',
                                       reply_markup=reply_markup)
        except Exception as e2:
            logger.error(f"Error editing caption in back button: {e2}")
            # Last fallback - send new message
            query.message.reply_text(msg,
                                     parse_mode='Markdown',
                                     reply_markup=reply_markup)


# BOT COMMAND HANDLERS


def start(update: Update, context: CallbackContext):
    """
    Welcome message for new users with image and buttons
    """
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
        "*Note : Access will expire in 7 Days 🗓️*")

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


def handle_prediction_button(update: Update, context: CallbackContext):
    """
    Handle the 'Prediction' button callback
    """
    query = update.callback_query
    query.answer()

    # Prediction menu message showing game selection
    prediction_msg = ("*🎮 Select Your Game*\n\n"
                      "*Choose which game you want predictions for:*\n\n"
                      "*🎯 Wingo – Color & Number Predictions*\n"
                      "*🚀 Aviator – Multiplier Predictions*\n\n"
                      "*More games coming soon 🔜*")

    # Create keyboard with Wingo and Aviator buttons, plus new games
    keyboard = [[
        InlineKeyboardButton("🎯 Wingo", callback_data="wingo_menu"),
        InlineKeyboardButton("🚀 Aviator", callback_data="aviator_menu")
    ],
                [
                    InlineKeyboardButton("💎 Mines Pro",
                                         callback_data="mines_menu"),
                    InlineKeyboardButton("🐲 Dragon Tiger",
                                         callback_data="dragon_tiger_menu")
                ], [InlineKeyboardButton("🔙 Back", callback_data="back")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Edit existing message with game selection image and content
    try:
        query.edit_message_media(media=InputMediaPhoto(
            media="https://files.catbox.moe/szmfsp.webp",
            caption=prediction_msg,
            parse_mode='Markdown'),
                                 reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Error editing message in prediction button: {e}")
        # Fallback to editing just caption if photo edit fails
        try:
            query.edit_message_caption(caption=prediction_msg,
                                       parse_mode='Markdown',
                                       reply_markup=reply_markup)
        except Exception as e2:
            logger.error(f"Error sending prediction menu message: {e2}")


def handle_manual_prediction_button(update: Update, context: CallbackContext):
    """
    Handle the 'Manual Prediction' button callback (same as old start prediction)
    """
    query = update.callback_query
    query.answer()

    # Request 3 digits message
    digits_request_msg = ("*🔢 Send the Last 3 Digits of the Period Number*\n"
                          "*📟 To Instantly Receive Your VIP Prediction!*\n\n"
                          "*⚙️ Example: If Period is 456123, just send 123*")

    # Create keyboard with Back button only
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="prediction")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Send new message with digits request instead of editing
    try:
        sent_message = query.message.reply_text(digits_request_msg,
                                                parse_mode='Markdown',
                                                reply_markup=reply_markup)

        # Store the message ID to delete it later
        user_id = query.from_user.id
        if 'digits_message_id' not in context.bot_data:
            context.bot_data['digits_message_id'] = {}
        context.bot_data['digits_message_id'][
            user_id] = sent_message.message_id

        # Answer the callback query to remove loading state
        query.answer()
    except Exception as e:
        logger.error(
            f"Error sending new message in manual prediction button: {e}")

    # Set user state to waiting for 3 digits
    user_id = query.from_user.id
    if 'waiting_for_digits' not in context.bot_data:
        context.bot_data['waiting_for_digits'] = set()
    context.bot_data['waiting_for_digits'].add(user_id)


def get_current_period_number():
    """
    Get current period number using the real Tiranga algorithm
    Format: YYYYMMDD + 10001 + HHHMM (counter from 00:00)
    """
    from datetime import datetime

    # Step 1: Get current time
    now = datetime.now()

    # Step 2: Format date
    date_str = now.strftime("%Y%m%d")  # YYYYMMDD

    # Step 3: Fixed game code for 1-min game
    game_code = "10001"

    # Step 4: Calculate counter (minutes since 00:00) + 1 to match real period
    counter = now.hour * 60 + now.minute + 1
    counter_str = f"{counter:04d}"  # zero-padded to 4 digits

    # Final period number
    period_number = f"{date_str}{game_code}{counter_str}"
    return period_number


def should_generate_new_period(context):
    """
    Check if we should generate a new period (every minute)
    Based on real period number changes
    """
    from datetime import datetime

    # Get current and stored period numbers
    current_period = get_current_period_number()
    stored_period = context.bot_data.get('current_period')

    # Generate new period if period number has changed
    return stored_period != current_period


def generate_auto_prediction(context: CallbackContext):
    """
    Generate automatic prediction with all components
    Uses real period numbers that change every minute
    """
    import random
    from datetime import datetime

    # Get current period number from "server"
    current_period = get_current_period_number()

    # Check if we should generate new prediction (only when period changes)
    should_generate_new_pred = should_generate_new_period(context)

    if should_generate_new_pred:
        # Generate Big/Small
        purchase_type = random.choice(["Big", "Small"])

        # Generate Color (Green/Red 95%, Violet 5%)
        color_roll = random.randint(1, 100)
        if color_roll <= 5:
            color = "Violet"
        else:
            color = random.choice(["Green", "Red"])

        # Generate Numbers based on Big/Small
        if purchase_type == "Big":
            # Big: numbers 5,6,7,8,9
            available_numbers = [5, 6, 7, 8, 9]
        else:
            # Small: numbers 0,1,2,3,4
            available_numbers = [0, 1, 2, 3, 4]

        # Select 2 random numbers from available set
        selected_numbers = random.sample(available_numbers, 2)
        selected_numbers.sort()

        # Store prediction data with current period
        context.bot_data['auto_prediction_data'] = {
            'period': current_period,
            'purchase_type': purchase_type,
            'color': color,
            'numbers': selected_numbers,
            'generated_time': datetime.now()
        }
        context.bot_data['last_period_time'] = datetime.now()
        context.bot_data['current_period'] = current_period
    else:
        # Use existing prediction data but update period if changed
        prediction_data = context.bot_data.get('auto_prediction_data', {})

        # Check if period changed (new minute)
        stored_period = context.bot_data.get('current_period')
        if stored_period != current_period:
            # Period changed, keep same prediction but update period
            context.bot_data['current_period'] = current_period
            if prediction_data:
                context.bot_data['auto_prediction_data'][
                    'period'] = current_period

        # Get existing prediction data
        purchase_type = prediction_data.get('purchase_type', 'Big')
        color = prediction_data.get('color', 'Green')
        selected_numbers = prediction_data.get('numbers', [3, 6])

    # Always return current period, but prediction only changes when new period is generated
    final_period = context.bot_data.get('current_period', current_period)
    final_prediction = context.bot_data.get('auto_prediction_data', {})

    return (final_period, final_prediction.get('purchase_type', 'Big'),
            final_prediction.get('color', 'Green'),
            final_prediction.get('numbers', [3, 6]))


def handle_auto_prediction_button(update: Update, context: CallbackContext):
    """
    Handle the 'Auto Prediction' button callback with real period numbers
    """
    query = update.callback_query
    query.answer()

    try:
        # Initialize user's prediction tracking if not exists
        user_id = query.from_user.id
        if 'user_prediction_messages' not in context.bot_data:
            context.bot_data['user_prediction_messages'] = {}
        if user_id not in context.bot_data['user_prediction_messages']:
            context.bot_data['user_prediction_messages'][user_id] = {}

        # Send sticker first for auto prediction analysis
        try:
            analysis_sticker = query.message.reply_sticker(
                sticker=
                "CAACAgUAAxkBAAEOokJoP6kNi3LIIAtNP6bOG-oNDN71qwACYQADO0qzKcFoBwUrNwVWNgQ"
            )
        except Exception as e:
            logger.error(f"Error sending sticker: {e}")

        # Generate prediction with real period number
        period, purchase_type, color, selected_numbers = generate_auto_prediction(
            context)

        # Store displayed period for tracking
        context.bot_data['displayed_period'] = period

        # Format numbers for display
        numbers_text = f"{selected_numbers[0]} or {selected_numbers[1]}"

        auto_prediction_msg = ("*🔐 VIP Hack Auto Prediction ⏳*\n\n"
                               "*🎮 Game: Wingo 1 Minute*\n"
                               f"*⏰ Period: {period}* 🔴 LIVE\n"
                               f"*💸 Purchase: {purchase_type}*\n\n"
                               "*🔮 Risky Predictions:*\n\n"
                               f"*➟ Colour: {color}*\n"
                               f"*➟ Numbers: {numbers_text}*\n\n"
                               "*⚠️ Important: Always maintain Level 5 funds*")

        # Create keyboard with Next Prediction and Back buttons
        keyboard = [[
            InlineKeyboardButton("Next Prediction",
                                 callback_data="next_auto_prediction")
        ], [InlineKeyboardButton("🔙 Back", callback_data="prediction")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Choose image based on prediction result
        if purchase_type == "Big":
            image_url = "https://files.catbox.moe/h5bgxo.jpg"
        else:  # Small
            image_url = "https://files.catbox.moe/mstdso.jpg"

        # Send new message with auto prediction photo and store message info
        try:
            sent_message = query.message.reply_photo(
                photo=image_url,
                caption=auto_prediction_msg,
                parse_mode='Markdown',
                reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Error sending photo in auto prediction: {e}")
            # Fallback to text message if photo fails
            sent_message = query.message.reply_text(auto_prediction_msg,
                                                    parse_mode='Markdown',
                                                    reply_markup=reply_markup)

        # Store the message ID for this period
        context.bot_data['user_prediction_messages'][user_id][period] = sent_message.message_id

    except Exception as e:
        logger.error(f"Error in auto prediction: {e}")
        query.answer("❌ Error generating prediction. Please try again.")


def handle_next_auto_prediction(update: Update, context: CallbackContext):
    """
    Handle the 'Next Prediction' button for auto prediction
    Keeps only one message per period, deletes duplicates for same period
    """
    query = update.callback_query
    user_id = query.from_user.id

    try:
        # Initialize user's prediction tracking if not exists
        if 'user_prediction_messages' not in context.bot_data:
            context.bot_data['user_prediction_messages'] = {}
        if user_id not in context.bot_data['user_prediction_messages']:
            context.bot_data['user_prediction_messages'][user_id] = {}

        # Get current real period number
        current_period = get_current_period_number()
        previous_period = context.bot_data.get('displayed_period')

        # Check if period has changed
        is_new_period = previous_period != current_period

        if is_new_period:
            # Period has changed - create new prediction (keep old periods)
            
            # Generate new prediction for new period
            period, purchase_type, color, selected_numbers = generate_auto_prediction(
                context)

            # Format numbers for display
            numbers_text = f"{selected_numbers[0]} or {selected_numbers[1]}"

            auto_prediction_msg = (
                "*🔐 VIP Hack Auto Prediction ⏳*\n\n"
                "*🎮 Game: Wingo 1 Minute*\n"
                f"*⏰ Period: {period}* 🆕 NEW PERIOD\n"
                f"*💸 Purchase: {purchase_type}*\n\n"
                "*🔮 Risky Predictions:*\n\n"
                f"*➟ Colour: {color}*\n"
                f"*➟ Numbers: {numbers_text}*\n\n"
                "*⚠️ Important: Always maintain Level 5 funds*")

            # Create keyboard with Next Prediction and Back buttons
            keyboard = [[
                InlineKeyboardButton("Next Prediction",
                                     callback_data="next_auto_prediction")
            ], [InlineKeyboardButton("🔙 Back", callback_data="prediction")]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            # Choose image based on prediction result
            if purchase_type == "Big":
                image_url = "https://files.catbox.moe/h5bgxo.jpg"
            else:  # Small
                image_url = "https://files.catbox.moe/mstdso.jpg"

            # Send new message with new prediction
            try:
                sent_message = query.message.reply_photo(
                    photo=image_url,
                    caption=auto_prediction_msg,
                    parse_mode='Markdown',
                    reply_markup=reply_markup)
            except Exception as e:
                logger.error(
                    f"Error sending photo in next auto prediction: {e}")
                # Fallback to text message if photo fails
                sent_message = query.message.reply_text(
                    auto_prediction_msg,
                    parse_mode='Markdown',
                    reply_markup=reply_markup)

            # Store new period message - don't delete messages from different periods
            context.bot_data['user_prediction_messages'][user_id][period] = sent_message.message_id

            # Store current displayed period
            context.bot_data['displayed_period'] = period

            # Answer callback with new period message
            query.answer("🆕 New period detected! Fresh prediction generated.",
                         show_alert=False)

        else:
            # Same period - delete previous prediction for this period and create new one
            period = current_period
            
            # Delete previous message for this same period (if exists)
            if period in context.bot_data['user_prediction_messages'][user_id]:
                try:
                    previous_msg_id = context.bot_data['user_prediction_messages'][user_id][period]
                    context.bot.delete_message(chat_id=user_id, message_id=previous_msg_id)
                    logger.info(f"Deleted duplicate prediction message for period {period} from user {user_id}")
                except Exception as e:
                    logger.error(f"Error deleting duplicate prediction message: {e}")

            # Send sticker first for auto prediction analysis
            try:
                analysis_sticker = query.message.reply_sticker(
                    sticker=
                    "CAACAgUAAxkBAAEOokJoP6kNi3LIIAtNP6bOG-oNDN71qwACYQADO0qzKcFoBwUrNwVWNgQ"
                )
            except Exception as e:
                logger.error(f"Error sending sticker: {e}")

            # Keep existing prediction but show current period
            prediction_data = context.bot_data.get('auto_prediction_data', {})
            purchase_type = prediction_data.get('purchase_type', 'Big')
            color = prediction_data.get('color', 'Green')
            selected_numbers = prediction_data.get('numbers', [3, 6])

            # Format numbers for display
            numbers_text = f"{selected_numbers[0]} or {selected_numbers[1]}"

            auto_prediction_msg = (
                "*🔐 VIP Hack Auto Prediction ⏳*\n\n"
                "*🎮 Game: Wingo 1 Minute*\n"
                f"*⏰ Period: {period}* 🔴 LIVE\n"
                f"*💸 Purchase: {purchase_type}*\n\n"
                "*🔮 Risky Predictions:*\n\n"
                f"*➟ Colour: {color}*\n"
                f"*➟ Numbers: {numbers_text}*\n\n"
                "*⚠️ Important: Always maintain Level 5 funds*")

            # Create keyboard with Next Prediction and Back buttons
            keyboard = [[
                InlineKeyboardButton("Next Prediction",
                                     callback_data="next_auto_prediction")
            ], [InlineKeyboardButton("🔙 Back", callback_data="prediction")]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            # Choose image based on prediction result
            if purchase_type == "Big":
                image_url = "https://files.catbox.moe/h5bgxo.jpg"
            else:  # Small
                image_url = "https://files.catbox.moe/mstdso.jpg"

            # Send new message with auto prediction photo
            try:
                sent_message = query.message.reply_photo(
                    photo=image_url,
                    caption=auto_prediction_msg,
                    parse_mode='Markdown',
                    reply_markup=reply_markup)
                
                # Store new message ID for this period (replacing old one)
                context.bot_data['user_prediction_messages'][user_id][period] = sent_message.message_id
                    
            except Exception as e:
                logger.error(f"Error sending new auto prediction photo: {e}")
                # Fallback to text message if photo fails
                try:
                    sent_message = query.message.reply_text(
                        auto_prediction_msg,
                        parse_mode='Markdown',
                        reply_markup=reply_markup)
                    
                    # Store new message ID for this period (replacing old one)
                    context.bot_data['user_prediction_messages'][user_id][period] = sent_message.message_id
                        
                except Exception as e2:
                    logger.error(f"Error sending new auto prediction text: {e2}")

            # Answer callback with same result message
            query.answer("🔄 Same period - updated prediction message",
                         show_alert=False)

    except Exception as e:
        logger.error(f"Error in next auto prediction: {e}")
        query.answer("❌ Error processing request. Please try again.")


def handle_support_button(update: Update, context: CallbackContext):
    """
    Handle the 'Support' button callback
    """
    query = update.callback_query
    query.answer()

    # Support message in bold mode
    support_msg = ("*⚠️ DEPOSIT / WITHDRAWAL ISSUE ⁉️*\n\n"
                   "*💬 Contact our Official Support Bot:*\n"
                   "*⏰ Support available 24/7*\n"
                   "*⚙️ Only use the official bot for help!*\n\n"
                   "*🚀 Get back in the game without delay*")

    # Create buttons with Contact and Back
    keyboard = [[
        InlineKeyboardButton("Contact", url="https://t.me/streamerflex_bot")
    ], [InlineKeyboardButton("🔙 Back", callback_data="back")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Edit existing message with new photo and content
    try:
        query.edit_message_media(media=InputMediaPhoto(
            media="https://files.catbox.moe/vata3j.webp",
            caption=support_msg,
            parse_mode='Markdown'),
                                 reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Error editing message in support button: {e}")
        # Fallback to editing just caption if photo edit fails
        try:
            query.edit_message_caption(caption=support_msg,
                                       parse_mode='Markdown',
                                       reply_markup=reply_markup)
        except Exception as e2:
            logger.error(f"Error editing caption in support button: {e2}")


def prediction_menu_handler(update: Update, context: CallbackContext):
    """
    Handle the prediction menu showing Wingo, Aviator, Mines Pro and Dragon Tiger options
    """
    query = update.callback_query
    query.answer()

    # Prediction menu message
    prediction_menu_msg = ("*🎮 Select Your Game*\n\n"
                           "*Choose which game you want predictions for:*\n\n"
                           "*🎯 Wingo - Color & Number Predictions*\n"
                           "*✈️ Aviator - Multiplier Predictions*\n"
                           "*💎 Mines Pro - Coming Soon*\n"
                           "*🐉 Dragon Tiger - Coming Soon*")

    # Create keyboard with all four buttons
    keyboard = [[
        InlineKeyboardButton("🎯 Wingo", callback_data="wingo_menu"),
        InlineKeyboardButton("✈️ Aviator", callback_data="aviator_menu")
    ],
                [
                    InlineKeyboardButton("💎 Mines Pro",
                                         callback_data="mines_menu"),
                    InlineKeyboardButton("🐉 Dragon Tiger",
                                         callback_data="dragon_tiger_menu")
                ], [InlineKeyboardButton("🔙 Back", callback_data="back")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Edit existing message with game selection image and content
    try:
        query.edit_message_media(media=InputMediaPhoto(
            media="https://files.catbox.moe/xevf55.webp",
            caption=prediction_menu_msg,
            parse_mode='Markdown'),
                                 reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Error editing message in prediction menu: {e}")
        # Fallback to editing just caption if photo edit fails
        try:
            query.edit_message_caption(caption=prediction_menu_msg,
                                       parse_mode='Markdown',
                                       reply_markup=reply_markup)
        except Exception as e2:
            logger.error(f"Error sending prediction menu message: {e2}")


def wingo_menu_handler(update: Update, context: CallbackContext):
    """
    Handle the wingo menu showing Manual and Auto Prediction options
    """
    query = update.callback_query
    query.answer()

    # Wingo prediction menu message
    wingo_menu_msg = ("*🥷 VIP AI Predictions*\n\n"
                      "*⚡️ Unlock Exclusive Predictions Powered by AI*\n"
                      "*🚀 High Accuracy & Smart Analysis*\n"
                      "*💰 Maximize Your Winnings Like Never Before*\n\n"
                      "*⚠️ Make Sure to Maintain Level '5'*")

    # Create keyboard with Manual and Auto Prediction buttons
    keyboard = [[
        InlineKeyboardButton("Manual Prediction",
                             callback_data="manual_prediction"),
        InlineKeyboardButton("Auto Prediction",
                             callback_data="auto_prediction")
    ], [InlineKeyboardButton("🔙 Back", callback_data="prediction_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Edit existing message with wingo image and content
    try:
        query.edit_message_media(media=InputMediaPhoto(
            media="https://files.catbox.moe/fo19ii.jpg",
            caption=wingo_menu_msg,
            parse_mode='Markdown'),
                                 reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Error editing message in wingo menu: {e}")
        # Fallback to editing just caption if photo edit fails
        try:
            query.edit_message_caption(caption=wingo_menu_msg,
                                       parse_mode='Markdown',
                                       reply_markup=reply_markup)
        except Exception as e2:
            logger.error(f"Error sending wingo menu message: {e2}")


def aviator_menu_handler(update: Update, context: CallbackContext):
    """
    Handle the aviator menu showing Aviator prediction options
    """
    query = update.callback_query
    query.answer()

    # Aviator prediction menu message
    aviator_menu_msg = ("*🚀 Aviator VIP Predictions*\n\n"
                        "*⚡️ AI-Powered Multiplier Predictions*\n"
                        "*🎳 Advanced Pattern Analysis*\n"
                        "*💎 Premium Aviator Strategies*\n\n"
                        "*⚠️ Recommended Bet Amount: Level 5*")

    # Create keyboard with only Get Signals button for Aviator
    keyboard = [[
        InlineKeyboardButton("🚀 Get Signals", callback_data="aviator_signals")
    ], [InlineKeyboardButton("🔙 Back", callback_data="prediction_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Edit existing message with aviator image and content
    try:
        query.edit_message_media(media=InputMediaPhoto(
            media="https://files.catbox.moe/etovfv.webp",
            caption=aviator_menu_msg,
            parse_mode='Markdown'),
                                 reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Error editing message in aviator menu: {e}")
        # Fallback to editing just caption if photo edit fails
        try:
            query.edit_message_caption(caption=aviator_menu_msg,
                                       parse_mode='Markdown',
                                       reply_markup=reply_markup)
        except Exception as e2:
            logger.error(f"Error sending aviator menu message: {e2}")


def mines_menu_handler(update: Update, context: CallbackContext):
    """
    Handle the mines menu showing coming soon message
    """
    query = update.callback_query
    query.answer()

    # Mines coming soon message
    mines_menu_msg = (
        "*💎 Mines Pro*\n\n"
        "*🚧 Coming Soon! 🚧*\n\n"
        "*We're working hard to bring you the best Mines predictions!*\n"
        "*Stay tuned for amazing features and high-accuracy predictions.*")

    # Create keyboard with back button
    keyboard = [[
        InlineKeyboardButton("🔙 Back", callback_data="prediction_menu")
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Edit existing message with mines image and content
    try:
        query.edit_message_media(media=InputMediaPhoto(
            media="https://files.catbox.moe/jpxz04.jpg",
            caption=mines_menu_msg,
            parse_mode='Markdown'),
                                 reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Error editing message in mines menu: {e}")
        # Fallback to editing just caption if photo edit fails
        try:
            query.edit_message_caption(caption=mines_menu_msg,
                                       parse_mode='Markdown',
                                       reply_markup=reply_markup)
        except Exception as e2:
            logger.error(f"Error sending mines menu message: {e2}")


def dragon_tiger_menu_handler(update: Update, context: CallbackContext):
    """
    Handle the dragon tiger menu showing coming soon message
    """
    query = update.callback_query
    query.answer()

    # Dragon Tiger coming soon message
    dragon_tiger_menu_msg = (
        "*🐲 Dragon Tiger*\n\n"
        "*🚧 Coming Soon! 🚧*\n\n"
        "*Get ready for the ultimate Dragon Tiger predictions!*\n"
        "*Advanced AI algorithms are being fine-tuned for maximum wins.*")

    # Create keyboard with back button
    keyboard = [[
        InlineKeyboardButton("🔙 Back", callback_data="prediction_menu")
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Edit existing message with dragon tiger image and content
    try:
        query.edit_message_media(media=InputMediaPhoto(
            media="https://files.catbox.moe/djdubx.webp",
            caption=dragon_tiger_menu_msg,
            parse_mode='Markdown'),
                                 reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Error editing message in dragon tiger menu: {e}")
        # Fallback to editing just caption if photo edit fails
        try:
            query.edit_message_caption(caption=dragon_tiger_menu_msg,
                                       parse_mode='Markdown',
                                       reply_markup=reply_markup)
        except Exception as e2:
            logger.error(f"Error sending dragon tiger menu message: {e2}")


def handle_aviator_signals_button(update: Update, context: CallbackContext):
    """
    Handle the aviator signals button - show instructions for round ID input
    """
    query = update.callback_query
    query.answer()

    user_id = query.from_user.id

    # Track user activity
    update_user_stats(user_id, 'aviator_signals_used')

    # Check if user is blocked
    try:
        user_doc = user_stats_col.find_one({'user_id': user_id})
        if user_doc and user_doc.get('is_blocked', False):
            query.edit_message_text("🚫 You have been blocked from using this bot.")
            return
    except Exception as e:
        logger.error(f"Error checking blocked status in aviator signals: {e}")

    # Show instruction message for round ID input
    instruction_msg = (
        "*🚀 Drop The Last 3 Digits Of The Round ID*\n"
        "*🎯 Claim Your VIP Aviator Tip – Instantly!*\n\n"
        "*⚙️ Example: 6456123 ➡️ Just Send 123*"
    )

    # Create keyboard with back button only
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="aviator_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Set user state to wait for round ID input
    if 'aviator_waiting_round_id' not in context.bot_data:
        context.bot_data['aviator_waiting_round_id'] = set()
    context.bot_data['aviator_waiting_round_id'].add(user_id)

    # Send instruction message and store its ID for later deletion
    try:
        instruction_message = query.message.reply_text(instruction_msg,
                                                      parse_mode='Markdown',
                                                      reply_markup=reply_markup)
        
        # Store instruction message ID for deletion when prediction arrives
        if 'aviator_instruction_messages' not in context.bot_data:
            context.bot_data['aviator_instruction_messages'] = {}
        context.bot_data['aviator_instruction_messages'][user_id] = instruction_message.message_id
        
    except Exception as e:
        logger.error(f"Error sending aviator signals instruction message: {e}")
        query.answer("❌ Error showing instructions. Please try again.", show_alert=True)


def generate_aviator_prediction(round_id):
    """
    Generate aviator prediction based on round ID with range 1.0x to 3.0x
    """
    import random
    
    # Generate multipliers from 1.0x to 3.0x with 0.2x increments
    # 1.0x, 1.2x, 1.4x, 1.6x, 1.8x, 2.0x, 2.2x, 2.4x, 2.6x, 2.8x, 3.0x
    multipliers = []
    for i in range(11):  # 0 to 10
        multiplier = 1.0 + (i * 0.2)
        multipliers.append(f"{multiplier:.1f}x")
    
    # Weighted probability distribution for more realistic aviator game
    rand = random.random()
    
    if rand < 0.35:  # 35% - Lower multipliers (1.0x-1.8x)
        low_multipliers = ["1.0x", "1.2x", "1.4x", "1.6x", "1.8x"]
        return random.choice(low_multipliers)
    elif rand < 0.70:  # 35% - Medium multipliers (2.0x-2.6x)
        medium_multipliers = ["2.0x", "2.2x", "2.4x", "2.6x"]
        return random.choice(medium_multipliers)
    else:  # 30% - Higher multipliers (2.8x-3.0x)
        high_multipliers = ["2.8x", "3.0x"]
        return random.choice(high_multipliers)


def handle_aviator_round_id_input(update: Update, context: CallbackContext, round_id):
    """
    Handle user's round ID input and generate prediction
    """
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


def handle_screenshot_button(update: Update, context: CallbackContext):
    """
    Handle the 'Send Screenshot' button callback
    """
    query = update.callback_query
    query.answer()

    # Send message asking for UID
    query.edit_message_caption(caption=(
        "*Welcome To Tashan Win Prediction Bot !! 🧞‍♂*\n\n"
        "*× To Access Premium Prediction ⚡+ Gift Code 🎁 + High Deposit Bonus 💰*\n\n"
        "*1. Register With Official Link 🔗\n"
        "2. Deposit ₹100 Atleast 📥\n"
        "3. Send UID & Screenshot 📃\n"
        "4. Wait For Admin Approval ⏰*\n\n"
        "*Note : Access will expire in 7 Days 🗓️*\n\n"
        "*📝 Please send your UID for verification (6-12 digits):*"),
                               parse_mode='Markdown')


def stats(update: Update, context: CallbackContext):
    """
    Show comprehensive user activity report (Admin only)
    """
    if update.message.from_user.id != ADMIN_UID:
        update.message.reply_text("❌ Unauthorized access.")
        return

    try:
        stats_data = get_user_activity_stats()

        # Get detailed blocked user statistics
        admin_blocked = user_stats_col.count_documents({
            'is_blocked':
            True,
            '$or': [{
                'blocked_by_user': {
                    '$exists': False
                }
            }, {
                'blocked_by_user': False
            }]
        })
        user_blocked = user_stats_col.count_documents({
            'is_blocked': True,
            'blocked_by_user': True
        })

        msg = (
            f"📊 *USER ACTIVITY REPORT*\n\n"
            f"🤖 Total Bot Users: {stats_data['total_users']}\n"
            f"🚫 Blocked Users: {stats_data['blocked_users']}\n"
            f"   ├─ 👤 User Blocked Bot: {user_blocked}\n"
            f"   └─ 🛡️ Admin Blocked: {admin_blocked}\n"
            f"✅ Verified UIDs: {stats_data['verified_uids']}\n"
            f"🔒 Fully Verified Users: {stats_data['fully_verified_users']}\n"
            f"⚠️ Non-Verified Users: {stats_data['non_verified_users']}\n"
            f"🛠 UIDs Updated by Admin: {stats_data['admin_updated_uids']}\n"
            f"⏳ Pending Wallet Verifications: {stats_data['pending_wallet_verifications']}\n"
            f"💰 Users with Valid Balance: {stats_data['users_with_valid_balance']}\n\n"
            f"📈 Verification Rate: {(stats_data['verified_uids']/stats_data['non_verified_users']*100) if stats_data['non_verified_users'] > 0 else 0:.1f}%"
        )

        # Create inline keyboard with delete button
        keyboard = [[
            InlineKeyboardButton("🗑", callback_data="confirm_delete_all_data")
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        update.message.reply_text(msg,
                                  parse_mode='Markdown',
                                  reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Error in stats command: {e}")
        update.message.reply_text("❌ Error retrieving statistics.")


def check_newly_verified_uids_silent(update: Update, context: CallbackContext):
    """
    Silently check for UIDs that became verified after admin updates and notify users
    """
    try:
        # Find UIDs that are verified but users haven't been notified yet
        newly_verified = list(
            uids_col.find({
                'verified': True,
                'fully_verified': False,
                'user_id': {
                    '$exists': True,
                    '$ne': None
                },
                'notified_for_wallet': {
                    '$ne': True
                }
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
                    f"*⚡Great News, Champ! 🧞‍♂️*\n\n"
                    f"*✅ UID {uid} Verified Successfully*\n"
                    f"*📩 Now, Please Send Your Wallet Screenshot For Balance Check.*\n"
                    f"*💰 Minimum Required Balance: ₹100*")

                sent = safe_send_message(context=context,
                                         chat_id=user_id,
                                         text=message,
                                         parse_mode='Markdown')

                if sent is None:
                    logger.warning(
                        f"Could not notify user {user_id} - they have blocked the bot"
                    )
                    continue

                # Mark as notified and set up for wallet verification
                uids_col.update_one({'_id': doc['_id']},
                                    {'$set': {
                                        'notified_for_wallet': True
                                    }})

                # Add to pending wallets
                if 'pending_wallets' not in context.bot_data:
                    context.bot_data['pending_wallets'] = {}
                context.bot_data['pending_wallets'][user_id] = uid

                notified_count += 1

            except Exception as e:
                logger.error(
                    f"Error notifying user {doc.get('user_id', 'Unknown')}: {e}"
                )

        if notified_count > 0:
            logger.info(
                f"Automatically notified {notified_count} users about newly verified UIDs"
            )

    except Exception as e:
        logger.error(f"Error checking newly verified UIDs: {e}")


def check_newly_verified_uids(update: Update, context: CallbackContext):
    """
    Check for UIDs that became verified after admin updates and notify users
    """
    try:
        # Find UIDs that are verified but users haven't been notified yet
        newly_verified = list(
            uids_col.find({
                'verified': True,
                'fully_verified': False,
                'user_id': {
                    '$exists': True,
                    '$ne': None
                },
                'notified_for_wallet': {
                    '$ne': True
                }
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
                    f"*⚡Great News, Champ! 🧞‍♂️*\n\n"
                    f"*✅ UID {uid} Verified Successfully*\n"
                    f"*📩 Now, Please Send Your Wallet Screenshot For Balance Check.*\n"
                    f"*💰 Minimum Required Balance: ₹100*")

                sent = safe_send_message(context=context,
                                         chat_id=user_id,
                                         text=message,
                                         parse_mode='Markdown')

                if sent is None:
                    logger.warning(
                        f"Could not notify user {user_id} - they have blocked the bot"
                    )
                    continue

                # Mark as notified and set up for wallet verification
                uids_col.update_one({'_id': doc['_id']},
                                    {'$set': {
                                        'notified_for_wallet': True
                                    }})

                # Add to pending wallets
                if 'pending_wallets' not in context.bot_data:
                    context.bot_data['pending_wallets'] = {}
                context.bot_data['pending_wallets'][user_id] = uid

                notified_count += 1

            except Exception as e:
                logger.error(
                    f"Error notifying user {doc.get('user_id', 'Unknown')}: {e}"
                )

        update.message.reply_text(
            f"📢 *Notification Summary*\n\n"
            f"✅ Notified {notified_count} users about verified UIDs\n"
            f"📸 They have been asked to send wallet screenshots",
            parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Error checking newly verified UIDs: {e}")
        update.message.reply_text("❌ Error checking for newly verified UIDs.")


def check_uid(update, context, uid, user_id, username):
    """
    Check if UID exists in database and update user info with restriction mode logic
    """
    global restrict_mode
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

            if restrict_mode:
                # Restriction mode is ON
                if found:
                    # UID exists in database
                    verified_by_tg_id = found.get('verified_by_tg_id')
                    is_verified = found.get('verified', False)

                    if verified_by_tg_id == user_id:
                        # Same Telegram user trying to verify same UID again - allow multiple times
                        if is_verified:
                            # UID is already verified by this user - allow re-verification
                            uids_col.update_one({'uid': uid}, {
                                '$set': {
                                    'user_id': user_id,
                                    'username': username,
                                    'last_checked': update.message.date
                                }
                            })
                            update.message.reply_text(
                                f"*✅ UID {uid} Verified*\n"
                                f"*📸 Please Send Your Wallet Screenshot For Balance Verification.*\n"
                                f"*💰 Minimum Required Balance: ₹100*",
                                parse_mode='Markdown')

                            # Store pending wallet verification
                            if 'pending_wallets' not in context.bot_data:
                                context.bot_data['pending_wallets'] = {}
                            context.bot_data['pending_wallets'][user_id] = uid
                            return
                        else:
                            # UID submitted by same user but still pending approval
                            approval_message = (
                                "*⏳ UID Still Under Review*\n\n"
                                "*🔴 Your UID is already submitted and waiting for admin approval.*\n"
                                "*⏰ Please wait for verification. No need to submit again.*"
                            )
                            update.message.reply_text(approval_message, parse_mode='Markdown')
                            return
                    elif verified_by_tg_id and verified_by_tg_id != user_id and is_verified:
                        # Different user trying to verify UID that's already verified by another user
                        restriction_msg = (
                            f"*🔒 UID Already Verified by Another Account*\n"
                            f"*🆔 UID: {uid}*\n"
                            f"*⚠️ This UID has been claimed by a different Telegram account.*\n"
                            f"*🔁 Each UID can only be verified once per user.*\n\n"
                            f"*➠ Please switch back to your original account or contact the admin for help.*"
                        )

                        # Create inline keyboard with Contact Admin button
                        keyboard = [[
                            InlineKeyboardButton(
                                "Contact Admin 👤",
                                url="https://t.me/streamerflex_bot")
                        ]]
                        reply_markup = InlineKeyboardMarkup(keyboard)

                        update.message.reply_text(restriction_msg,
                                                  parse_mode='Markdown',
                                                  reply_markup=reply_markup)
                        return
                    else:
                        # UID exists but no verified_by_tg_id field or not verified yet - update it
                        uids_col.update_one({'uid': uid}, {
                            '$set': {
                                'user_id': user_id,
                                'username': username,
                                'verified': True,
                                'verified_by': user_id,
                                'verified_by_tg_id': user_id,  # Save Telegram ID
                                'last_checked': update.message.date
                            }
                        })
                        update.message.reply_text(
                            f"*✅ UID {uid} Verified*\n"
                            f"*📸 Please Send Your Wallet Screenshot For Balance Verification.*\n"
                            f"*💰 Minimum Required Balance: ₹100*",
                            parse_mode='Markdown')

                        # Store pending wallet verification
                        if 'pending_wallets' not in context.bot_data:
                            context.bot_data['pending_wallets'] = {}
                        context.bot_data['pending_wallets'][user_id] = uid
                        return
                else:
                    # UID not found in database in restriction mode
                    # Check if user already submitted this UID before
                    existing_submission = uids_col.find_one({
                        'uid': uid,
                        'verified_by_tg_id': user_id
                    })

                    if existing_submission:
                        # User already submitted this UID before
                        if existing_submission.get('verified', False):
                            # Admin has already verified this UID for this user
                            update.message.reply_text(
                                f"*✅ UID {uid} Verified*\n"
                                f"*📸 Please Send Your Wallet Screenshot For Balance Verification.*\n"
                                f"*💰 Minimum Required Balance: ₹100*",
                                parse_mode='Markdown')

                            # Store pending wallet verification
                            if 'pending_wallets' not in context.bot_data:
                                context.bot_data['pending_wallets'] = {}
                            context.bot_data['pending_wallets'][user_id] = uid
                            return
                        else:
                            # Still pending approval
                            approval_message = (
                                "*⏳ UID Still Under Review*\n\n"
                                "*🔴 Your UID is already submitted and waiting for admin approval.*\n"
                                "*⏰ Please wait for verification. No need to submit again.*"
                            )
                            update.message.reply_text(approval_message,
                                                      parse_mode='Markdown')
                            return
                    else:
                        # First time submission - insert with verified_by_tg_id
                        uids_col.insert_one({
                            'uid': uid,
                            'user_id': user_id,
                            'username': username,
                            'verified': False,
                            'fully_verified': False,
                            'verified_by': user_id,
                            'verified_by_tg_id': user_id,  # Save Telegram ID
                            'added_date': update.message.date
                        })
                        approval_message = (
                            "*☑️ Your UID Successfully Sent For Approval !*\n\n"
                            "*🔴 You Will Get Access Within Few Minutes If You Enter Correct Details*"
                        )
                        update.message.reply_text(approval_message,
                                                  parse_mode='Markdown')

                        # Notify admin
                        try:
                            update.message.bot.send_message(
                                chat_id=ADMIN_UID,
                                text=
                                f"⚠️ New UID verification attempt (RESTRICT MODE):\n"
                                f"UID: {uid}\n"
                                f"User: @{username} (ID: {user_id})\n"
                                f"Status: NOT FOUND\n"
                                f"🔒 Verified by TG ID: {user_id}")
                        except Exception as e:
                            logger.error(f"Error notifying admin: {e}")
                        return
            else:
                # Restriction mode is OFF - original logic with Telegram ID tracking
                if found:
                    # UID found in database
                    uids_col.update_one(
                        {'uid': uid},
                        {
                            '$set': {
                                'user_id': user_id,
                                'username': username,
                                'verified': True,
                                'verified_by': user_id,
                                'verified_by_tg_id': user_id,  # Save Telegram ID
                                'last_checked': update.message.date
                            }
                        },
                        upsert=True)
                    update.message.reply_text(
                        f"*✅ UID {uid} Verified*\n"
                        f"*📸 Please Send Your Wallet Screenshot For Balance Verification.*\n"
                        f"*💰 Minimum Required Balance: ₹100*",
                        parse_mode='Markdown')

                    # Store pending wallet verification
                    if 'pending_wallets' not in context.bot_data:
                        context.bot_data['pending_wallets'] = {}
                    context.bot_data['pending_wallets'][user_id] = uid
                    return

                else:
                    # UID not found
                    uids_col.update_one(
                        {'uid': uid},
                        {
                            '$set': {
                                'user_id': user_id,
                                'username': username,
                                'verified': False,
                                'fully_verified': False,
                                'verified_by': user_id,
                                'verified_by_tg_id': user_id,  # Save Telegram ID
                                'added_date': update.message.date
                            }
                        },
                        upsert=True)
                    approval_message = (
                        "*☑️ Your UID Successfully Sent For Approval !*\n\n"
                        "*🔴 You Will Get Access Within Few Minutes If You Enter Correct Details*"
                    )
                    update.message.reply_text(approval_message,
                                              parse_mode='Markdown')

                    # Notify admin
                    try:
                        update.message.bot.send_message(
                            chat_id=ADMIN_UID,
                            text=f"⚠️ New UID verification attempt:\n"
                            f"UID: {uid}\n"
                            f"User: @{username} (ID: {user_id})\n"
                            f"Status: NOT FOUND\n"
                            f"🔒 Verified by TG ID: {user_id}")
                    except Exception as e:
                        logger.error(f"Error notifying admin: {e}")
                    return

        except Exception as e:
            logger.error(
                f"Error in check_uid (attempt {retry_count + 1}): {e}")
            retry_count += 1
            if retry_count < max_retries:
                import time
                time.sleep(1)  # Wait 1 second before retry

    # If we get here, all retries failed
    update.message.reply_text(
        "❌ Database temporarily unavailable. Please try again in a few minutes.\n"
        f"If the problem persists, contact admin.")


def handle_wallet(update: Update, context: CallbackContext):
    """
    Process wallet screenshot for balance verification with fake detection
    """
    user_id = update.message.from_user.id

    # Check if user has pending wallet verification
    if ('pending_wallets' not in context.bot_data
            or user_id not in context.bot_data['pending_wallets']):
        update.message.reply_text(
            "❌ No pending UID verification. Please send your UID first.")
        return

    uid = context.bot_data['pending_wallets'][user_id]

    try:
        # Get the highest resolution photo
        photo = update.message.photo[-1]
        img_file = photo.get_file()
        img_bytes = img_file.download_as_bytearray()

        # Step 1: Send sticker for analysis
        analysis_sticker = update.message.reply_sticker(
            sticker=
            "CAACAgIAAxkBAAEOoRVoPrSHoQhhqqrZb_-cEVCEudhKWgACVgADDbbSGdwzoZ8qLZ2yNgQ"
        )

        # Detect digital editing/manipulation
        is_unedited, confidence_score, editing_evidence, full_analysis = detect_fake_screenshot(
            img_bytes)

        # Schedule sticker deletion after 2 minutes
        import threading

        def delete_sticker_after_delay():
            try:
                import time
                time.sleep(120)  # Wait 2 minutes (120 seconds)
                context.bot.delete_message(
                    chat_id=user_id, message_id=analysis_sticker.message_id)
                logger.info(
                    f"Analysis sticker deleted after 2 minutes for user {user_id}"
                )
            except Exception as e:
                logger.error(f"Error deleting sticker after delay: {e}")

        # Start the deletion timer in a separate thread
        deletion_thread = threading.Thread(target=delete_sticker_after_delay)
        deletion_thread.daemon = True  # Thread will exit when main program exits
        deletion_thread.start()

        # If screenshot has been digitally edited (only reject if clearly edited)
        if not is_unedited and confidence_score >= 60:
            # Log the editing detection
            logger.warning(
                f"EDITED SCREENSHOT DETECTED - User {user_id}, UID {uid}, Confidence: {confidence_score}%"
            )

            # Notify admin with detailed analysis
            try:
                admin_msg = (
                    f"🚨 EDITED SCREENSHOT ALERT 🚨\n\n"
                    f"👤 User: @{update.message.from_user.username} (ID: {user_id})\n"
                    f"🆔 UID: {uid}\n"
                    f"🔍 Status: {'DIGITALLY EDITED' if not is_unedited else 'SUSPICIOUS EDITING'}\n"
                    f"📊 Confidence: {confidence_score}%\n"
                    f"⚠️ Evidence: {', '.join(editing_evidence)}\n\n"
                    f"🤖 AI Analysis:\n{full_analysis[:500]}...")
                context.bot.send_message(chat_id=ADMIN_UID, text=admin_msg)
            except Exception as e:
                logger.error(
                    f"Error notifying admin about edited screenshot: {e}")

            # Reject user with specific editing detection message
            rejection_msg = (
                f"🚨 *SECURITY ALERT - EDITED SCREENSHOT DETECTED* 🚨\n\n"
                f"❌ *Your wallet screenshot has been digitally edited or manipulated*\n\n"
                f"🔍 *Our AI detected the following editing signs:*\n"
                f"• Digital editing confidence: {confidence_score}%\n"
                f"• Photo editing software traces found\n"
                f"• Text manipulation detected\n\n"
                f"⚠️ *IMPORTANT:*\n"
                f"• Only submit ORIGINAL, unmodified screenshots\n"
                f"• Do not use ANY photo editing software\n"
                f"• Take fresh screenshots directly from your app\n"
                f"• Do not crop, edit, or modify the image in any way\n\n"
                f"🚫 *Access denied - Screenshot editing detected*\n"
                f"🔒 *Submit only unedited original screenshots*")

            # Create inline keyboard with Contact Admin button
            keyboard = [[
                InlineKeyboardButton("Contact Admin 👤",
                                     url="https://t.me/streamerflex_bot")
            ]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            update.message.reply_text(rejection_msg,
                                      parse_mode='Markdown',
                                      reply_markup=reply_markup)

            # Mark user with editing detection flag
            uids_col.update_one({'uid': uid}, {
                '$set': {
                    'edited_screenshot_detected': True,
                    'editing_detection_date': update.message.date,
                    'ai_confidence_score': confidence_score,
                    'editing_evidence': editing_evidence,
                    'security_flag': True
                }
            })

            # Remove from pending wallets
            del context.bot_data['pending_wallets'][user_id]
            return

        # Step 2: If unedited, proceed with OCR processing
        extracted_text = gemini_ocr(img_bytes)

        if not extracted_text:
            update.message.reply_text(
                "❌ Could not process image. Please try again with a clearer screenshot."
            )
            return

        # Extract balance and UID from OCR text
        balance = None
        matched_uid = None

        # Look for balance (₹ or Rs followed by digits, or standalone numbers after balance keywords)
        balance_patterns = [
            r'(?:₹|Rs\.?|INR)\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)',
            r'(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)\s*(?:₹|Rs\.?|INR)',
            r'Balance[:\s]*(?:₹|Rs\.?|INR)?\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)',
            r'Total\s+balance[:\s]*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)',
            r'(?:Balance|Total|Amount)[:\s]*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)',
            r'(\d{1,3}(?:,\d{3})*\.\d{2})',  # Any number with decimal places (like 6,077.40)
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
            # Successful verification with editing detection confirmation
            uids_col.update_one({'uid': uid}, {
                '$set': {
                    'fully_verified': True,
                    'wallet_balance': balance,
                    'verification_date': update.message.date,
                    'screenshot_unedited': True,
                    'ai_editing_check_score': confidence_score,
                    'security_verified': True
                }
            })
            # Create inline keyboard with 4 buttons
            keyboard = [[
                InlineKeyboardButton("Prediction", callback_data="prediction"),
                InlineKeyboardButton("Gift Codes", callback_data="gift_codes")
            ],
                        [
                            InlineKeyboardButton("Bonus",
                                                 callback_data="bonus"),
                            InlineKeyboardButton("Support",
                                                 callback_data="support")
                        ]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            # Send photo with verification message and buttons
            try:
                update.message.reply_photo(
                    photo="https://files.catbox.moe/4hd1vl.png",
                    caption=
                    (f"*✅ Verification Successful! 🎯*\n\n"
                     f"*You're now eligible for VIP AI Predictions ⚡️& Daily Gift Codes worth up to ₹500 🎁*\n\n"
                     f"*📋 UID: {uid}*\n"
                     f"*💰 Balance: ₹{balance:.2f}*\n"
                     f"*🏆 Status: Fully Verified*\n\n"
                     f"*👤Approved by Admin!*\n"
                     f"*⚠️ Note: Your access is valid for 7 days 📆*"),
                    parse_mode='Markdown',
                    reply_markup=reply_markup)
            except Exception as e:
                logger.error(
                    f"Error sending photo in verification success: {e}")
                # Fallback to text message if photo fails
                update.message.reply_text(
                    f"*✅ Verification Successful! 🎯*\n\n"
                    f"*You're now eligible for VIP AI Predictions ⚡️& Daily Gift Codes worth up to ₹500 🎁*\n\n"
                    f"*📋 UID: {uid}*\n"
                    f"*💰 Balance: ₹{balance:.2f}*\n"
                    f"*🏆 Status: Fully Verified*\n\n"
                    f"*👤Approved by Admin!*\n"
                    f"*⚠️ Note: Your access is valid for 7 days 📆*",
                    parse_mode='Markdown',
                    reply_markup=reply_markup)

            # Notify admin of successful verification
            try:
                context.bot.send_message(
                    chat_id=ADMIN_UID,
                    text=f"✅ Successful verification:\n"
                    f"UID: {uid}\n"
                    f"User: @{update.message.from_user.username}\n"
                    f"Balance: ₹{balance:.2f}\n"
                    f"🔒 Screenshot: UNEDITED ({confidence_score}% confidence)\n"
                    f"🛡️ Security: VERIFIED")
            except Exception as e:
                logger.error(f"Error notifying admin: {e}")

        else:
            # Verification failed
            failure_reasons = []
            if matched_uid != uid:
                failure_reasons.append(
                    f"UID mismatch (found: {matched_uid}, expected: {uid})")
            if not balance:
                failure_reasons.append("Could not detect balance")
            elif balance < 100.0:
                failure_reasons.append(
                    f"Insufficient balance (₹{balance:.2f} < ₹100.00)")

            # Format the failure message based on the reason
            if not balance:
                failure_msg = (
                    f"*📛 Access Denied*\n"
                    f"*🚫 Reason: Could not detect balance from screenshot*\n"
                    f"*📄 Please send a clearer wallet screenshot.*\n"
                    f"*🔔 Admin has been notified.*")
            elif balance < 100.0:
                failure_msg = (
                    f"*📛 Access Denied*\n"
                    f"*🚫 Reason: Insufficient Balance (₹{balance:.2f} < ₹100.00)*\n"
                    f"*📄 Please recharge your account to continue.*\n"
                    f"*🔔 Admin has been notified.*")
            elif matched_uid != uid:
                failure_msg = (
                    f"*📛 Access Denied*\n"
                    f"*🚫 Reason: UID mismatch (found: {matched_uid}, expected: {uid})*\n"
                    f"*📄 Please send screenshot with correct UID.*\n"
                    f"*🔔 Admin has been notified.*")
            else:
                failure_msg = (
                    f"*📛 Access Denied*\n"
                    f"*🚫 Reason: {', '.join(failure_reasons)}*\n"
                    f"*📄 Please check your details and try again.*\n"
                    f"*🔔 Admin has been notified.*")

            update.message.reply_text(failure_msg, parse_mode='Markdown')

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
                    f"🔒 Screenshot: UNEDITED ({confidence_score}% confidence)\n"
                    f"OCR Text: {extracted_text[:200]}...")
            except Exception as e:
                logger.error(f"Error notifying admin: {e}")

        # Remove from pending wallets
        del context.bot_data['pending_wallets'][user_id]

    except Exception as e:
        logger.error(f"Error in handle_wallet: {e}")
        update.message.reply_text(
            "❌ Error processing wallet screenshot. Please try again.")


# ADMIN UPDATE COMMANDS


def update_cmd(update: Update, context: CallbackContext):
    """
    Start dual mode update conversation (Admin only)
    """
    logger.info(f"Update command called by user {update.message.from_user.id}")

    if update.message.from_user.id != ADMIN_UID:
        logger.warning(
            f"Unauthorized update access by user {update.message.from_user.id}"
        )
        update.message.reply_text("❌ Unauthorized access.")
        return ConversationHandler.END

    try:
        buttons = [[KeyboardButton("Single UID")],
                   [KeyboardButton("Bulk Screenshot")],
                   [KeyboardButton("Cancel")]]
        reply_markup = ReplyKeyboardMarkup(buttons,
                                           one_time_keyboard=True,
                                           resize_keyboard=True)

        update.message.reply_text(
            "🔧 *Admin Update Mode*\n\n"
            "Choose update method:\n"
            "• Single UID: Add one UID at a time\n"
            "• Bulk Screenshot: Extract UIDs from images\n"
            "• Cancel: Exit update mode",
            reply_markup=reply_markup,
            parse_mode='Markdown')
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
            parse_mode='Markdown')
        logger.info("Switched to SINGLE_UID mode")
        return SINGLE_UID
    elif update.message.text == "Bulk Screenshot":
        update.message.reply_text(
            "📸 *Bulk Screenshot Mode*\n\n"
            "Send screenshot(s) containing UIDs.\n"
            "Type /done when finished.",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode='Markdown')
        logger.info("Switched to BULK_IMG mode")
        return BULK_IMG
    elif update.message.text == "Cancel":
        update.message.reply_text("❌ Update mode cancelled.",
                                  reply_markup=ReplyKeyboardRemove())
        logger.info("Update mode cancelled by user")
        return ConversationHandler.END
    else:
        logger.warning(f"Invalid mode selection: {update.message.text}")
        update.message.reply_text(
            "❌ Invalid option. Please select from the buttons provided.",
            reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END


def handle_single_uid(update: Update, context: CallbackContext):
    """
    Handle single UID update
    """
    # Check if user wants to finish
    if update.message.text and update.message.text.strip().lower() in [
            '/done', 'done'
    ]:
        logger.info(
            f"Single UID mode completed by user {update.message.from_user.id}")
        update.message.reply_text("✅ Single UID update completed.",
                                  reply_markup=ReplyKeyboardRemove())
        # Check for newly verified UIDs
        check_newly_verified_uids(update, context)
        return ConversationHandler.END

    uid = update.message.text.strip()

    # Validate UID format
    if not re.match(r'^\d{6,12}$', uid):
        update.message.reply_text(
            "❌ Invalid UID format. Must be 6-12 digits.\n"
            "Send another UID or type /done to finish.")
        return SINGLE_UID

    try:
        result = uids_col.update_one(
            {'uid': uid},
            {
                '$set': {
                    'verified':
                    True,  # UID is verified since admin added it to database
                    'fully_verified': False,
                    'admin_added': True,
                    'verified_by': ADMIN_UID,  # Admin added this UID
                    'verified_by_tg_id': None,  # Admin added - no specific user TG ID
                    'added_date': update.message.date
                }
            },
            upsert=True)

        if result.upserted_id:
            update.message.reply_text(
                f"✅ UID {uid} added to database.\n"
                f"Send another UID or type /done to finish.")
        else:
            update.message.reply_text(
                f"✅ UID {uid} updated in database.\n"
                f"Send another UID or type /done to finish.")

    except Exception as e:
        logger.error(f"Error updating single UID: {e}")
        update.message.reply_text("❌ Database error. Please try again.")

    return SINGLE_UID


def handle_bulk_images(update: Update, context: CallbackContext):
    """
    Handle bulk image processing for UID extraction
    """
    if update.message.text and update.message.text == '/done':
        logger.info(
            f"Bulk image mode completed by user {update.message.from_user.id}")
        update.message.reply_text("✅ Bulk update completed.",
                                  reply_markup=ReplyKeyboardRemove())
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
            update.message.reply_text(
                "❌ Could not process image. Try another image.")
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
                    {
                        '$set': {
                            'verified':
                            True,  # UID is verified since admin added it to database
                            'fully_verified': False,
                            'admin_added': True,
                            'bulk_added': True,
                            'verified_by': ADMIN_UID,  # Admin added this UID
                            'verified_by_tg_id': None,  # Admin added - no specific user TG ID
                            'added_date': update.message.date
                        }
                    },
                    upsert=True)
                updated_count += 1
            except Exception as e:
                logger.error(f"Error updating UID {uid}: {e}")

        update.message.reply_text(
            f"✅ Processed {updated_count} UID(s) from image.\n"
            f"Found UIDs: {', '.join(found_uids[:10])}{'...' if len(found_uids) > 10 else ''}\n\n"
            f"Send another image or /done to finish.")

    except Exception as e:
        logger.error(f"Error in bulk image processing: {e}")
        update.message.reply_text(
            "❌ Error processing image. Please try again.")

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
        uids = list(
            uids_col.find({'fully_verified': True}, {
                'uid': 1,
                'username': 1,
                'wallet_balance': 1
            }))

        if not uids:
            update.message.reply_text("📭 No verified UIDs found.")
            return

        uid_list = []
        for doc in uids[:50]:  # Limit to 50 to avoid message length issues
            balance = doc.get('wallet_balance', 'N/A')
            username = doc.get('username', 'Unknown')
            # Escape markdown characters in username
            safe_username = username.replace('_', '\\_').replace(
                '*', '\\*').replace('[', '\\[').replace('`', '\\`')
            balance_str = f"{balance:.2f}" if isinstance(
                balance, (int, float)) and balance != 'N/A' else balance
            uid_list.append(
                f"✅ {doc['uid']} (@{safe_username}, ₹{balance_str})")

        message = f"🎉 *Verified UIDs ({len(uids)} total)*\n\n" + "\n".join(
            uid_list)
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
        uids = list(
            uids_col.find(
                {
                    'fully_verified': False,
                    'notified_for_wallet': {
                        '$ne': True
                    }  # Exclude UIDs already in wallet verification stage
                },
                {
                    'uid': 1,
                    'username': 1
                }))

        if not uids:
            update.message.reply_text("📭 No non-verified UIDs found.")
            return

        uid_list = []
        for doc in uids[:50]:  # Limit to 50
            username = doc.get('username', 'Unknown')
            # Escape markdown characters in username
            safe_username = username.replace('_', '\\_').replace(
                '*', '\\*').replace('[', '\\[').replace('`', '\\`')
            uid_list.append(f"❌ {doc['uid']} (@{safe_username})")

        message = f"⏳ *Non-Verified UIDs ({len(uids)} total)*\n\n" + "\n".join(
            uid_list)
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
        uids = list(
            uids_col.find({}, {
                'uid': 1,
                'fully_verified': 1
            }).limit(50))

        if not uids:
            update.message.reply_text("📭 No UIDs found in database.")
            return

        uid_list = []
        for doc in uids:
            status = "✅" if doc.get('fully_verified') else "❌"
            uid_list.append(f"{status} {doc['uid']}")

        message = f"📂 *All UIDs ({total_count} total)*\n\n" + "\n".join(
            uid_list)
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
            parse_mode='Markdown')
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
            parse_mode='Markdown')

        # Log deletion
        logger.info(
            f"Admin {update.message.from_user.username} deleted {result.deleted_count} UIDs"
        )

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
            parse_mode='Markdown')
        return

    try:
        num = int(context.args[0])

        if num <= 0 or num > len(last_extractions):
            update.message.reply_text(
                f"❌ Invalid number. Available: 1-{len(last_extractions)}")
            return

        # Collect UIDs to delete
        to_delete = []
        for block in last_extractions[:num]:
            to_delete.extend(block)

        if not to_delete:
            update.message.reply_text(
                "❌ No UIDs found in selected extractions.")
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
            parse_mode='Markdown')

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
        # Find UIDs that are verified (in database) and have user_id but users haven't been notified for wallet verification
        # This includes both UIDs added by admin that users later tried to verify, and UIDs users submitted that were found in DB
        newly_verified = list(
            uids_col.find({
                '$or': [{
                    'admin_added': True,
                    'verified': True,
                    'fully_verified': False,
                    'user_id': {
                        '$exists': True,
                        '$ne': None
                    },
                    'notified_for_wallet': {
                        '$ne': True
                    }
                }, {
                    'verified': True,
                    'fully_verified': False,
                    'user_id': {
                        '$exists': True,
                        '$ne': None
                    },
                    'notified_for_wallet': {
                        '$ne': True
                    }
                }]
            }))

        if not newly_verified:
            update.message.reply_text(
                "ℹ️ No newly verified UIDs found in non-verified list.")
            return

        notified_count = 0
        for doc in newly_verified:
            try:
                user_id = doc['user_id']
                uid = doc['uid']
                username = doc.get('username', 'User')

                # Send notification to user
                message = (
                    f"*⚡Great News, Champ! 🧞‍♂️*\n\n"
                    f"*✅ UID {uid} Verified Successfully*\n"
                    f"*📩 Now, Please Send Your Wallet Screenshot For Balance Check.*\n"
                    f"*💰 Minimum Required Balance: ₹100*")

                sent = safe_send_message(context=context,
                                         chat_id=user_id,
                                         text=message,
                                         parse_mode='Markdown')

                if sent is None:
                    logger.warning(
                        f"Could not notify user {user_id} - they have blocked the bot"
                    )
                    continue

                # Mark as notified and set up for wallet verification
                uids_col.update_one({'_id': doc['_id']},
                                    {'$set': {
                                        'notified_for_wallet': True
                                    }})

                # Add to pending wallets
                if 'pending_wallets' not in context.bot_data:
                    context.bot_data['pending_wallets'] = {}
                context.bot_data['pending_wallets'][user_id] = uid

                notified_count += 1

            except Exception as e:
                logger.error(
                    f"Error notifying user {doc.get('user_id', 'Unknown')}: {e}"
                )

        # Now check for UIDs that are still unverified and notify users of rejection
        # Exclude UIDs that have been notified for wallet verification
        still_unverified = list(
            uids_col.find({
                'verified': False,
                'fully_verified': False,
                'user_id': {
                    '$exists': True,
                    '$ne': None
                },
                'rejection_notified': {
                    '$ne': True
                },
                'notified_for_wallet': {
                    '$ne': True
                }  # Exclude UIDs already in wallet verification stage
            }))

        rejected_count = 0
        deleted_count = 0
        rejected_uids = []
        for doc in still_unverified:
            try:
                user_id = doc['user_id']
                uid = doc['uid']

                # Send rejection message to user
                rejection_message = (
                    f"*❌ Your UID {uid} Got Rejected !*\n\n"
                    f"*⚠️ Again Register With Official Link To Get VIP Hack Prediction & Gift Codes At Free !!*"
                )

                # Create inline keyboard with registration button
                keyboard = [[
                    InlineKeyboardButton(
                        "✅ Official Register Link",
                        url=
                        "https://www.jalwagame4.com/#/register?invitationCode=16887113053"
                    )
                ]]
                reply_markup = InlineKeyboardMarkup(keyboard)

                sent = safe_send_message(context=context,
                                         chat_id=user_id,
                                         text=rejection_message,
                                         parse_mode='Markdown',
                                         reply_markup=reply_markup)

                if sent is None:
                    logger.warning(
                        f"Could not send rejection to user {user_id} - they have blocked the bot"
                    )
                    # Still count as rejected and delete the UID
                    pass

                # Auto-delete the rejected UID from database
                delete_result = uids_col.delete_one({'_id': doc['_id']})
                if delete_result.deleted_count > 0:
                    deleted_count += 1
                    rejected_uids.append(uid)

                rejected_count += 1

            except Exception as e:
                logger.error(
                    f"Error sending rejection to user {doc.get('user_id', 'Unknown')}: {e}"
                )

        # Create list of newly verified UIDs for display
        verified_uid_list = []
        for doc in newly_verified:
            uid = doc['uid']
            username = doc.get('username', 'Unknown')
            # Escape markdown characters in username
            safe_username = username.replace('_', '\\_').replace(
                '*', '\\*').replace('[', '\\[').replace('`', '\\`')
            verified_uid_list.append(f"• {uid} (@{safe_username})")

        # Prepare summary message
        summary_message = f"📢 *Notification Summary*\n\n"

        if newly_verified:
            summary_message += f"✅ Found {len(newly_verified)} newly verified UIDs in non-verified list\n"
            summary_message += f"✅ Notified {notified_count} users about verified UIDs\n"
            summary_message += f"📸 They have been asked to send wallet screenshots\n\n"
            summary_message += f"🔄 *UIDs that changed from unverified to verified:*\n"
            summary_message += "\n".join(
                verified_uid_list[:20])  # Show max 20 UIDs
            if len(verified_uid_list) > 20:
                summary_message += f"\n... and {len(verified_uid_list) - 20} more"
            summary_message += "\n\n"
        else:
            summary_message += f"ℹ️ No newly verified UIDs found in non-verified list\n\n"

        summary_message += f"❌ Found {len(still_unverified)} still unverified UIDs\n"
        summary_message += f"❌ Sent rejection messages to {rejected_count} users\n"
        summary_message += f"🗑️ Auto-deleted {deleted_count} rejected UIDs from database"

        update.message.reply_text(summary_message, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Error checking newly verified UIDs: {e}")
        update.message.reply_text("❌ Error checking for newly verified UIDs.")


def reject_command(update: Update, context: CallbackContext):
    """
    Send rejection message to all non-verified users (Admin only)
    """
    if update.message.from_user.id != ADMIN_UID:
        update.message.reply_text("❌ Unauthorized access.")
        return

    update.message.reply_text(
        "🔄 Sending rejection messages to all non-verified users...")

    try:
        # Find all UIDs that are not fully verified and have user_id
        # Exclude UIDs that have been notified for wallet verification
        non_verified_users = list(
            uids_col.find({
                'fully_verified': False,
                'user_id': {
                    '$exists': True,
                    '$ne': None
                },
                'notified_for_wallet': {
                    '$ne': True
                }  # Exclude UIDs already in wallet verification stage
            }))

        if not non_verified_users:
            update.message.reply_text("ℹ️ No non-verified users found.")
            return

        # Create list of rejected UIDs for display BEFORE deletion
        rejected_uid_list = []
        for doc in non_verified_users[:20]:  # Show max 20 UIDs
            uid = doc['uid']
            username = doc.get('username', 'Unknown')
            # Escape markdown characters in username
            safe_username = username.replace('_', '\\_').replace(
                '*', '\\*').replace('[', '\\[').replace('`', '\\`')
            rejected_uid_list.append(f"• {uid} (@{safe_username})")

        rejected_count = 0
        deleted_count = 0
        for doc in non_verified_users:
            try:
                user_id = doc['user_id']
                uid = doc['uid']

                # Send rejection message to user
                rejection_message = (
                    f"*❌ Your UID {uid} Got Rejected !*\n\n"
                    f"*⚠️ Again Register With Official Link To Get VIP Hack Prediction & Gift Codes At Free !!*"
                )

                # Create inline keyboard with registration button
                keyboard = [[
                    InlineKeyboardButton(
                        "✅ Official Register Link",
                        url=
                        "https://www.jalwagame4.com/#/register?invitationCode=16887113053"
                    )
                ]]
                reply_markup = InlineKeyboardMarkup(keyboard)

                sent = safe_send_message(context=context,
                                         chat_id=user_id,
                                         text=rejection_message,
                                         parse_mode='Markdown',
                                         reply_markup=reply_markup)

                if sent is None:
                    logger.warning(
                        f"Could not send rejection to user {user_id} - they have blocked the bot"
                    )
                    # Still count as rejected and delete the UID
                    pass

                # Auto-delete the rejected UID from database
                delete_result = uids_col.delete_one({'_id': doc['_id']})
                if delete_result.deleted_count > 0:
                    deleted_count += 1

                rejected_count += 1

            except Exception as e:
                logger.error(
                    f"Error sending rejection to user {doc.get('user_id', 'Unknown')}: {e}"
                )

        summary_message = (
            f"📢 *REJECTION COMPLETED*\n\n"
            f"🔍 Non-verified users found: {len(non_verified_users)}\n"
            f"✅ Rejection messages sent: {rejected_count}\n"
            f"🗑️ UIDs deleted from database: {deleted_count}\n\n")

        if rejected_uid_list:
            summary_message += f"🚫 *Rejected & Deleted UIDs:*\n"
            summary_message += "\n".join(rejected_uid_list)
            if len(non_verified_users) > 20:
                summary_message += f"\n... and {len(non_verified_users) - 20} more"
            summary_message += f"\n\n✅ All rejected users have been automatically removed from the database"
        else:
            summary_message += "ℹ️ No users were rejected (database was already clean)"

        update.message.reply_text(summary_message, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Error sending rejection messages: {e}")
        update.message.reply_text("❌ Error sending rejection messages.")


def newcode_command(update: Update, context: CallbackContext):
    """
    Update gift code (Admin only)
    Usage: /newcode NEWCODE123
    """
    if update.message.from_user.id != ADMIN_UID:
        update.message.reply_text("❌ Unauthorized access.")
        return

    if not context.args:
        update.message.reply_text(
            "🎁 *Update Gift Code*\n\n"
            "Usage: `/newcode <new_gift_code>`\n"
            "Example: `/newcode ABC123XYZ789`",
            parse_mode='Markdown')
        return

    try:
        new_code = ' '.join(context.args).strip()

        if not new_code:
            update.message.reply_text("❌ Gift code cannot be empty.")
            return

        # Get current date for updated_date
        from datetime import timezone, timedelta
        ist = timezone(timedelta(hours=5, minutes=30))
        current_date = datetime.now(ist).strftime("%d/%m/%Y at %I:%M %p IST")

        # Deactivate old codes
        gift_codes_col.update_many({'active': True},
                                   {'$set': {
                                       'active': False
                                   }})

        # Insert new gift code
        new_gift_code = {
            'code': new_code,
            'updated_date': current_date,
            'active': True,
            'created_at': datetime.now()
        }

        gift_codes_col.insert_one(new_gift_code)

        update.message.reply_text(
            f"✅ *Gift Code Updated Successfully!*\n\n"
            f"🎁 New Code: `{new_code}`\n"
            f"🕒 Updated: {current_date}\n"
            f"🔄 Next Update: 24 hours Later\n\n"
            f"🔔 *Broadcasting notification to all users...*",
            parse_mode='Markdown')

        # Broadcast notification to all users
        broadcast_gift_code_notification(context, new_code)

        logger.info(
            f"Admin {update.message.from_user.username} updated gift code to: {new_code}"
        )

    except Exception as e:
        logger.error(f"Error updating gift code: {e}")
        update.message.reply_text("❌ Error updating gift code.")


def broadcast_gift_code_notification(context: CallbackContext, new_code: str):
    """
    Broadcast gift code notification to all users
    """
    try:
        # Get all users who have interacted with the bot (not blocked by admin)
        all_users = list(
            user_stats_col.find({
                'user_id': {
                    '$ne': 'global_stats',
                    '$exists': True
                },
                '$or': [
                    {
                        'is_blocked': {
                            '$ne': True
                        }
                    },
                    {
                        'is_blocked': {
                            '$exists': False
                        }
                    },
                    {
                        'is_blocked': True,
                        'blocked_by_user':
                        True  # Include users who blocked the bot (they might unblock)
                    }
                ]
            }))

        notification_message = "*Hey Buddy 😉 !! Your Gift Code is Live ,Tap /claim and Grab It Now! 🚀*"

        sent_count = 0
        failed_count = 0

        for user_doc in all_users:
            try:
                user_id = user_doc['user_id']

                # Send notification using safe_send_message
                sent = safe_send_message(context=context,
                                         chat_id=user_id,
                                         text=notification_message,
                                         parse_mode='Markdown')

                if sent is None:
                    failed_count += 1
                else:
                    sent_count += 1

                # Add small delay to avoid rate limiting
                import time
                time.sleep(0.1)

            except Exception as e:
                logger.error(
                    f"Error sending gift code notification to user {user_doc.get('user_id', 'Unknown')}: {e}"
                )
                failed_count += 1

        logger.info(
            f"Gift code notification sent to {sent_count} users, {failed_count} failed"
        )

    except Exception as e:
        logger.error(f"Error broadcasting gift code notification: {e}")


def claim_command(update: Update, context: CallbackContext):
    """
    Handle /claim command for gift codes
    """
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
            # User is fully verified - show gift codes page
            gift_codes_msg = (
                "*📋 Join All Channels To Unlock the Gift Code!*\n\n"
                "*🎁 Earn More Exclusive Gift Codes From Here*\n\n"
                "*⚠️ You must join ALL 4 channels below to unlock gift codes:*"
            )

            # Create inline keyboard with JOIN buttons for all 4 channels and unlock button
            keyboard = [
                [
                    InlineKeyboardButton("JOIN",
                                         url="https://t.me/+vge9Lu_k4wUyYTY9"),
                    InlineKeyboardButton("JOIN",
                                         url="https://t.me/+7io6Ktb7WwQzZjll")
                ],
                [
                    InlineKeyboardButton("JOIN",
                                         url="https://t.me/+mm3dF_L31cg2NjA1"),
                    InlineKeyboardButton("JOIN",
                                         url="https://t.me/+2u_ekSv7S71lZTll")
                ],
                [
                    InlineKeyboardButton("🔐 Unlock Gift Code",
                                         callback_data="unlock_gift_code")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            # Send photo with gift codes page
            try:
                update.message.reply_photo(
                    photo="https://files.catbox.moe/zk8ir9.webp",
                    caption=gift_codes_msg,
                    parse_mode='Markdown',
                    reply_markup=reply_markup)
            except Exception as e:
                logger.error(f"Error sending photo in claim command: {e}")
                # Fallback to text message if photo fails
                update.message.reply_text(gift_codes_msg,
                                          parse_mode='Markdown',
                                          reply_markup=reply_markup)
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


def block_user_command(update: Update, context: CallbackContext):
    """
    Block/unblock users (Admin only)
    Usage: /block user_id or /unblock user_id
    """
    if update.message.from_user.id != ADMIN_UID:
        update.message.reply_text("❌ Unauthorized access.")
        return

    command = update.message.text.split()[0].lower()
    is_block = command == '/block'

    if not context.args:
        action = "block" if is_block else "unblock"
        update.message.reply_text(
            f"🚫 *{action.title()} User*\n\n"
            f"Usage: `/{action} <user_id>`\n"
            f"Example: `/{action} 123456789`",
            parse_mode='Markdown')
        return

    try:
        target_user_id = int(context.args[0])

        # Update user stats
        user_stats_col.update_one({'user_id': target_user_id}, {
            '$set': {
                'is_blocked': is_block,
                'blocked_date': datetime.now() if is_block else None
            }
        },
                                  upsert=True)

        # Update global counts
        if is_block:
            user_stats_col.update_one(
                {'_id': 'global_stats'},
                {
                    '$inc': {
                        'blocked_users': 1,
                        'total_users':
                        -1  # Remove from total when admin blocks
                    }
                },
                upsert=True)
        else:
            user_stats_col.update_one(
                {'_id': 'global_stats'},
                {
                    '$inc': {
                        'blocked_users': -1,
                        'total_users':
                        1  # Add back to total when admin unblocks
                    }
                },
                upsert=True)

        action = "blocked" if is_block else "unblocked"
        emoji = "🚫" if is_block else "✅"

        update.message.reply_text(
            f"{emoji} User {target_user_id} has been {action} successfully!",
            parse_mode='Markdown')

        logger.info(
            f"Admin {update.message.from_user.username} {action} user {target_user_id}"
        )

    except ValueError:
        update.message.reply_text("❌ Invalid user ID format.")
    except Exception as e:
        logger.error(f"Error blocking/unblocking user: {e}")
        update.message.reply_text("❌ Error processing request.")


def check_blocked_command(update: Update, context: CallbackContext):
    """
    Check for users who have blocked the bot and update stats (Admin only)
    """
    if update.message.from_user.id != ADMIN_UID:
        update.message.reply_text("❌ Unauthorized access.")
        return

    try:
        update.message.reply_text(
            "🔍 Checking for users who have blocked the bot...")

        newly_blocked = check_blocked_users(context)

        # Get updated stats
        stats_data = get_user_activity_stats()

        update.message.reply_text(
            f"✅ *Blocked Users Check Complete*\n\n"
            f"🔍 Newly detected blocked users: {newly_blocked}\n"
            f"🚫 Total blocked users: {stats_data['blocked_users']}\n"
            f"👥 Total users: {stats_data['total_users']}\n"
            f"📊 Block rate: {(stats_data['blocked_users']/stats_data['total_users']*100) if stats_data['total_users'] > 0 else 0:.1f}%",
            parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Error checking blocked users: {e}")
        update.message.reply_text("❌ Error checking blocked users.")


def restrict_command(update: Update, context: CallbackContext):
    """
    Toggle global restriction mode (Admin only)
    Usage: /restrict on or /restrict off
    """
    global restrict_mode

    if update.message.from_user.id != ADMIN_UID:
        update.message.reply_text("❌ Unauthorized access.")
        return

    if not context.args:
        current_status = "ON" if restrict_mode else "OFF"
        update.message.reply_text(
            f"🔐 *Restriction Mode Control*\n\n"
            f"*Current Status:* {current_status}\n\n"
            f"*Usage:*\n"
            f"• `/restrict on` - Enable restriction mode\n"
            f"• `/restrict off` - Disable restriction mode",
            parse_mode='Markdown')
        return

    try:
        mode = context.args[0].lower()

        if mode == 'on':
            restrict_mode = True
            update.message.reply_text("🔐 Restriction Mode is now ON")
            logger.info(
                f"Admin {update.message.from_user.username} enabled restriction mode"
            )
        elif mode == 'off':
            restrict_mode = False
            update.message.reply_text("🔓 Restriction Mode is now OFF")
            logger.info(
                f"Admin {update.message.from_user.username} disabled restriction mode"
            )
        else:
            update.message.reply_text(
                "❌ Invalid option. Use `/restrict on` or `/restrict off`")

    except Exception as e:
        logger.error(f"Error in restrict command: {e}")
        update.message.reply_text("❌ Error processing restriction command.")


def cast_command(update: Update, context: CallbackContext):
    """
    Broadcast message to all users (Admin only)
    Usage: /cast <message> or reply to a message with /cast
    Supports: Text, Photos, Videos, Documents, Stickers, and Inline Keyboards
    """
    if update.message.from_user.id != ADMIN_UID:
        update.message.reply_text("❌ Unauthorized access.")
        return

    broadcast_content = None
    content_type = "text"
    broadcast_message = ""
    reply_markup = None

    # Check if the command is a reply to another message
    if update.message.reply_to_message:
        replied_msg = update.message.reply_to_message
        
        # Handle different message types
        if replied_msg.photo:
            content_type = "photo"
            broadcast_content = replied_msg.photo[-1].file_id  # Get highest resolution
            broadcast_message = replied_msg.caption or ""
            reply_markup = replied_msg.reply_markup
        elif replied_msg.video:
            content_type = "video" 
            broadcast_content = replied_msg.video.file_id
            broadcast_message = replied_msg.caption or ""
            reply_markup = replied_msg.reply_markup
        elif replied_msg.document:
            content_type = "document"
            broadcast_content = replied_msg.document.file_id
            broadcast_message = replied_msg.caption or ""
            reply_markup = replied_msg.reply_markup
        elif replied_msg.sticker:
            content_type = "sticker"
            broadcast_content = replied_msg.sticker.file_id
            reply_markup = replied_msg.reply_markup
        elif replied_msg.animation:
            content_type = "animation"
            broadcast_content = replied_msg.animation.file_id
            broadcast_message = replied_msg.caption or ""
            reply_markup = replied_msg.reply_markup
        elif replied_msg.voice:
            content_type = "voice"
            broadcast_content = replied_msg.voice.file_id
            broadcast_message = replied_msg.caption or ""
            reply_markup = replied_msg.reply_markup
        elif replied_msg.audio:
            content_type = "audio"
            broadcast_content = replied_msg.audio.file_id
            broadcast_message = replied_msg.caption or ""
            reply_markup = replied_msg.reply_markup
        elif replied_msg.text:
            content_type = "text"
            broadcast_message = replied_msg.text
            reply_markup = replied_msg.reply_markup
        else:
            update.message.reply_text(
                "❌ Cannot cast this type of message. Please reply to a supported message type."
            )
            return
    elif context.args:
        # Use the arguments provided with the command
        content_type = "text"
        broadcast_message = ' '.join(context.args)
    else:
        # No arguments and no reply
        update.message.reply_text(
            "📢 *Enhanced Cast Message to All Users*\n\n"
            "*Supported message types:*\n"
            "• Text messages\n"
            "• Photos with captions\n"
            "• Videos with captions\n"
            "• Documents/Files\n"
            "• Stickers\n"
            "• Voice messages\n"
            "• Audio files\n"
            "• GIFs/Animations\n"
            "• Messages with inline keyboards/buttons\n\n"
            "*Usage methods:*\n\n"
            "*Method 1:* `/cast <your_message>`\n"
            "*Method 2:* Reply to any supported message with `/cast`\n\n"
            "⚠️ This will send the message to ALL bot users.",
            parse_mode='Markdown')
        return

    if content_type == "text" and not broadcast_message.strip():
        update.message.reply_text("❌ Message cannot be empty.")
        return

    try:
        # Show what message will be broadcasted
        preview_message = (
            f"📡 *Starting broadcast...*\n\n"
            f"*Message to broadcast:*\n"
            f"`{broadcast_message[:200]}{'...' if len(broadcast_message) > 200 else ''}`\n\n"
            f"*This may take a while.*")
        update.message.reply_text(preview_message, parse_mode='Markdown')

        # Get all users who have interacted with the bot (not blocked by admin)
        all_users = list(
            user_stats_col.find({
                'user_id': {
                    '$ne': 'global_stats',
                    '$exists': True
                },
                '$or': [
                    {
                        'is_blocked': {
                            '$ne': True
                        }
                    },
                    {
                        'is_blocked': {
                            '$exists': False
                        }
                    },
                    {
                        'is_blocked': True,
                        'blocked_by_user':
                        True  # Include users who blocked the bot (they might unblock)
                    }
                ]
            }))

        total_users = len(all_users)
        sent_count = 0
        failed_count = 0
        newly_blocked = 0

        for user_doc in all_users:
            try:
                user_id = user_doc['user_id']
                sent = None

                # Send different types of content
                if content_type == "photo":
                    try:
                        sent_msg = context.bot.send_photo(
                            chat_id=user_id,
                            photo=broadcast_content,
                            caption=broadcast_message if broadcast_message else None,
                            parse_mode='Markdown',
                            reply_markup=reply_markup
                        )
                        sent = True
                    except Exception as e:
                        if "blocked" in str(e).lower() or "chat not found" in str(e).lower():
                            sent = None
                        else:
                            raise e

                elif content_type == "video":
                    try:
                        sent_msg = context.bot.send_video(
                            chat_id=user_id,
                            video=broadcast_content,
                            caption=broadcast_message if broadcast_message else None,
                            parse_mode='Markdown',
                            reply_markup=reply_markup
                        )
                        sent = True
                    except Exception as e:
                        if "blocked" in str(e).lower() or "chat not found" in str(e).lower():
                            sent = None
                        else:
                            raise e

                elif content_type == "document":
                    try:
                        sent_msg = context.bot.send_document(
                            chat_id=user_id,
                            document=broadcast_content,
                            caption=broadcast_message if broadcast_message else None,
                            parse_mode='Markdown',
                            reply_markup=reply_markup
                        )
                        sent = True
                    except Exception as e:
                        if "blocked" in str(e).lower() or "chat not found" in str(e).lower():
                            sent = None
                        else:
                            raise e

                elif content_type == "sticker":
                    try:
                        sent_msg = context.bot.send_sticker(
                            chat_id=user_id,
                            sticker=broadcast_content,
                            reply_markup=reply_markup
                        )
                        sent = True
                    except Exception as e:
                        if "blocked" in str(e).lower() or "chat not found" in str(e).lower():
                            sent = None
                        else:
                            raise e

                elif content_type == "animation":
                    try:
                        sent_msg = context.bot.send_animation(
                            chat_id=user_id,
                            animation=broadcast_content,
                            caption=broadcast_message if broadcast_message else None,
                            parse_mode='Markdown',
                            reply_markup=reply_markup
                        )
                        sent = True
                    except Exception as e:
                        if "blocked" in str(e).lower() or "chat not found" in str(e).lower():
                            sent = None
                        else:
                            raise e

                elif content_type == "voice":
                    try:
                        sent_msg = context.bot.send_voice(
                            chat_id=user_id,
                            voice=broadcast_content,
                            caption=broadcast_message if broadcast_message else None,
                            parse_mode='Markdown',
                            reply_markup=reply_markup
                        )
                        sent = True
                    except Exception as e:
                        if "blocked" in str(e).lower() or "chat not found" in str(e).lower():
                            sent = None
                        else:
                            raise e

                elif content_type == "audio":
                    try:
                        sent_msg = context.bot.send_audio(
                            chat_id=user_id,
                            audio=broadcast_content,
                            caption=broadcast_message if broadcast_message else None,
                            parse_mode='Markdown',
                            reply_markup=reply_markup
                        )
                        sent = True
                    except Exception as e:
                        if "blocked" in str(e).lower() or "chat not found" in str(e).lower():
                            sent = None
                        else:
                            raise e

                else:  # text message
                    sent = safe_send_message(context=context,
                                           chat_id=user_id,
                                           text=broadcast_message,
                                           parse_mode='Markdown',
                                           reply_markup=reply_markup)

                if sent is None:
                    # User has blocked the bot
                    failed_count += 1
                    newly_blocked += 1
                else:
                    sent_count += 1

                # Add small delay to avoid rate limiting
                import time
                time.sleep(0.1)

            except Exception as e:
                logger.error(
                    f"Error sending broadcast to user {user_doc.get('user_id', 'Unknown')}: {e}"
                )
                failed_count += 1

        # Send summary to admin
        content_description = {
            "text": "Text Message",
            "photo": "Photo with Caption",
            "video": "Video with Caption", 
            "document": "Document/File",
            "sticker": "Sticker",
            "animation": "GIF/Animation",
            "voice": "Voice Message",
            "audio": "Audio File"
        }
        
        summary_message = (
            f"📊 *Broadcast Summary*\n\n"
            f"📱 Total Users Found: {total_users}\n"
            f"✅ Messages Sent: {sent_count}\n"
            f"❌ Failed to Send: {failed_count}\n"
            f"🚫 Newly Blocked Users: {newly_blocked}\n\n"
            f"📈 Success Rate: {(sent_count/total_users*100) if total_users > 0 else 0:.1f}%\n\n"
            f"📤 Content Type: {content_description.get(content_type, 'Unknown')}\n"
            f"🔘 Inline Buttons: {'Yes' if reply_markup else 'No'}\n\n"
            f"💬 Message/Caption:\n`{broadcast_message if broadcast_message else 'No text content'}`")

        update.message.reply_text(summary_message, parse_mode='Markdown')

        logger.info(
            f"Admin {update.message.from_user.username} broadcasted message to {sent_count} users"
        )

    except Exception as e:
        logger.error(f"Error in cast command: {e}")
        update.message.reply_text("❌ Error broadcasting message.")


# MESSAGE HANDLERS


def handle_all(update: Update, context: CallbackContext):
    """
    Handle all incoming messages (text and photos)
    """
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


def cancel_conversation(update: Update, context: CallbackContext):
    """
    Cancel any ongoing conversation
    """
    logger.info(
        f"Conversation cancelled by user {update.message.from_user.id}")
    update.message.reply_text("❌ Operation cancelled.",
                              reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


def handle_confirm_delete_all_data(update: Update, context: CallbackContext):
    """
    Handle the delete button callback - show confirmation
    """
    query = update.callback_query
    query.answer()

    # Get current stats for confirmation message
    try:
        stats_data = get_user_activity_stats()

        confirmation_msg = (
            f"⚠️ *DANGEROUS ACTION - CONFIRMATION REQUIRED*\n\n"
            f"🗑️ *You are about to DELETE ALL user data:*\n\n"
            f"🤖 Total Bot Users: {stats_data['total_users']}\n"
            f"✅ Verified UIDs: {stats_data['verified_uids']}\n"
            f"🔒 Fully Verified Users: {stats_data['fully_verified_users']}\n"
            f"⚠️ Non-Verified Users: {stats_data['non_verified_users']}\n\n"
            f"*This action will:*\n"
            f"• Delete ALL UID records\n"
            f"• Delete ALL user statistics\n"
            f"• Reset all counters to 0\n"
            f"• Cannot be undone!\n\n"
            f"*Are you sure you want to proceed?*")

        # Create confirmation keyboard
        keyboard = [[
            InlineKeyboardButton("✅ YES - DELETE ALL",
                                 callback_data="delete_all_data_yes")
        ],
                    [
                        InlineKeyboardButton(
                            "❌ NO - CANCEL",
                            callback_data="delete_all_data_no")
                    ]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        query.edit_message_text(text=confirmation_msg,
                                parse_mode='Markdown',
                                reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Error in confirmation dialog: {e}")
        query.edit_message_text("❌ Error showing confirmation dialog.")


def handle_delete_all_data_yes(update: Update, context: CallbackContext):
    """
    Handle YES confirmation - directly execute database deletion
    """
    query = update.callback_query
    query.answer()

    query.edit_message_text(
        text="⏳ *Executing database deletion...*",
        parse_mode='Markdown')
    
    # Create a mock update object for execute_database_deletion
    class MockUpdate:
        def __init__(self, user):
            self.message = self
            self.from_user = user
            
        def reply_text(self, text, parse_mode=None):
            query.edit_message_text(text=text, parse_mode=parse_mode)
    
    mock_update = MockUpdate(query.from_user)
    execute_database_deletion(mock_update, context)


def execute_database_deletion(update: Update, context: CallbackContext):
    """
    Execute the actual database deletion after captcha verification
    """
    try:
        # Count records before deletion for summary
        uid_count = uids_col.count_documents({})
        user_stats_count = user_stats_col.count_documents(
            {'user_id': {
                '$ne': 'global_stats'
            }})

        # Delete all UID records
        uid_delete_result = uids_col.delete_many({})

        # Delete all user statistics (except global_stats which we'll reset)
        user_stats_delete_result = user_stats_col.delete_many(
            {'user_id': {
                '$ne': 'global_stats'
            }})

        # Reset global statistics to 0
        user_stats_col.update_one({'_id': 'global_stats'}, {
            '$set': {
                'total_users': 0,
                'blocked_users': 0,
                'reset_date': datetime.now(),
                'reset_by_admin': True
            }
        },
                                  upsert=True)

        # Clear bot data
        if 'pending_wallets' in context.bot_data:
            context.bot_data['pending_wallets'].clear()
        if 'verified_members' in context.bot_data:
            context.bot_data['verified_members'].clear()
        if 'waiting_for_digits' in context.bot_data:
            context.bot_data['waiting_for_digits'].clear()
        if 'digits_message_id' in context.bot_data:
            context.bot_data['digits_message_id'].clear()

        success_msg = (
            f"✅ *ALL DATA SUCCESSFULLY DELETED*\n\n"
            f"🗑️ *Deletion Summary:*\n"
            f"• UID Records Deleted: {uid_delete_result.deleted_count}\n"
            f"• User Statistics Deleted: {user_stats_delete_result.deleted_count}\n"
            f"• Global Counters Reset: ✅\n"
            f"• Bot Memory Cleared: ✅\n\n"
            f"📊 *All statistics are now reset to 0*\n"
            f"🔄 *Bot is ready for fresh start*\n\n"
            f"⚠️ *Data deletion completed at:*\n"
            f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")

        update.message.reply_text(text=success_msg, parse_mode='Markdown')

        logger.info(
            f"Admin {update.message.from_user.username} deleted all user data - UIDs: {uid_delete_result.deleted_count}, Users: {user_stats_delete_result.deleted_count}"
        )

    except Exception as e:
        logger.error(f"Error deleting all data: {e}")
        update.message.reply_text(
            f"❌ *Error deleting data:*\n{str(e)}\n\nPlease check logs and try again.",
            parse_mode='Markdown')


def handle_delete_all_data_no(update: Update, context: CallbackContext):
    """
    Handle NO confirmation - cancel deletion and return to stats
    """
    query = update.callback_query
    query.answer("✅ Deletion cancelled")
    
    # Clear captcha data if exists
    user_id = query.from_user.id
    if 'delete_captcha' in context.bot_data and user_id in context.bot_data['delete_captcha']:
        del context.bot_data['delete_captcha'][user_id]
    if 'waiting_for_delete_captcha' in context.bot_data and user_id in context.bot_data['waiting_for_delete_captcha']:
        context.bot_data['waiting_for_delete_captcha'].remove(user_id)

    try:
        # Get fresh stats data
        stats_data = get_user_activity_stats()

        # Get detailed blocked user statistics
        admin_blocked = user_stats_col.count_documents({
            'is_blocked':
            True,
            '$or': [{
                'blocked_by_user': {
                    '$exists': False
                }
            }, {
                'blocked_by_user': False
            }]
        })
        user_blocked = user_stats_col.count_documents({
            'is_blocked': True,
            'blocked_by_user': True
        })

        msg = (
            f"📊 *USER ACTIVITY REPORT*\n\n"
            f"🤖 Total Bot Users: {stats_data['total_users']}\n"
            f"🚫 Blocked Users: {stats_data['blocked_users']}\n"
            f"   ├─ 👤 User Blocked Bot: {user_blocked}\n"
            f"   └─ 🛡️ Admin Blocked: {admin_blocked}\n"
            f"✅ Verified UIDs: {stats_data['verified_uids']}\n"
            f"🔒 Fully Verified Users: {stats_data['fully_verified_users']}\n"
            f"⚠️ Non-Verified Users: {stats_data['non_verified_users']}\n"
            f"🛠 UIDs Updated by Admin: {stats_data['admin_updated_uids']}\n"
            f"⏳ Pending Wallet Verifications: {stats_data['pending_wallet_verifications']}\n"
            f"💰 Users with Valid Balance: {stats_data['users_with_valid_balance']}\n\n"
            f"📈 Verification Rate: {(stats_data['verified_uids']/stats_data['non_verified_users']*100) if stats_data['non_verified_users'] > 0 else 0:.1f}%"
        )

        # Create inline keyboard with delete button
        keyboard = [[
            InlineKeyboardButton("🗑", callback_data="confirm_delete_all_data")
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        try:
            query.edit_message_text(text=msg,
                                    parse_mode='Markdown',
                                    reply_markup=reply_markup)
        except Exception as edit_error:
            error_msg = str(edit_error).lower()
            if "message is not modified" in error_msg:
                # Message content is identical, just skip silently
                pass
            else:
                logger.error(f"Error editing stats message: {edit_error}")
                query.edit_message_text("❌ Error returning to stats view.")

    except Exception as e:
        logger.error(f"Error returning to stats: {e}")
        query.edit_message_text("❌ Error returning to stats view.")


def safe_send_message(context,
                      chat_id,
                      text,
                      parse_mode=None,
                      reply_markup=None):
    """
    Send a message, handling potential block by the user.
    Returns True if message was sent, None if user blocked the bot.
    """
    try:
        return context.bot.send_message(chat_id=chat_id,
                                        text=text,
                                        parse_mode=parse_mode,
                                        reply_markup=reply_markup)
    except Exception as e:
        error_msg = str(e).lower()
        if any(keyword in error_msg for keyword in [
                "blocked", "deactivated", "user is deactivated",
                "bot was blocked", "forbidden", "chat not found"
        ]):
            logger.warning(
                f"User {chat_id} has blocked the bot. Error: {error_msg}")

            # Mark user as blocked in database
            try:
                # Check if user was previously not blocked
                user_doc = user_stats_col.find_one({'user_id': chat_id})
                was_blocked = user_doc.get('is_blocked',
                                           False) if user_doc else False

                # Update user as blocked
                user_stats_col.update_one(
                    {'user_id': chat_id},
                    {
                        '$set': {
                            'is_blocked': True,
                            'blocked_date': datetime.now(),
                            'blocked_by_user':
                            True  # Flag to indicate user blocked the bot
                        }
                    },
                    upsert=True)

                # Update global counts only if user wasn't already marked as blocked
                if not was_blocked:
                    user_stats_col.update_one(
                        {'_id': 'global_stats'},
                        {
                            '$inc': {
                                'blocked_users': 1,
                                'total_users':
                                -1  # Remove from total user count when blocked
                            }
                        },
                        upsert=True)
                    logger.info(
                        f"User {chat_id} automatically marked as blocked and removed from total users"
                    )

            except Exception as db_error:
                logger.error(
                    f"Error updating blocked status for user {chat_id}: {db_error}"
                )

            return None
        else:
            logger.error(f"Error sending message to {chat_id}: {e}")
            return None


# MAIN FUNCTION


def main():
    """
    Main function to start the bot
    """
    try:
        # Create updater and dispatcher with conflict resolution
        updater = Updater(BOT_TOKEN, use_context=True)
        dp = updater.dispatcher

        # Aggressive conflict resolution
        try:
            # Force delete webhook and clear updates
            updater.bot.delete_webhook(drop_pending_updates=True)
            logger.info("Webhook cleared with pending updates dropped")
            
            # Multiple attempts to clear updates
            for attempt in range(3):
                try:
                    updates = updater.bot.get_updates(timeout=2, allowed_updates=[])
                    if updates:
                        last_update_id = updates[-1].update_id
                        updater.bot.get_updates(offset=last_update_id + 1, timeout=1)
                        logger.info(f"Attempt {attempt + 1}: Cleared {len(updates)} pending updates")
                    else:
                        logger.info(f"Attempt {attempt + 1}: No pending updates found")
                        break
                except Exception as inner_e:
                    logger.warning(f"Attempt {attempt + 1} failed: {inner_e}")
                    if attempt < 2:
                        import time
                        time.sleep(1)
                        
        except Exception as e:
            logger.warning(f"Could not clear pending updates/webhooks: {e}")
            
        # Extended delay for cleanup
        import time
        time.sleep(3)

        # Initialize bot data
        if 'pending_wallets' not in dp.bot_data:
            dp.bot_data['pending_wallets'] = {}
        if 'digits_message_id' not in dp.bot_data:
            dp.bot_data['digits_message_id'] = {}

        # Conversation handler for update command with proper state management
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('update', update_cmd)],
            states={
                MODE_SELECT:
                [MessageHandler(Filters.text & ~Filters.command, handle_mode)],
                SINGLE_UID: [
                    MessageHandler(Filters.text & ~Filters.command,
                                   handle_single_uid),
                    CommandHandler('done', handle_single_uid)
                ],
                BULK_IMG: [
                    MessageHandler(Filters.photo, handle_bulk_images),
                    MessageHandler(Filters.text & ~Filters.command,
                                   handle_bulk_images),
                    CommandHandler('done', handle_bulk_images)
                ]
            },
            fallbacks=[
                CommandHandler('cancel', cancel_conversation),
                CommandHandler('done', cancel_conversation),
                CommandHandler('start', cancel_conversation),
                CommandHandler('stats', cancel_conversation),
                CommandHandler(
                    'update', cancel_conversation
                )  # Handle new update command during conversation
            ],
            persistent=False,
            name="update_conversation",
            per_chat=True,
            per_user=True,
            per_message=False)

        # Add handlers
        dp.add_handler(CommandHandler("start", start))
        dp.add_handler(CommandHandler("claim", claim_command))
        dp.add_handler(CommandHandler("stats", stats))
        dp.add_handler(CommandHandler("verified", verified))
        dp.add_handler(CommandHandler("nonverified", nonverified))
        dp.add_handler(CommandHandler("all", all_uids))
        dp.add_handler(CommandHandler("dustbin", dustbin))
        dp.add_handler(CommandHandler("del", del_command))
        dp.add_handler(CommandHandler("done", done_command))
        dp.add_handler(CommandHandler("reject", reject_command))
        dp.add_handler(CommandHandler("newcode", newcode_command))
        dp.add_handler(CommandHandler("block", block_user_command))
        dp.add_handler(CommandHandler("unblock", block_user_command))
        dp.add_handler(CommandHandler("checkblocked", check_blocked_command))
        dp.add_handler(CommandHandler("restrict", restrict_command))
        dp.add_handler(CommandHandler("cast", cast_command))
        dp.add_handler(
            CallbackQueryHandler(handle_screenshot_button,
                                 pattern="send_screenshot"))
        dp.add_handler(
            CallbackQueryHandler(handle_bonus_button, pattern="bonus"))
        dp.add_handler(
            CallbackQueryHandler(handle_gift_codes_button,
                                 pattern="gift_codes"))
        dp.add_handler(
            CallbackQueryHandler(handle_verify_membership,
                                 pattern="verify_membership"))
        dp.add_handler(
            CallbackQueryHandler(handle_unlock_gift_code,
                                 pattern="unlock_gift_code"))
        dp.add_handler(CallbackQueryHandler(handle_back_button,
                                            pattern="back"))
        # Add handler for prediction button
        dp.add_handler(
            CallbackQueryHandler(handle_prediction_button,
                                 pattern="prediction"))
        dp.add_handler(
            CallbackQueryHandler(handle_manual_prediction_button,
                                 pattern="manual_prediction"))
        dp.add_handler(
            CallbackQueryHandler(handle_auto_prediction_button,
                                 pattern="auto_prediction"))
        dp.add_handler(
            CallbackQueryHandler(handle_next_auto_prediction,
                                 pattern="next_auto_prediction"))
        dp.add_handler(
            CallbackQueryHandler(handle_support_button, pattern="support"))
        # Add the three missing callback query handlers
        dp.add_handler(
            CallbackQueryHandler(prediction_menu_handler,
                                 pattern="prediction_menu"))
        dp.add_handler(
            CallbackQueryHandler(wingo_menu_handler, pattern="wingo_menu"))
        dp.add_handler(
            CallbackQueryHandler(aviator_menu_handler, pattern="aviator_menu"))
        dp.add_handler(
            CallbackQueryHandler(mines_menu_handler, pattern="mines_menu"))
        dp.add_handler(
            CallbackQueryHandler(dragon_tiger_menu_handler,
                                 pattern="dragon_tiger_menu"))
        dp.add_handler(
            CallbackQueryHandler(handle_aviator_signals_button,
                                 pattern="aviator_signals"))
        dp.add_handler(
            CallbackQueryHandler(handle_confirm_delete_all_data,
                                 pattern="confirm_delete_all_data"))
        dp.add_handler(
            CallbackQueryHandler(handle_delete_all_data_yes,
                                 pattern="delete_all_data_yes"))
        dp.add_handler(
            CallbackQueryHandler(handle_delete_all_data_no,
                                 pattern="delete_all_data_no"))
        dp.add_handler(conv_handler)
        dp.add_handler(MessageHandler(Filters.all, handle_all))

        # Error handler with conflict detection
        def error_handler(update, context):
            error_msg = str(context.error)
            if "Conflict" in error_msg and "getUpdates" in error_msg:
                logger.error(
                    "Bot conflict detected - another instance may be running")
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