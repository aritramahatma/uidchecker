"""
Helper utilities for the Telegram bot
"""
import logging
from datetime import datetime
from services.database import user_stats_col
from telegram.error import Unauthorized, BadRequest, TimedOut

logger = logging.getLogger(__name__)


def safe_send_message(context, chat_id, text, parse_mode='Markdown', reply_markup=None, **kwargs):
    """
    Safely send a message with error handling
    Returns message object if successful, None if failed
    """
    try:
        message = context.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
            disable_web_page_preview=True,  # Prevent link previews
            **kwargs
        )
        logger.debug(f"Message sent successfully to {chat_id}")
        return message
    except Unauthorized:
        # User blocked the bot
        logger.warning(f"User {chat_id} has blocked the bot - cannot send message")
        return None
    except BadRequest as e:
        if "chat not found" in str(e).lower():
            logger.warning(f"Chat {chat_id} not found - user may have deleted account")
        elif "message is too long" in str(e).lower():
            logger.error(f"Message too long for {chat_id}: {len(text)} characters")
        else:
            logger.error(f"Bad request when sending to {chat_id}: {e}")
        return None
    except TimedOut:
        logger.warning(f"Timeout when sending message to {chat_id}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error sending message to {chat_id}: {e}")
        return None


def broadcast_gift_code_notification(context, new_code: str):
    """Broadcast gift code notification to all users"""
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