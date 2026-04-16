from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from parlour.models import Order, OrderItem
from .models import Profile, Agent, PromoUsage
from decimal import Decimal
from allauth.account.signals import user_signed_up
import logging

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Helper: Send WhatsApp safely (never crashes the main flow)
# ─────────────────────────────────────────────────────────────────────────────

def _send_whatsapp(phone: str, message: str, label: str = ""):
    """Wrapper so a WhatsApp failure never breaks order saving."""
    try:
        from whatsapphoka.service import send_whatsapp_message
        result = send_whatsapp_message(phone, message)
        logger.info(f"WhatsApp [{label}]: {result}")
    except Exception as e:
        logger.error(f"WhatsApp failed [{label}]: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Sales Record — fires on new order
# ─────────────────────────────────────────────────────────────────────────────

@receiver(post_save, sender=Order)
def create_sales_record(sender, instance, created, **kwargs):
    if created:
        try:
            from .models import SalesRecord
            total_items = sum(item.quantity for item in instance.orderitem_set.all())
            total_amount = instance.get_total()
            profit_estimate = Decimal(str(total_amount)) * Decimal('0.3')
            SalesRecord.objects.create(
                order=instance,
                total_items=total_items,
                total_amount=total_amount,
                profit_estimate=profit_estimate
            )
        except Exception as e:
            logger.error(f"Error creating sales record: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# WhatsApp Order Confirmation — fires on new order
# ─────────────────────────────────────────────────────────────────────────────

@receiver(post_save, sender=Order)
def send_order_confirmation_whatsapp(sender, instance, created, **kwargs):
    if not created or not instance.phone_number:
        return

    try:
        pickup_info = instance.get_pickup_info()
        items = instance.orderitem_set.select_related('product').all()

        items_text = ""
        for item in items:
            size_text = f" (Size: {item.size})" if item.size else ""
            items_text += f"  • {item.product.name}{size_text} x{item.quantity} — KES {item.get_subtotal():,.0f}\n"

        total = instance.get_total()

        message = (
            f"✅ *Order Confirmed — Qunimart*\n\n"
            f"Hi {instance.customer_name}! 🎉 Your order has been received.\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🧾 *Order #{instance.id}*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{items_text}\n"
            f"💰 *Total: KES {total:,.0f}*\n\n"
            f"📦 *Delivery Info*\n"
            f"{pickup_info['label']}\n"
            f"📍 {pickup_info['location']}\n\n"
            f"📬 *Delivery Address:*\n{instance.delivery_address}\n\n"
            f"We'll notify you when your order is dispatched. "
            f"Thank you for shopping with us! 🛍️"
        )

        _send_whatsapp(instance.phone_number, message, label=f"order_confirmation #{instance.id}")

    except Exception as e:
        logger.error(f"Error building order confirmation WhatsApp for #{instance.id}: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Product Stats — fires on new order item
# ─────────────────────────────────────────────────────────────────────────────

@receiver(post_save, sender=OrderItem)
def update_product_stats(sender, instance, created, **kwargs):
    if created:
        try:
            from .models import ProductStats
            stats, _ = ProductStats.objects.get_or_create(
                product=instance.product,
                defaults={
                    'total_sold': 0,
                    'total_revenue': Decimal('0.00')
                }
            )
            stats.total_sold += instance.quantity
            subtotal = instance.get_subtotal()
            if isinstance(subtotal, str):
                subtotal = Decimal(subtotal)
            elif not isinstance(subtotal, Decimal):
                subtotal = Decimal(str(subtotal))
            stats.total_revenue += subtotal
            stats.last_sold_date = instance.order.created_at
            stats.save()
        except Exception as e:
            logger.error(f"Error updating product stats: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Email + WhatsApp Status Updates — fires when order_status changes
# ─────────────────────────────────────────────────────────────────────────────

STATUS_WHATSAPP_MESSAGES = {
    'processing': (
        "⚙️ *Order Update — Qunimart*\n\n"
        "Hi {name}! Your order *#{id}* is now being *processed*. 🏪\n\n"
        "We're preparing your items and will notify you once dispatched."
    ),
    'dispatched': (
        "🚚 *Order Dispatched — Qunimart*\n\n"
        "Hi {name}! Great news — your order *#{id}* is on its way! 🎉\n\n"
        "📬 Delivering to: {address}\n\n"
        "You'll receive it soon. Thank you for your patience! 💛"
    ),
    'delivered': (
        "✅ *Order Delivered — Qunimart*\n\n"
        "Hi {name}! Your order *#{id}* has been *delivered*. 📦\n\n"
        "We hope you love your items! 😊\n"
        "If you have any issues, feel free to reach us at {store_phone}.\n\n"
        "Thank you for shopping with Qunimart! 🛍️💕"
    ),
}


@receiver(pre_save, sender=Order)
def send_order_status_email(sender, instance, **kwargs):
    if not instance.pk:
        return

    try:
        old_instance = Order.objects.get(pk=instance.pk)
    except Order.DoesNotExist:
        return

    status_changed = old_instance.order_status != instance.order_status

    # ── Emails (unchanged from your original) ────────────────────
    if status_changed:
        try:
            from .email_utils import send_order_status_change_email
            send_order_status_change_email(instance)
        except ImportError:
            logger.warning("send_order_status_change_email not found in email_utils")

        if instance.order_status == 'dispatched':
            try:
                from .email_utils import send_order_dispatched_email
                send_order_dispatched_email(instance)
            except ImportError:
                logger.warning("send_order_dispatched_email not found in email_utils")

    # ── WhatsApp Status Update ────────────────────────────────────
    if status_changed and instance.phone_number:
        template = STATUS_WHATSAPP_MESSAGES.get(instance.order_status)
        if template:
            try:
                from parlour.models import StoreSettings
                store_phone = StoreSettings.get_settings().store_phone
            except Exception:
                store_phone = '+254 700 000 000'

            message = template.format(
                name=instance.customer_name,
                id=instance.id,
                address=instance.delivery_address,
                store_phone=store_phone,
            )
            _send_whatsapp(
                instance.phone_number,
                message,
                label=f"status_{instance.order_status} #{instance.id}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# User Sign Up — referral / promo logic (unchanged)
# ─────────────────────────────────────────────────────────────────────────────

@receiver(user_signed_up)
def on_user_signed_up(request, user, **kwargs):
    profile, _ = Profile.objects.get_or_create(user=user)
    referral_code = request.session.pop('referral_code', None)

    logger.info(
        f"SIGNAL FIRED - user: {user.username} | "
        f"referral_code: {referral_code} | "
        f"session_key: {request.session.session_key}"
    )

    if referral_code:
        try:
            agent = Agent.objects.get(referral_code=referral_code, status='approved')
            if not hasattr(user, 'promousage'):
                PromoUsage.objects.create(
                    user=user,
                    agent=agent,
                    promo_purchases_count=0,
                    is_active=True
                )
            # Use update() to bypass ORM cache entirely
            Profile.objects.filter(user=user).update(
                show_promo_popup=False,
                promo_popup_shown=True
            )
            logger.info(f"Referral code {referral_code} applied for {user.username}")
        except Agent.DoesNotExist:
            Profile.objects.filter(user=user).update(
                show_promo_popup=True,
                promo_popup_shown=False
            )
            logger.info(f"Invalid referral — show_promo_popup=True set for {user.username}")
    else:
        Profile.objects.filter(user=user).update(
            show_promo_popup=True,
            promo_popup_shown=False
        )
        logger.info(f"No referral code — show_promo_popup=True set for {user.username}")