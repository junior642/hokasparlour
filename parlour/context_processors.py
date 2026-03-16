from django.utils import timezone
from datetime import timedelta
import logging
from parlour.models import Profile

logger = logging.getLogger(__name__)


def whatsapp_popup(request):
    if not request.user.is_authenticated:
        return {'show_whatsapp_popup': False}

    try:
        profile = request.user.profile

        if profile.whatsapp_joined:
            return {'show_whatsapp_popup': False}

        if not profile.whatsapp_popup_dismissed_at:
            return {'show_whatsapp_popup': True}

        three_days_ago = timezone.now() - timedelta(days=3)
        if profile.whatsapp_popup_dismissed_at < three_days_ago:
            return {'show_whatsapp_popup': True}

        return {'show_whatsapp_popup': False}

    except Exception:
        return {'show_whatsapp_popup': False}

def promo_popup(request):
    """Show promo code popup once on first signup — uses DB flag, not session."""
    if not request.user.is_authenticated:
        return {'show_promo_popup': False}

    try:
        # Force fresh read from DB every time
        profile = Profile.objects.get(user=request.user)

        logger.info(f"PROMO CHECK - show_promo_popup: {profile.show_promo_popup} | promo_popup_shown: {profile.promo_popup_shown} | user: {request.user}")

        if profile.promo_popup_shown:
            return {'show_promo_popup': False}
        if hasattr(request.user, 'promousage'):
            return {'show_promo_popup': False}
        if profile.show_promo_popup:
            return {'show_promo_popup': True}

        return {'show_promo_popup': False}

    except Exception as e:
        logger.error(f"PROMO CHECK ERROR: {e}")
        return {'show_promo_popup': False}

def cart_count(request):
    cart = request.session.get('cart', {})
    count = sum(item['quantity'] for item in cart.values())
    return {'cart_count': count}
