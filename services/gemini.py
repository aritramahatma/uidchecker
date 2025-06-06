
"""
Gemini AI service for OCR and image analysis
"""
import logging
import requests
import base64
import re
from config import GEMINI_API_KEY

logger = logging.getLogger(__name__)


def gemini_ocr(image_bytes):
    """Process image using Gemini OCR to extract text"""
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        img_base64 = base64.b64encode(image_bytes).decode('utf-8')

        data = {
            "contents": [{
                "parts": [{
                    "text":
                    "Extract all text from this image, especially focusing on UIDs and balance amounts:"
                }, {
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": img_base64
                    }
                }]
            }]
        }

        response = requests.post(url, json=data, timeout=30)

        if response.ok:
            try:
                result = response.json()
                return result['candidates'][0]['content']['parts'][0]['text']
            except (KeyError, IndexError) as e:
                logger.error(f"Error parsing Gemini response: {e}")
                return ''
        else:
            logger.error(
                f"Gemini API error: {response.status_code} - {response.text}")
            return ''

    except Exception as e:
        logger.error(f"Error in gemini_ocr: {e}")
        return ''


def detect_fake_screenshot(image_bytes):
    """Use Gemini AI to detect if a screenshot has been digitally edited or manipulated"""
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        img_base64 = base64.b64encode(image_bytes).decode('utf-8')

        # Focused prompt for detecting digital editing and manipulation
        detection_prompt = """
DIGITAL EDITING DETECTION: Analyze this screenshot to detect if it has been digitally edited or manipulated using photo editing software.

IMPORTANT: Only flag as EDITED if you find CLEAR evidence of digital manipulation. Natural compression artifacts, normal screenshot quality variations, and typical mobile app interface elements should NOT be considered editing.

FOCUS ON THESE EDITING INDICATORS:

1. TEXT EDITING SIGNS:
   - Text that looks pasted or overlaid (not natural UI text)
   - Inconsistent fonts within similar elements
   - Text with different pixelation/quality than surroundings
   - Numbers that appear copied from elsewhere
   - Text with unnatural edges or artifacts
   - Inconsistent text alignment or spacing

2. DIGITAL MANIPULATION ARTIFACTS:
   - Copy-paste selection artifacts
   - Clone stamp tool marks
   - Brush tool evidence
   - Selection box remnants
   - Layer blend inconsistencies
   - Compression artifacts around edited areas (not normal JPEG compression)

3. VISUAL EDITING EVIDENCE:
   - Color mismatches in similar elements
   - Inconsistent lighting/shadows on text
   - Pixelation differences between areas (not normal compression)
   - Unnatural sharp edges around numbers/text
   - Background inconsistencies behind text
   - Different image quality in specific regions

4. PHOTO EDITING SOFTWARE TRACES:
   - Healing tool artifacts
   - Content-aware fill marks
   - Transform tool distortions
   - Filter inconsistencies
   - Digital watermark removal traces

PROVIDE ANALYSIS IN THIS FORMAT:
EDITING_STATUS: [UNEDITED/EDITED/HEAVILY_EDITED]
CONFIDENCE: [0-100]%
EDITING_EVIDENCE: [List specific editing signs found, or "None found" if unedited]
TEXT_ALTERED: [YES/NO - Details of text manipulation]
DIGITAL_ARTIFACTS: [YES/NO - Software editing traces]
RECOMMENDATION: [ACCEPT/REVIEW/REJECT]

If NO clear editing evidence is found, mark as UNEDITED with ACCEPT recommendation.
Focus ONLY on whether the image has been digitally modified/edited, not on whether the content is "real" or "fake".
"""

        data = {
            "contents": [{
                "parts": [{
                    "text": detection_prompt
                }, {
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": img_base64
                    }
                }]
            }],
            "generationConfig": {
                "temperature": 0.1,  # Low temperature for consistent analysis
                "maxOutputTokens": 1000
            }
        }

        response = requests.post(url, json=data, timeout=30)

        if response.ok:
            try:
                result = response.json()
                analysis = result['candidates'][0]['content']['parts'][0][
                    'text']

                # Parse the analysis
                is_unedited = True
                confidence_score = 100
                suspicious_elements = []

                # Check editing status
                if "EDITING_STATUS:" in analysis:
                    edit_line = [
                        line for line in analysis.split('\n')
                        if 'EDITING_STATUS:' in line
                    ][0]
                    if "UNEDITED" in edit_line.upper():
                        is_unedited = True
                    elif any(word in edit_line.upper()
                             for word in ['EDITED', 'HEAVILY_EDITED']):
                        is_unedited = False

                # Get confidence score
                if "CONFIDENCE:" in analysis:
                    conf_line = [
                        line for line in analysis.split('\n')
                        if 'CONFIDENCE:' in line
                    ][0]
                    conf_match = re.search(r'(\d+)', conf_line)
                    if conf_match:
                        confidence_score = int(conf_match.group(1))

                # Get evidence only if editing was detected
                if "EDITING_EVIDENCE:" in analysis and not is_unedited:
                    evidence_line = [
                        line for line in analysis.split('\n')
                        if 'EDITING_EVIDENCE:' in line
                    ]
                    if evidence_line:
                        evidence_text = evidence_line[0].replace(
                            'EDITING_EVIDENCE:', '').strip()
                        if evidence_text and evidence_text.lower() not in [
                                'none', 'no evidence', 'not found'
                        ]:
                            suspicious_elements.append(evidence_text)

                # Only check for specific editing indicators if not already marked as unedited
                if is_unedited:
                    # Additional checks for definitive editing indicators
                    if any(keyword in analysis.upper() for keyword in [
                            'TEXT_ALTERED: YES', 'DIGITAL_ARTIFACTS: YES',
                            'RECOMMENDATION: REJECT'
                    ]):
                        is_unedited = False

                return is_unedited, confidence_score, suspicious_elements, analysis

            except (KeyError, IndexError) as e:
                logger.error(f"Error parsing editing detection response: {e}")
                return False, 0, ["Error parsing AI response"], ""
        else:
            logger.error(
                f"Gemini editing detection API error: {response.status_code} - {response.text}"
            )
            return False, 0, ["API Error"], ""

    except Exception as e:
        logger.error(f"Error in detect_fake_screenshot: {e}")
        return False, 0, [f"Detection error: {str(e)}"], ""
