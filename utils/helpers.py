
"""
Helper utilities for the Telegram bot
"""
import logging
from datetime import datetime
from services.database import user_stats_col

logger = logging.getLogger(__name__)


def safe_send_message(context, chat_id, text, parse_mode=None, reply_markup=None):
    """Send a message, handling potential block by the user."""
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
