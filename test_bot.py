#!/usr/bin/env python3
import os
import logging

# Test script to verify bot functionality
print("Testing bot setup...")

# Check environment variables
bot_token = os.getenv('BOT_TOKEN')
admin_uid = os.getenv('ADMIN_UID')
gemini_key = os.getenv('GEMINI_API_KEY')

print(f"BOT_TOKEN exists: {bool(bot_token)}")
print(f"ADMIN_UID exists: {bool(admin_uid)}")
print(f"GEMINI_API_KEY exists: {bool(gemini_key)}")

# Test telegram import directly
try:
    from telegram.ext import Updater
    print("✓ Telegram import successful")
except ImportError as e:
    print(f"✗ Telegram import failed: {e}")

# Test MongoDB connection
try:
    from pymongo import MongoClient
    MONGO_URI = 'mongodb+srv://404movie:404moviepass@cluster0.fca76c9.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0'
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    client.admin.command('ping')
    print("✓ MongoDB connection successful")
except Exception as e:
    print(f"✗ MongoDB connection failed: {e}")

# Test Gemini API
try:
    import requests
    if gemini_key:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={gemini_key}"
        test_data = {
            "contents": [{"parts": [{"text": "Hello"}]}]
        }
        response = requests.post(url, json=test_data, timeout=10)
        if response.status_code == 200:
            print("✓ Gemini API connection successful")
        else:
            print(f"✗ Gemini API failed: {response.status_code}")
    else:
        print("✗ No Gemini API key provided")
except Exception as e:
    print(f"✗ Gemini API test failed: {e}")

print("Test completed.")