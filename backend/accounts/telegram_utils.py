import os
import base64
import qrcode
from io import BytesIO
import requests
from django.conf import settings


def _telegram_post(url, payload, timeout=10):
    """POST to Telegram API without inheriting broken proxy env vars."""
    with requests.Session() as session:
        session.trust_env = False
        return session.post(url, json=payload, timeout=timeout)


def generate_qr_code_with_ref(ref_id):
    """
    Generate QR code containing ref_id and return base64 encoded image.
    
    Args:
        ref_id: Unique reference ID for the OTP session
        
    Returns:
        dict: {
            'qr_code_base64': base64 encoded QR code image,
            'ref_id': reference ID,
            'telegram_url': deeplink to Telegram bot
        }
    """
    try:
        bot_username = os.getenv('TELEGRAM_BOT_USERNAME', 'auto_invest_bot')

        # Create QR code using the Telegram deep link payload so scanners open the bot directly
        telegram_link = f'https://t.me/{bot_username}?start={ref_id}'

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=2,
        )
        qr.add_data(telegram_link)
        qr.make(fit=True)

        # Create image
        img = qr.make_image(fill_color="black", back_color="white")

        # Convert to base64
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        img_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

        return {
            'qr_code_base64': img_base64,
            'ref_id': ref_id,
            'telegram_url': telegram_link
        }
    except Exception as e:
        raise Exception(f"Failed to generate QR code: {str(e)}")


def send_otp_via_telegram(telegram_user_id, otp_code, ref_id=None):
    """
    Send OTP to user via Telegram.
    
    Args:
        telegram_user_id: Telegram user ID
        otp_code: 6-digit OTP code
        ref_id: Optional reference ID for logging
        
    Returns:
        bool: True if message sent successfully, False otherwise
    """
    try:
        bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        if not bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN not configured in .env")
        
        message = f"""🔐 Your AUTO INVEST OTP

Your One-Time Password is:

<b>{otp_code}</b>

⏰ This code expires in 10 minutes
🔒 Never share this code with anyone

If you didn't request this, ignore this message."""
        
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            'chat_id': telegram_user_id,
            'text': message,
            'parse_mode': 'HTML'
        }
        
        response = _telegram_post(url, payload, timeout=10)
        if response.status_code != 200:
            print(f"Telegram API HTTP error (ref: {ref_id}): {response.status_code} {response.text}")
            return False

        try:
            data = response.json()
        except Exception:
            print(f"Telegram API non-JSON response (ref: {ref_id}): {response.text}")
            return False

        if not data.get("ok", False):
            print(f"Telegram API rejected message (ref: {ref_id}): {data}")
            return False

        return True
            
    except Exception as e:
        print(f"Failed to send OTP via Telegram (ref: {ref_id}): {str(e)}")
        return False


def send_password_reset_message(telegram_user_id, new_password=None):
    """
    Send password reset confirmation via Telegram.
    
    Args:
        telegram_user_id: Telegram user ID
        new_password: Optional new password (if generated)
        
    Returns:
        bool: True if message sent successfully, False otherwise
    """
    try:
        bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        if not bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN not configured in .env")
        
        if new_password:
            message = f"""✅ Password Reset Successful

Your new password is:
<b>{new_password}</b>

⚠️ Please change this immediately after logging in for security reasons."""
        else:
            message = """✅ Password Reset Successful

You can now login with your new password."""
        
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            'chat_id': telegram_user_id,
            'text': message,
            'parse_mode': 'HTML'
        }
        
        response = _telegram_post(url, payload, timeout=10)
        if response.status_code != 200:
            return False
        try:
            data = response.json()
        except Exception:
            return False
        return bool(data.get("ok", False))
        
    except Exception as e:
        print(f"Failed to send reset message via Telegram: {str(e)}")
        return False


def send_telegram_update_response(chat_id, text):
    """Send a plain Telegram message in response to webhook update."""
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN not configured in .env")

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML'
    }
    resp = _telegram_post(url, payload, timeout=10)
    if resp.status_code != 200:
        return False
    try:
        data = resp.json()
    except Exception:
        return False
    return bool(data.get("ok", False))
