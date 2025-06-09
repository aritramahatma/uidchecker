
"""
Validation utilities for the Telegram bot
"""
import re
import logging
from datetime import datetime
from services.database import uids_col, ensure_db_connection
from services.gemini import gemini_ocr, detect_fake_screenshot
from config import restrict_mode, ADMIN_UID

logger = logging.getLogger(__name__)


def check_uid(update, context, uid, user_id, username):
    """Check if UID exists in database and update user info with restriction mode logic"""
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
                        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
                        
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


def handle_wallet(update, context):
    """Process wallet screenshot for balance verification with fake detection"""
    from services.gemini import detect_fake_screenshot, gemini_ocr
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    
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
        try:
            analysis_sticker = update.message.reply_sticker(
                sticker=
                "CAACAgIAAxkBAAEOoRVoPrSHoQhhqqrZb_-cEVCEudhKWgACVgADDbbSGdwzoZ8qLZ2yNgQ"
            )
        except Exception as e:
            logger.error(f"Error sending sticker: {e}")

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

        # Use enhanced extraction function
        from services.gemini import extract_uid_and_balance, analyze_screenshot_quality
        
        # Analyze screenshot quality
        quality_score, quality_issues = analyze_screenshot_quality(img_bytes)
        
        if quality_score < 50:
            update.message.reply_text(
                f"⚠️ *Screenshot Quality Issues Detected*\n\n"
                f"Quality Score: {quality_score}/100\n"
                f"Issues: {', '.join(quality_issues)}\n\n"
                f"*Please send a clearer, higher quality screenshot*",
                parse_mode='Markdown'
            )
            return
        
        # Extract data using enhanced function
        extracted_data = extract_uid_and_balance(extracted_text)
        balance = extracted_data['balance']
        matched_uid = extracted_data['uid']

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
