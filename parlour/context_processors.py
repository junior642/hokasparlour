from django.utils import timezone
from datetime import timedelta

def whatsapp_popup(request):
    if not request.user.is_authenticated:
        return {'show_whatsapp_popup': False}
    
    try:
        profile = request.user.profile
        
        # Never show if already joined
        if profile.whatsapp_joined:
            return {'show_whatsapp_popup': False}
        
        # Show if never dismissed
        if not profile.whatsapp_popup_dismissed_at:
            return {'show_whatsapp_popup': True}
        
        # Show again if 3 days have passed since last dismissal
        three_days_ago = timezone.now() - timedelta(days=3)
        if profile.whatsapp_popup_dismissed_at < three_days_ago:
            return {'show_whatsapp_popup': True}
        
        return {'show_whatsapp_popup': False}
    
    except Exception:
        return {'show_whatsapp_popup': False}