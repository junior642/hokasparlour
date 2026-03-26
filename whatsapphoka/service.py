import requests
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

WHATSAPP_SERVICE_URL = getattr(settings, 'WHATSAPP_SERVICE_URL', 'http://localhost:3000')


def normalize_phone(phone: str) -> str:
    """Convert any Kenyan phone format to 2547XXXXXXXX"""
    phone = phone.strip().replace("+", "").replace(" ", "").replace("-", "")
    if phone.startswith("0"):
        phone = "254" + phone[1:]
    return phone


def send_whatsapp_message(phone: str, message: str) -> dict:
    try:
        response = requests.post(
            f"{WHATSAPP_SERVICE_URL}/send-message",
            json={"phone": normalize_phone(phone), "message": message},
            timeout=10
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        logger.error("WhatsApp service is not running")
        return {"success": False, "error": "WhatsApp service unavailable"}
    except Exception as e:
        logger.error(f"WhatsApp send failed: {e}")
        return {"success": False, "error": str(e)}
