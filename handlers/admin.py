
"""
Admin command handlers for the Telegram bot
"""
import logging
import re
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, ConversationHandler
from services.database import (uids_col, gift_codes_col, user_stats_col, 
                               get_user_activity_stats, check_blocked_users)
from services.gemini import gemini_ocr
from utils.helpers import safe_send_message, broadcast_gift_code_notification
from config import ADMIN_UID, MODE_SELECT, SINGLE_UID, BULK_IMG, last_extractions, restrict_mode

logger = logging.getLogger(__name__)


def stats(update: Update, context: CallbackContext):
    """Show comprehensive user activity report (Admin only)"""
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


def update_cmd(update: Update, context: CallbackContext):
    """Start dual mode update conversation (Admin only)"""
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
    """Handle mode selection in update conversation"""
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
    """Handle single UID update"""
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
    """Handle bulk image processing for UID extraction"""
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


def check_newly_verified_uids(update: Update, context: CallbackContext):
    """Check for UIDs that became verified after admin updates and notify users"""
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


# Additional admin commands would go here...
def newcode_command(update: Update, context: CallbackContext):
    """Update gift code (Admin only)"""
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


def cancel_conversation(update: Update, context: CallbackContext):
    """Cancel any ongoing conversation"""
    logger.info(
        f"Conversation cancelled by user {update.message.from_user.id}")
    update.message.reply_text("❌ Operation cancelled.",
                              reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END
