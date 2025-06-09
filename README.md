
# Telegram Bot Setup Guide

## Quick Start (For New Users)

1. **Clone this project to your Replit account**
2. **Click the RUN button** - it will automatically fix all dependencies
3. **Add your environment variables** in Secrets:
   - `BOT_TOKEN`: Your Telegram bot token
   - `ADMIN_UID`: Your Telegram user ID
   - `GEMINI_API_KEY`: Your Gemini API key

## Manual Setup (If needed)

If you face any dependency issues, run this command in Shell:

```bash
python setup_dependencies.py
```

This script will:
- Remove conflicting telegram packages
- Install the correct `python-telegram-bot==13.15`
- Verify the installation
- Install all other dependencies

## Common Issues Fixed

✅ **ImportError: cannot import name 'Update' from 'telegram'**
- Automatically removes wrong `telegram` package (v0.0.1)
- Installs correct `python-telegram-bot==13.15`

✅ **Package conflicts**
- Clears pip cache
- Force reinstalls with correct versions

✅ **Dependency management**
- Handles both requirements.txt and pyproject.toml

## Running the Bot

After setup, your bot will start automatically. You can also use these workflows:
- **Setup and Run Bot** (recommended)
- **Run Telegram Bot**

## Bot Commands & Functions

### **User Commands**
- **`/start`** - Welcome message with registration link and verification options
- **`/claim`** - Access gift codes (requires full verification)

### **Admin Commands** (Only for ADMIN_UID: 6490401448)

#### **Statistics & Monitoring**
- **`/stats`** - Comprehensive user activity report showing:
  - Total bot users
  - Blocked users (admin blocked vs user blocked)
  - Verified UIDs
  - Fully verified users
  - Non-verified users
  - Admin updated UIDs
  - Pending wallet verifications
  - Users with valid balance
  - Verification rate percentage

#### **UID Management**
- **`/update`** - Dual mode UID management system:
  - **Single UID Mode**: Add UIDs one by one (6-12 digits)
  - **Bulk Screenshot Mode**: Extract UIDs from images using AI OCR
  - Type `/done` to finish either mode

- **`/verified`** - Show all verified UIDs with usernames and balances
- **`/nonverified`** - Show all non-verified UIDs
- **`/all`** - Show all UIDs in database with verification status

#### **User Management**
- **`/done`** - Check for newly verified UIDs and notify users
- **`/reject`** - Send rejection messages to all non-verified users and auto-delete their UIDs
- **`/block <user_id>`** - Block a specific user from using the bot
- **`/unblock <user_id>`** - Unblock a previously blocked user
- **`/checkblocked`** - Check for users who have blocked the bot and update stats

#### **Data Management**
- **`/dustbin <uid1,uid2,uid3>`** - Delete specific UIDs from database
  - Example: `/dustbin 123456,789012,345678`
- **`/del <number>`** - Delete UIDs from last bulk extractions
  - Example: `/del 2` (deletes UIDs from last 2 extractions)

#### **Gift Code Management**
- **`/newcode <gift_code>`** - Update the daily gift code:
  - Deactivates old codes
  - Sets new active code
  - Broadcasts notification to all users
  - Example: `/newcode ABC123XYZ789`

#### **System Controls**
- **`/restrict on/off`** - Toggle global restriction mode for UID verification
- **`/cast <message>`** - Broadcast message to all users (supports text, photos, videos, stickers, etc.)

#### **Admin Management** (Primary Admin Only)
- **`/addadmin <user_id>`** - Add a new admin to the bot
  - Example: `/addadmin 123456789`
- **`/removeadmin <user_id>`** - Remove an admin from the bot
  - Example: `/removeadmin 123456789`
- **`/listadmins`** - Show all current bot admins with their roles

### **Interactive Features**

#### **Game Predictions** (For verified users)
- **Wingo** - 1-minute color/number predictions (Manual & Auto modes)
- **Aviator** - Multiplier signal predictions
- **Mines Pro** - Safe tile position predictions
- **Dragon Tiger** - Card game predictions

#### **Callback Button Functions**
- **Send Screenshot** - Start UID verification process
- **Prediction** - Access game prediction menu
- **Gift Codes** - Join channels to unlock gift codes
- **Get Hack** - Access bonus/hack features
- **Support** - Contact official support bot
- **Unlock Gift Code** - Verify channel membership and get gift codes

### **Verification Process**
1. **UID Submission** - Users send 6-12 digit gaming platform UID
2. **Screenshot Analysis** - AI-powered fake detection using Google Gemini
3. **Wallet Verification** - Minimum ₹100 balance check
4. **Full Verification** - Access to all premium features

### **System Capabilities**
- **MongoDB Integration** - Stores all user data and statistics
- **AI Screenshot Analysis** - Detects edited/fake images
- **Auto User Management** - Tracks blocked users and activity
- **Broadcast System** - Mass notifications for gift codes
- **Anti-Fraud Protection** - Multiple verification layers
- **Real-time Predictions** - Period-based gaming predictions
- **Channel Membership Verification** - Must join 4 Telegram channels for rewards

## Support

If you still face issues, the setup script provides detailed logs to help debug the problem.
