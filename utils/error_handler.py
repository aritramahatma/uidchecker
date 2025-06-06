
"""
Comprehensive error handling utilities for the Telegram bot
"""
import logging
import traceback
from datetime import datetime
from functools import wraps
from telegram import Update
from telegram.ext import CallbackContext
from telegram.error import (
    TelegramError, NetworkError, BadRequest, TimedOut, 
    ChatMigrated, RetryAfter, Unauthorized, Conflict
)

logger = logging.getLogger(__name__)


def handle_telegram_errors(func):
    """Decorator to handle common Telegram API errors"""
    @wraps(func)
    def wrapper(update: Update, context: CallbackContext, *args, **kwargs):
        try:
            return func(update, context, *args, **kwargs)
        except Unauthorized as e:
            logger.warning(f"Bot was blocked by user {update.effective_user.id if update.effective_user else 'Unknown'}: {e}")
            # Don't send error message as user blocked the bot
            return None
        except BadRequest as e:
            error_msg = str(e).lower()
            if "message is not modified" in error_msg:
                # Silently ignore message not modified errors
                return None
            elif "chat not found" in error_msg:
                logger.warning(f"Chat not found: {e}")
                return None
            elif "message to edit not found" in error_msg:
                logger.warning(f"Message to edit not found: {e}")
                return None
            else:
                logger.error(f"Bad request error in {func.__name__}: {e}")
                safe_reply(update, "❌ Invalid request. Please try again.")
        except RetryAfter as e:
            logger.warning(f"Rate limited, retry after {e.retry_after} seconds")
            safe_reply(update, f"⏳ Too many requests. Please wait {e.retry_after} seconds and try again.")
        except TimedOut as e:
            logger.error(f"Request timed out in {func.__name__}: {e}")
            safe_reply(update, "⏱️ Request timed out. Please try again.")
        except NetworkError as e:
            logger.error(f"Network error in {func.__name__}: {e}")
            safe_reply(update, "🌐 Network error. Please check your connection and try again.")
        except ChatMigrated as e:
            logger.info(f"Chat migrated to {e.new_chat_id}")
            # Handle chat migration if needed
        except Conflict as e:
            logger.error(f"Bot conflict detected in {func.__name__}: {e}")
            safe_reply(update, "⚠️ Bot conflict detected. Please try again in a moment.")
        except TelegramError as e:
            logger.error(f"Telegram error in {func.__name__}: {e}")
            safe_reply(update, "❌ Telegram service error. Please try again later.")
        except Exception as e:
            logger.error(f"Unexpected error in {func.__name__}: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            safe_reply(update, "❌ An unexpected error occurred. Please try again.")
        return None
    return wrapper


def handle_database_errors(func):
    """Decorator to handle database-related errors"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                error_msg = str(e).lower()
                if any(keyword in error_msg for keyword in [
                    "connection", "timeout", "network", "unreachable"
                ]):
                    retry_count += 1
                    if retry_count < max_retries:
                        logger.warning(f"Database connection issue (attempt {retry_count}), retrying: {e}")
                        import time
                        time.sleep(1)
                        continue
                    else:
                        logger.error(f"Database connection failed after {max_retries} attempts: {e}")
                        raise DatabaseConnectionError(f"Database unavailable after {max_retries} attempts")
                else:
                    logger.error(f"Database error in {func.__name__}: {e}")
                    raise DatabaseOperationError(f"Database operation failed: {e}")
        return None
    return wrapper


def handle_api_errors(func):
    """Decorator to handle external API errors (Gemini, etc.)"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            error_msg = str(e).lower()
            if any(keyword in error_msg for keyword in [
                "timeout", "connection", "network", "503", "502", "500"
            ]):
                logger.error(f"API service unavailable in {func.__name__}: {e}")
                raise APIServiceError("External service temporarily unavailable")
            elif "quota" in error_msg or "rate limit" in error_msg:
                logger.error(f"API quota exceeded in {func.__name__}: {e}")
                raise APIQuotaError("API quota exceeded")
            elif "authentication" in error_msg or "unauthorized" in error_msg:
                logger.error(f"API authentication error in {func.__name__}: {e}")
                raise APIAuthError("API authentication failed")
            else:
                logger.error(f"API error in {func.__name__}: {e}")
                raise APIError(f"API operation failed: {e}")
    return wrapper


def safe_reply(update: Update, message: str, parse_mode=None, reply_markup=None):
    """Safely send a reply message with error handling"""
    if not update or not update.effective_message:
        return None
        
    try:
        return update.effective_message.reply_text(
            text=message,
            parse_mode=parse_mode,
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"Failed to send reply: {e}")
        return None


def safe_edit_message(query, text=None, caption=None, parse_mode=None, reply_markup=None, media=None):
    """Safely edit a message with error handling"""
    try:
        if media:
            return query.edit_message_media(
                media=media,
                reply_markup=reply_markup
            )
        elif caption:
            return query.edit_message_caption(
                caption=caption,
                parse_mode=parse_mode,
                reply_markup=reply_markup
            )
        else:
            return query.edit_message_text(
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup
            )
    except Exception as e:
        error_msg = str(e).lower()
        if "message is not modified" in error_msg:
            # Silently ignore - message content is identical
            return None
        elif "message to edit not found" in error_msg:
            logger.warning(f"Message to edit not found: {e}")
            return None
        else:
            logger.error(f"Failed to edit message: {e}")
            return None


def safe_send_photo(update: Update, photo, caption=None, parse_mode=None, reply_markup=None):
    """Safely send a photo with error handling"""
    try:
        return update.effective_message.reply_photo(
            photo=photo,
            caption=caption,
            parse_mode=parse_mode,
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"Failed to send photo: {e}")
        # Fallback to text message
        return safe_reply(update, caption or "Photo unavailable", parse_mode, reply_markup)


def global_error_handler(update: Update, context: CallbackContext):
    """Global error handler for the bot"""
    error = context.error
    
    # Log the error with context
    logger.error(f"Global error handler caught: {error}")
    logger.error(f"Update: {update}")
    logger.error(f"Traceback: {traceback.format_exc()}")
    
    # Handle specific error types
    if isinstance(error, Unauthorized):
        logger.warning("Bot was blocked by a user or chat")
        return
    elif isinstance(error, BadRequest):
        logger.warning(f"Bad request: {error}")
        return
    elif isinstance(error, TimedOut):
        logger.warning("Request timed out")
        return
    elif isinstance(error, NetworkError):
        logger.warning(f"Network error: {error}")
        return
    elif isinstance(error, Conflict):
        logger.error("Bot conflict - another instance may be running")
        return
    
    # Send error notification to user if possible
    try:
        if update and update.effective_message:
            safe_reply(
                update,
                "❌ An unexpected error occurred. Our team has been notified. Please try again later."
            )
    except Exception as e:
        logger.error(f"Failed to send error message to user: {e}")
    
    # Send error notification to admin
    try:
        from config import ADMIN_UID
        error_details = (
            f"🚨 *Bot Error Alert*\n\n"
            f"*Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"*Error:* `{str(error)[:200]}`\n"
            f"*User:* {update.effective_user.id if update and update.effective_user else 'Unknown'}\n"
            f"*Update:* {str(update)[:300] if update else 'None'}"
        )
        
        context.bot.send_message(
            chat_id=ADMIN_UID,
            text=error_details,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Failed to notify admin about error: {e}")


# Custom Exception Classes
class BotError(Exception):
    """Base exception for bot-related errors"""
    pass


class DatabaseConnectionError(BotError):
    """Raised when database connection fails"""
    pass


class DatabaseOperationError(BotError):
    """Raised when database operation fails"""
    pass


class APIError(BotError):
    """Base exception for API-related errors"""
    pass


class APIServiceError(APIError):
    """Raised when external API service is unavailable"""
    pass


class APIQuotaError(APIError):
    """Raised when API quota is exceeded"""
    pass


class APIAuthError(APIError):
    """Raised when API authentication fails"""
    pass


class UserInputError(BotError):
    """Raised when user input is invalid"""
    pass


class ValidationError(BotError):
    """Raised when data validation fails"""
    pass
