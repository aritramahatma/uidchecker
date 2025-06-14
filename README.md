
# 🤖 UIDChecker Telegram Bot

A powerful Telegram bot that verifies gaming UIDs using AI-powered screenshot analysis, detects fake submissions, manages users, and handles gift code distribution with advanced fraud detection.

## 🌟 Features

- **AI-Powered Verification**: Uses Google Gemini Vision API to detect fake screenshots
- **UID Extraction**: OCR-based UID extraction from profile screenshots
- **User Management**: Block/unblock users, track statistics
- **Gift Code System**: Secure gift code distribution to verified users
- **Broadcast System**: Send messages, images, and videos to all users
- **Anti-Fraud Protection**: Advanced detection and prevention systems
- **MongoDB Integration**: Reliable data storage and management
- **Admin Panel**: Comprehensive admin controls and statistics

## 🚀 Quick Setup on Replit

### Step 1: Fork the Repository
1. Open [Replit](https://replit.com)
2. Click "Import from GitHub"
3. Enter repository URL: `https://github.com/aritramahatma/uidchecker`
4. Click "Import"

### Step 2: Configure Environment Variables
1. Go to **Secrets** tab in your Replit
2. Add the following secrets:

| Secret Name | Description | Required |
|-------------|-------------|----------|
| `BOT_TOKEN` | Your Telegram bot token from @BotFather | ✅ |
| `ADMIN_UID` | Your Telegram numeric user ID | ✅ |
| `GEMINI_API_KEY` | Google Gemini Vision API key | ✅ |

### Step 3: Run the Bot
1. Click the **"Run"** button
2. Wait for dependencies to install automatically
3. Bot will start and show connection status

## 🔑 Getting Required Tokens

### Telegram Bot Token
1. Open Telegram and search for [@BotFather](https://t.me/botfather)
2. Send `/newbot` command
3. Follow instructions to create your bot
4. Copy the provided token

### Your Telegram User ID
1. Search for [@userinfobot](https://t.me/userinfobot) on Telegram
2. Send `/start` command
3. Copy your numeric user ID

### Google Gemini API Key
1. Visit [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Create a new API key
3. Copy the generated key

## 📱 User Commands

| Command | Description |
|---------|-------------|
| `/start` | Initialize bot and show welcome message |
| `/claim` | Claim gift codes (verified users only) |

## 👑 Admin Commands

### 📊 Statistics & Reports
- `/stats` - View total users, verified count, blocked users, and balance statistics

### 🔧 UID Management
- `/update` - Add UIDs manually or by uploading images
- `/done` - Finalize UID updates and notify users
- `/verified` - List all verified UIDs
- `/nonverified` - List non-verified UIDs
- `/all` - Show all UIDs with their verification status

### 👥 User Management
- `/block <user_id>` - Block a specific user
- `/unblock <user_id>` - Unblock a user
- `/checkblocked` - Scan for users who blocked the bot
- `/reject` - Remove non-verified users and delete their data

### 🗑️ Data Management
- `/dustbin <uid1,uid2,...>` - Delete specific UIDs (comma-separated)
- `/del <number>` - Delete UIDs from last N extractions

### 🎁 Gift Code Management
- `/newcode <code>` - Set new gift code and broadcast to all users

### 🔒 System Controls
- `/restrict on` or `/restrict off` - Toggle verification lock
- `/cast <message>` - Broadcast messages to all users (supports text, images, videos)

### 👨‍💼 Admin Controls
- `/addadmin <user_id>` - Add new administrator
- `/removeadmin <user_id>` - Remove administrator privileges
- `/listadmins` - Display all current administrators

## 🔍 Verification Process

1. **UID Submission**: User sends a 6-12 digit gaming UID
2. **Screenshot Upload**: User uploads profile screenshot
3. **AI Analysis**: Google Gemini Vision API analyzes image for:
   - Screenshot authenticity (real vs fake)
   - UID matching verification
4. **Balance Check** (Optional): Verify minimum wallet balance (₹100)
5. **Verification**: If all checks pass, user gains full access

## 🛠️ Technical Stack

- **Language**: Python 3.11+
- **Framework**: python-telegram-bot 13.15
- **Database**: MongoDB
- **AI Vision**: Google Gemini Vision API
- **Image Processing**: Pillow (PIL)
- **Hosting**: Replit (recommended)

## 📁 Project Structure

```
uidchecker/
├── handlers/           # Command and callback handlers
│   ├── admin.py       # Admin command handlers
│   ├── callbacks.py   # Inline keyboard callbacks
│   ├── commands.py    # User command handlers
│   └── messages.py    # Message processing
├── services/          # Core services
│   ├── database.py    # MongoDB operations
│   ├── gemini.py      # AI vision processing
│   └── predictions.py # Prediction algorithms
├── utils/             # Utility functions
│   ├── error_handler.py
│   ├── helpers.py
│   └── validators.py
├── main.py           # Main bot application
├── config.py         # Configuration settings
└── requirements.txt  # Python dependencies
```

## 🔧 Configuration

The bot uses environment variables for configuration. All settings are managed through Replit Secrets:

```python
# Core Configuration
BOT_TOKEN = "your_telegram_bot_token"
ADMIN_UID = "your_telegram_user_id"
GEMINI_API_KEY = "your_gemini_api_key"

# Optional Settings (configured in code)
MIN_BALANCE = 100  # Minimum wallet balance for verification
MAX_UID_LENGTH = 12  # Maximum UID length
MIN_UID_LENGTH = 6   # Minimum UID length
```

## 🚨 Troubleshooting

### Common Issues

**Bot not responding:**
- Check if BOT_TOKEN is correct
- Verify bot is not blocked by Telegram
- Check Replit console for error messages

**AI verification failing:**
- Ensure GEMINI_API_KEY is valid
- Check API quota limits
- Verify image format is supported

**Database connection issues:**
- MongoDB connection is automatically handled
- Check console logs for connection status

### Debug Commands

Run the test script to verify all components:
```bash
python test_bot.py
```

## 📋 Requirements

- Python 3.11+
- Valid Telegram Bot Token
- Google Gemini API Key
- Internet connection
- Replit account (for easy hosting)

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📄 License

This project is open source. Feel free to use and modify according to your needs.

## 🆘 Support

For support and questions:
- GitHub Issues: [Create an issue](https://github.com/aritramahatma/uidchecker/issues)
- Telegram: Contact the bot administrator

## 🔗 Links

- **GitHub Repository**: https://github.com/aritramahatma/uidchecker
- **Replit Template**: Fork and run instantly on Replit
- **Demo Bot**: Contact repository owner for demo access

---

**⚠️ Important**: Keep your API keys secure and never share them publicly. Use Replit Secrets for secure environment variable management.
