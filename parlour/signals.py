from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from parlour.models import Order, OrderItem
from .models import Profile, Agent, PromoUsage
from decimal import Decimal
from allauth.account.signals import user_signed_up
import logging

logger = logging.getLogger(__name__)


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


@receiver(pre_save, sender=Order)
def send_order_status_email(sender, instance, **kwargs):
    if instance.pk:
        try:
            old_instance = Order.objects.get(pk=instance.pk)
            if old_instance.order_status != instance.order_status:
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
        except Order.DoesNotExist:
            pass


@receiver(user_signed_up)
def on_user_signed_up(request, user, **kwargs):
    """
    Fires after ANY signup — manual OTP or Google OAuth.
    Handles referral code and promo popup flag.
    """
    profile, _ = Profile.objects.get_or_create(user=user)

    referral_code = request.session.pop('referral_code', None)

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
            profile.promo_popup_shown = True
            profile.save(update_fields=['promo_popup_shown'])
            logger.info(f"Referral code {referral_code} applied for {user.username}")
        except Agent.DoesNotExist:
            request.session['new_signup'] = True
            profile.promo_popup_shown = False
            profile.save(update_fields=['promo_popup_shown'])
    else:
        request.session['new_signup'] = True
        profile.promo_popup_shown = False
        profile.save(update_fields=['promo_popup_shown'])