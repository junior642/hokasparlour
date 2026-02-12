from django.core.mail import send_mail
from django.conf import settings
from .models import StoreSettings

def send_order_confirmation_email(order):
    """Send order confirmation email to customer with global pickup info"""
    
    # Get global store settings
    store_settings = StoreSettings.get_settings()
    pickup_info = order.get_pickup_info()
    
    subject = f'Order Confirmation #{order.id} - Hoka\'s Parlour'
    
    # Get order items
    items = order.orderitem_set.all()
    
    # Create email message
    message = f"""
Dear {order.customer_name},

Thank you for your order at Hoka's Parlour!

ORDER DETAILS
=============
Order Number: #{order.id}
Order Date: {order.created_at.strftime('%B %d, %Y at %I:%M %p')}
Order Status: {order.get_order_status_display()}

ITEMS ORDERED
=============
"""
    
    for item in items:
        message += f"\n- {item.product.name} (Size: {item.size})\n"
        message += f"  Quantity: {item.quantity}\n"
        message += f"  Price: ${item.price}\n"
        message += f"  Subtotal: ${item.get_subtotal()}\n"
    
    message += f"\nTOTAL AMOUNT: ${order.get_total()}\n"
    
    # Add global pickup information
    message += f"""
PICKUP INFORMATION
==================
Pickup Location: {pickup_info['location']}
Pickup Date: {pickup_info['date'].strftime('%B %d, %Y')}
Pickup Time: {pickup_info['time'].strftime('%I:%M %p')}
Pickup Days: {pickup_info['days']}

Please arrive on the pickup date during our pickup time with your Order ID.

DELIVERY ADDRESS (For Reference)
=================================
{order.delivery_address}

CONTACT INFORMATION
===================
Email: {order.email}
Phone: {order.phone_number}

Store Contact: {store_settings.store_phone}
Store Email: {store_settings.store_email}

IMPORTANT NOTES
===============
- Please bring your Order ID (#{order.id}) when picking up your order
- Pickup Date: {pickup_info['date'].strftime('%B %d, %Y')}
- Pickup Time: {pickup_info['time'].strftime('%I:%M %p')}
- Pickup Location: {pickup_info['location']}
- If you have any questions, contact us at {store_settings.store_email}

Thank you for shopping with us!

Best regards,
Hoka's Parlour Team
"""
    
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[order.email],
            fail_silently=False,
        )
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False