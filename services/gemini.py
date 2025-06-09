
"""
Gemini AI OCR and fake detection service
"""
import os
import re
import logging
import requests
import base64
from PIL import Image, ImageEnhance, ImageFilter
from io import BytesIO
import json

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', 'AIzaSyAGDi2WslEe8VvBc7v3-dwpEmJobE6df1o')


def preprocess_image(img_bytes):
    """Preprocess image for better OCR accuracy"""
    try:
        # Open image from bytes
        image = Image.open(BytesIO(img_bytes))
        
        # Convert to RGB if necessary
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Resize if image is too large (max 2048x2048)
        max_size = 2048
        if image.width > max_size or image.height > max_size:
            image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        
        # Enhance contrast and sharpness for better OCR
        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(1.2)
        
        enhancer = ImageEnhance.Sharpness(image)
        image = enhancer.enhance(1.1)
        
        # Convert back to bytes
        output = BytesIO()
        image.save(output, format='JPEG', quality=95)
        return output.getvalue()
        
    except Exception as e:
        logger.error(f"Error preprocessing image: {e}")
        return img_bytes


def gemini_ocr(img_bytes):
    """Extract text from image using Gemini Vision API with enhanced prompting"""
    try:
        # Preprocess image for better quality
        processed_img = preprocess_image(img_bytes)
        
        # Convert to base64
        img_base64 = base64.b64encode(processed_img).decode('utf-8')
        
        # Enhanced prompt for better text extraction
        prompt = """
        You are an expert OCR system. Please extract ALL text from this image with high accuracy.
        
        Focus on:
        1. Numbers (especially UIDs, balances, amounts)
        2. Currency symbols (₹, Rs, INR)
        3. Labels and headings
        4. Any visible text or numbers
        
        Extract text exactly as it appears. Include:
        - UID/User ID numbers
        - Balance amounts with currency
        - All visible numbers and text
        - App names and headers
        
        Return the extracted text in a clean, readable format.
        """
        
        # API request payload
        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": img_base64
                        }
                    }
                ]
            }],
            "generationConfig": {
                "temperature": 0.1,
                "topK": 32,
                "topP": 1,
                "maxOutputTokens": 2048,
            }
        }
        
        # Make API request
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        
        response = requests.post(
            url,
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            if 'candidates' in result and len(result['candidates']) > 0:
                text = result['candidates'][0]['content']['parts'][0]['text']
                logger.info(f"OCR extracted text: {text[:200]}...")
                return text.strip()
            else:
                logger.error("No text extracted from image")
                return ""
        else:
            logger.error(f"Gemini API error: {response.status_code} - {response.text}")
            return ""
            
    except Exception as e:
        logger.error(f"Error in gemini_ocr: {e}")
        return ""


def detect_fake_screenshot(img_bytes):
    """
    Advanced fake screenshot detection using Gemini AI
    Returns: (is_unedited, confidence_score, editing_evidence, full_analysis)
    """
    try:
        # Preprocess image
        processed_img = preprocess_image(img_bytes)
        img_base64 = base64.b64encode(processed_img).decode('utf-8')
        
        # Enhanced fake detection prompt
        prompt = """
        You are an expert digital forensics analyst specializing in screenshot authenticity verification.
        
        Analyze this image for signs of digital editing, manipulation, or fakery. Look for:
        
        TECHNICAL INDICATORS:
        1. Compression artifacts inconsistencies
        2. Pixel-level anomalies
        3. Font rendering inconsistencies
        4. Shadow/lighting mismatches
        5. Resolution inconsistencies
        6. Color gradient abnormalities
        
        CONTENT INDICATORS:
        1. Unrealistic UI elements
        2. Misaligned text or buttons
        3. Inconsistent app styling
        4. Suspicious number patterns
        5. Copy-paste evidence
        6. Template usage signs
        
        METADATA ANALYSIS:
        1. Image quality vs claimed source
        2. Aspect ratio consistency
        3. Screen recording vs screenshot markers
        
        Provide analysis in this EXACT format:
        
        AUTHENTICITY: [GENUINE/SUSPICIOUS/EDITED]
        CONFIDENCE: [0-100]%
        EVIDENCE: [list specific signs found]
        ANALYSIS: [detailed technical explanation]
        
        Be strict in evaluation. Even minor editing signs should be flagged.
        """
        
        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": img_base64
                        }
                    }
                ]
            }],
            "generationConfig": {
                "temperature": 0.1,
                "topK": 32,
                "topP": 1,
                "maxOutputTokens": 1024,
            }
        }
        
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        
        response = requests.post(
            url,
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            if 'candidates' in result and len(result['candidates']) > 0:
                analysis = result['candidates'][0]['content']['parts'][0]['text']
                
                # Parse the analysis
                is_unedited = True
                confidence_score = 0
                editing_evidence = []
                
                # Extract authenticity
                auth_match = re.search(r'AUTHENTICITY:\s*(\w+)', analysis, re.IGNORECASE)
                if auth_match:
                    authenticity = auth_match.group(1).upper()
                    if authenticity in ['SUSPICIOUS', 'EDITED']:
                        is_unedited = False
                
                # Extract confidence
                conf_match = re.search(r'CONFIDENCE:\s*(\d+)', analysis)
                if conf_match:
                    confidence_score = int(conf_match.group(1))
                
                # Extract evidence
                evidence_match = re.search(r'EVIDENCE:\s*(.+?)(?=ANALYSIS:|$)', analysis, re.DOTALL)
                if evidence_match:
                    evidence_text = evidence_match.group(1).strip()
                    editing_evidence = [item.strip() for item in evidence_text.split(',') if item.strip()]
                
                logger.info(f"Fake detection - Unedited: {is_unedited}, Confidence: {confidence_score}%")
                return is_unedited, confidence_score, editing_evidence, analysis
                
            else:
                logger.error("No analysis returned from Gemini")
                return True, 0, [], "Analysis failed"
        else:
            logger.error(f"Gemini API error in fake detection: {response.status_code}")
            return True, 0, [], "API error"
            
    except Exception as e:
        logger.error(f"Error in fake detection: {e}")
        return True, 0, [], f"Error: {e}"


def extract_uid_and_balance(text):
    """
    Enhanced extraction of UID and balance from OCR text
    """
    try:
        extracted_data = {
            'uid': None,
            'balance': None,
            'currency': None
        }
        
        # Enhanced UID patterns
        uid_patterns = [
            r'(?:UID|User\s*ID|ID)[:\s]*(\d{6,12})',  # Labeled UID
            r'(\d{8,12})',  # 8-12 digit numbers (most likely UIDs)
            r'(\d{6,7})',   # 6-7 digit numbers (shorter UIDs)
        ]
        
        for pattern in uid_patterns:
            uid_match = re.search(pattern, text, re.IGNORECASE)
            if uid_match:
                potential_uid = uid_match.group(1)
                # Avoid very common numbers like years, small amounts
                if len(potential_uid) >= 6 and not potential_uid.startswith('20'):
                    extracted_data['uid'] = potential_uid
                    break
        
        # Enhanced balance patterns
        balance_patterns = [
            r'(?:₹|Rs\.?|INR)\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)',
            r'(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)\s*(?:₹|Rs\.?|INR)',
            r'(?:Balance|Total|Amount|Available)[:\s]*(?:₹|Rs\.?|INR)?\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)',
            r'(?:Balance|Total)[:\s]*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)',
            r'(\d{1,3}(?:,\d{3})*\.\d{2})',  # Any decimal number format
            r'(\d{3,6})\s*(?:₹|Rs)',  # Numbers before currency
        ]
        
        for pattern in balance_patterns:
            balance_match = re.search(pattern, text, re.IGNORECASE)
            if balance_match:
                balance_str = balance_match.group(1).replace(',', '')
                try:
                    balance = float(balance_str)
                    # Reasonable balance range check
                    if 0 <= balance <= 1000000:  # Up to 10 lakh
                        extracted_data['balance'] = balance
                        # Detect currency
                        if '₹' in text or 'Rs' in text or 'INR' in text:
                            extracted_data['currency'] = 'INR'
                        break
                except ValueError:
                    continue
        
        logger.info(f"Extracted data: UID={extracted_data['uid']}, Balance={extracted_data['balance']}")
        return extracted_data
        
    except Exception as e:
        logger.error(f"Error extracting UID and balance: {e}")
        return {'uid': None, 'balance': None, 'currency': None}


def analyze_screenshot_quality(img_bytes):
    """Analyze screenshot quality and provide recommendations"""
    try:
        image = Image.open(BytesIO(img_bytes))
        
        quality_score = 100
        issues = []
        
        # Check resolution
        if image.width < 300 or image.height < 500:
            quality_score -= 30
            issues.append("Low resolution")
        
        # Check aspect ratio (should be mobile-like)
        aspect_ratio = image.height / image.width
        if aspect_ratio < 1.3 or aspect_ratio > 2.5:
            quality_score -= 20
            issues.append("Unusual aspect ratio")
        
        # Check if image is too small in bytes
        if len(img_bytes) < 10000:  # Less than 10KB
            quality_score -= 25
            issues.append("Very small file size")
        
        return quality_score, issues
        
    except Exception as e:
        logger.error(f"Error analyzing screenshot quality: {e}")
        return 50, ["Quality analysis failed"]
