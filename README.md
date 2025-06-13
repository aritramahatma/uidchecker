[https://chatgpt.com/c/684be915-7270-8008-a6c5-6ab2c76f7c9b#:~:text=Notepad%20without%20issues%3A-,UIDChecker%20Telegram%20Bot%20%E2%80%93%20Setup%20%26%20Admin%20Guide,Channel%20join%20verification%20support%20(optional),-Need%20Help%3F#📘 UIDChecker Telegram Bot – Setup & Admin Guide
uidchecker is a powerful Telegram bot for verifying gaming UIDs through screenshots using AI, managing users, gift code claims, and more. It supports image-based UID scanning, wallet proof, and complete admin control.

GitHub Repo: github.com/aritramahatma/uidchecker

#🚀 Quick Setup (Replit Recommended)
Step 1: Fork & Open
Go to Replit

Import the repo:
https://github.com/aritramahatma/uidchecker

Step 2: Click Run
Replit will:

Install all Python dependencies

Auto-correct any broken Telegram packages

Step 3: Add Secrets
Click the "lock" icon on the left side (Secrets/Environment Variables), and add:

Key	Value
BOT_TOKEN	Your bot token from @BotFather
ADMIN_UID	Your Telegram numeric user ID
GEMINI_API_KEY	Your Google Gemini Vision API key

#🖥️ VPS Deployment Guide (Contabo/DigitalOcean/Any Ubuntu Server)
✅ Requirements
Ubuntu 20.04+ VPS

Python 3.8+

Git installed

SSH access

#📦 VPS Installation Steps
bash
Copy
Edit
# 1. Connect to VPS
ssh root@your-vps-ip

# 2. Update system
apt update && apt upgrade -y

# 3. Install dependencies
apt install git python3-pip python3-venv -y

# 4. Clone your repo
git clone https://github.com/aritramahatma/uidchecker.git
cd uidchecker

# 5. Create virtual environment (optional)
python3 -m venv venv
source venv/bin/activate

# 6. Install required packages
pip install -r requirements.txt

# 7. Fix dependency issues (if any)
python setup_dependencies.py

# 8. Set environment variables (temporary method)
export BOT_TOKEN='your_bot_token'
export ADMIN_UID='your_admin_uid'
export GEMINI_API_KEY='your_gemini_api_key'

# 9. Start the bot
python main.py
✅ To keep bot running in background:

bash
Copy
Edit
nohup python main.py &
🔁 To run bot on boot, use systemd (ask me if you want the service file).

🤖 Bot Command Reference
🔓 User Commands
/start – Welcome + begin verification

/claim – Claim gift code (if fully verified)

🔐 Admin Commands (ADMIN_UID only)
📊 Analytics
/stats – Total users, UID stats, verification %

🧾 UID Tools
/update – Add UIDs (manual or screenshot via OCR)

/done – Finalize UID update and notify users

/verified – Show verified UIDs

/nonverified – Show non-verified UIDs

/all – Show all UIDs in DB

👥 User Management
/block <user_id> – Block user

/unblock <user_id> – Unblock user

/checkblocked – Find users who blocked bot

/reject – Reject all non-verified users

🧹 UID Cleanup
/dustbin 123456,654321,... – Delete selected UIDs

/del 2 – Delete last 2 bulk extracted UID batches

🎁 Gift Code Control
/newcode ABC123XYZ – Set new gift code and broadcast

📢 Broadcast & Restrictions
/cast <msg> – Broadcast message to all users

/restrict on/off – Enable or disable UID verification globally

👑 Admin Roles
/addadmin <user_id> – Add admin

/removeadmin <user_id> – Remove admin

/listadmins – Show all admins

🧠 Verification Flow (AI + Manual)
User sends UID (6–12 digits)

User uploads screenshot of game profile

AI (Gemini Vision) checks if image is:

Real or edited/fake

Contains matching UID

If verified:

User gets access to gift claim

Optionally verifies wallet balance

All verified UIDs are stored in MongoDB

🔍 Advanced Features
✅ Google Gemini API for real-time fake screenshot detection

✅ MongoDB data storage

✅ Channel join verification (configurable)

✅ Broadcast to all users

✅ Block detection

✅ Multi-mode UID input (manual + image OCR)

🧪 Need Help?
Want auto-start on VPS reboot, domain support, or advanced security?

Ask me to:

Create systemd service for auto-start

Add .env file support for easier variable management

Add MongoDB cloud setup

Add verification channel locks
](https://chatgpt.com/c/684be915-7270-8008-a6c5-6ab2c76f7c9b#:~:text=Notepad%20without%20issues%3A-,UIDChecker%20Telegram%20Bot%20%E2%80%93%20Setup%20%26%20Admin%20Guide,Channel%20join%20verification%20support%20(optional),-Need%20Help%3F)
