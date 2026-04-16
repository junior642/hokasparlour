# whatsapp/messages.py

def order_confirmation_message(order) -> str:
    """
    Builds the WhatsApp message sent when an order is placed.
    Uses the Order model's existing methods for totals and delivery info.
    """
    store_settings = order.get_pickup_info()
    items = order.orderitem_set.select_related('product').all()

    # Build items list
    items_text = ""
    for item in items:
        size_text = f" (Size: {item.size})" if item.size else ""
        items_text += f"  • {item.product.name}{size_text} x{item.quantity} — KES {item.get_subtotal():,.0f}\n"

    total = order.get_total()
    delivery_label = store_settings['label']
    pickup_location = store_settings['location']

    message = (
        f"✅ *Order Confirmed — Qunimart*\n\n"
        f"Hi {order.customer_name}! 🎉 Your order has been received.\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🧾 *Order #{order.id}*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{items_text}\n"
        f"💰 *Total: KES {total:,.0f}*\n\n"
        f"📦 *Delivery Info*\n"
        f"{delivery_label}\n"
        f"📍 {pickup_location}\n\n"
        f"📬 *Delivery Address:*\n{order.delivery_address}\n\n"
        f"We'll notify you when your order is dispatched. Thank you for shopping with us! 🛍️"
    )
    return message


def order_status_update_message(order) -> str:
    """Sent when order status changes (processing, dispatched, delivered)."""

    status_messages = {
        'processing': (
            f"⚙️ *Order Update — Qunimart*\n\n"
            f"Hi {order.customer_name}! Your order *#{order.id}* is now being *processed*.\n\n"
            f"We're preparing your items and will notify you once dispatched. 🏪"
        ),
        'dispatched': (
            f"🚚 *Order Dispatched — Qunimart*\n\n"
            f"Hi {order.customer_name}! Great news! Your order *#{order.id}* is on its way. 🎉\n\n"
            f"📬 Delivering to: {order.delivery_address}\n\n"
            f"You'll receive it soon. Thank you for your patience! 💛"
        ),
        'delivered': (
            f"✅ *Order Delivered — Qunimart*\n\n"
            f"Hi {order.customer_name}! Your order *#{order.id}* has been *delivered*. 📦\n\n"
            f"We hope you love your items! 😊\n"
            f"If you have any issues, reply to this message or call us at {_get_store_phone()}.\n\n"
            f"Thank you for shopping with Qunimart! 🛍️💕"
        ),
    }

    return status_messages.get(order.order_status, f"Your order #{order.id} status has been updated to: {order.order_status}")


def payment_confirmed_message(order) -> str:
    """Sent when M-Pesa payment is confirmed."""
    total = order.get_total()
    return (
        f"💳 *Payment Confirmed — Qunimart*\n\n"
        f"Hi {order.customer_name}! We've received your payment of *KES {total:,.0f}* "
        f"for order *#{order.id}*. ✅\n\n"
        f"Your order is now being processed. We'll keep you updated! 🙏"
    )


def _get_store_phone():
    from store.models import StoreSettings
    try:
        return StoreSettings.get_settings().store_phone
    except Exception:
        return '+254 700 000 000'