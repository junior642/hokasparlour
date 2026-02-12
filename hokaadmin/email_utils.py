from django.core.mail import send_mail
from django.conf import settings
from .models import EmailLog

def send_order_email(recipient_email, subject, message):
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient_email],
            fail_silently=False,
        )
        
        EmailLog.objects.create(
            recipient_email=recipient_email,
            subject=subject,
            message=message,
            status='sent'
        )
        
        return True
    except Exception as e:
        EmailLog.objects.create(
            recipient_email=recipient_email,
            subject=subject,
            message=message,
            status='failed'
        )
        
        return False


def send_order_status_change_email(order):
    subject = f"Order #{order.id} Status Update - Hoka's Parlour"
    message = f"""
Dear {order.customer_name},

Your order #{order.id} status has been updated to: {order.get_order_status_display()}

Order Details:
- Order ID: {order.id}
- Status: {order.get_order_status_display()}
- Order Date: {order.created_at.strftime('%Y-%m-%d %H:%M:%S')}

"""
    
    if order.expected_delivery_date:
        message += f"- Expected Delivery: {order.expected_delivery_date}\n"
    
    if order.delivery_location:
        message += f"- Current Location: {order.delivery_location}\n"
    
    message += """
Thank you for shopping with Hoka's Parlour!

Best regards,
Hoka's Parlour Team
"""
    
    return send_order_email(order.email, subject, message)


def send_order_dispatched_email(order):
    subject = f"Order #{order.id} Dispatched - Hoka's Parlour"
    message = f"""
Dear {order.customer_name},

Great news! Your order #{order.id} has been dispatched and is on its way to you.

Order Details:
- Order ID: {order.id}
- Status: Dispatched
- Delivery Address: {order.delivery_address}
"""
    
    if order.expected_delivery_date:
        message += f"- Expected Delivery: {order.expected_delivery_date}\n"
    
    if order.delivery_location:
        message += f"- Current Location: {order.delivery_location}\n"
    
    message += """
You can track your order status at any time using your Order ID.

Thank you for shopping with Hoka's Parlour!

Best regards,
Hoka's Parlour Team
"""
    
    return send_order_email(order.email, subject, message)