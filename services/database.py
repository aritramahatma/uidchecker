
"""
Database service for MongoDB operations
"""
import logging
from datetime import datetime
from pymongo import MongoClient
from config import MONGO_URI

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


def get_current_gift_code():
    """Get the current gift code from database"""
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
