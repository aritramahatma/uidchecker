
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

## Support

If you still face issues, the setup script provides detailed logs to help debug the problem.
