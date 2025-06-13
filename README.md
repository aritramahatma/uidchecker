UIDChecker Telegram Bot – Setup & Admin Guide
uidchecker is a Telegram bot that verifies gaming UIDs using screenshots, detects fakes with AI, manages users, and handles gift code claims.

GitHub Repo: https://github.com/aritramahatma/uidchecker

1. Quick Setup (Replit)
Step 1: Fork or Import

Open Replit

Import the repo: https://github.com/aritramahatma/uidchecker

Step 2: Click "Run"

This auto-installs dependencies and fixes broken packages

Step 3: Add Secrets
Go to Replit > Secrets and add the following:

BOT_TOKEN = Your Telegram bot token

ADMIN_UID = Your Telegram numeric user ID

GEMINI_API_KEY = Your Gemini Vision API key

2. VPS Setup (Contabo / DigitalOcean)
Requirements:

Ubuntu 20.04+ server

Python 3.8+

Git installed

Installation Steps:

bash
Copy
Edit
# Connect to VPS
ssh root@your-vps-ip

# Update packages
apt update && apt upgrade -y

# Install Python, Git
apt install git python3-pip python3-venv -y

# Clone the repo
git clone https://github.com/aritramahatma/uidchecker.git
cd uidchecker

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install requirements
pip install -r requirements.txt

# Fix dependencies (optional)
python setup_dependencies.py

# Set environment variables temporarily
export BOT_TOKEN='your_bot_token'
export ADMIN_UID='your_admin_uid'
export GEMINI_API_KEY='your_gemini_api_key'

# Run the bot
python main.py
To keep the bot running in background:

bash
Copy
Edit
nohup python main.py &
3. User Commands
/start – Shows welcome message and verification steps

/claim – Claim gift code (only for verified users)

4. Admin Commands (for ADMIN_UID only)
Statistics & Reports

/stats – Total users, verified, blocked, pending, balance checks

UID Management

/update – Add UIDs manually or by image

/done – Finalize the update and notify users

/verified – List of all verified UIDs

/nonverified – List of non-verified UIDs

/all – Show all UIDs with status

User Management

/block <user_id> – Block a user

/unblock <user_id> – Unblock a user

/checkblocked – Scan for users who blocked the bot

/reject – Reject non-verified users and delete their data

Data Cleanup

/dustbin <uid1,uid2,...> – Delete specific UIDs

/del <number> – Delete UIDs from last N extractions

Gift Code Management

/newcode <code> – Set and broadcast new gift code

System Controls

/restrict on or /restrict off – Toggle verification lock

/cast <message> – Broadcast to all users (text, images, videos)

Admin Controls

/addadmin <user_id> – Add new admin

/removeadmin <user_id> – Remove an admin

/listadmins – List all admins

5. Verification Process
User sends a 6–12 digit UID

Uploads screenshot of profile

AI checks image (real/fake and UID match)

Optionally checks wallet balance (min ₹100)

If verified, user gains access to all features

6. Features Summary
Google Gemini Vision API for fake screenshot detection

MongoDB database for storing UIDs and user data

Image-based UID extraction (OCR)

Broadcast support

Anti-fraud and block check system

Channel join verification support (optional)
