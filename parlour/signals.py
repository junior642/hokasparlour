from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from parlour.models import Order, OrderItem
from .models import SalesRecord, ProductStats
from .email_utils import send_order_status_change_email, send_order_dispatched_email
from decimal import Decimal

@receiver(post_save, sender=Order)
def create_sales_record(sender, instance, created, **kwargs):
    if created:
        total_items = sum(item.quantity for item in instance.orderitem_set.all())
        total_amount = instance.get_total()
        profit_estimate = Decimal(str(total_amount)) * Decimal('0.3')
        
        SalesRecord.objects.create(
            order=instance,
            total_items=total_items,
            total_amount=total_amount,
            profit_estimate=profit_estimate
        )


from decimal import Decimal

@receiver(post_save, sender=OrderItem)
def update_product_stats(sender, instance, created, **kwargs):
    if created:
        stats, created_stats = ProductStats.objects.get_or_create(
            product=instance.product,
            defaults={
                'total_sold': 0,
                'total_revenue': Decimal('0.00')
            }
        )
        
        stats.total_sold += instance.quantity
        
        # Ensure subtotal is a Decimal
        subtotal = instance.get_subtotal()
        if isinstance(subtotal, str):
            subtotal = Decimal(subtotal)
        elif not isinstance(subtotal, Decimal):
            subtotal = Decimal(str(subtotal))
        
        stats.total_revenue += subtotal
        stats.last_sold_date = instance.order.created_at
        stats.save()


@receiver(pre_save, sender=Order)
def send_order_status_email(sender, instance, **kwargs):
    if instance.pk:
        try:
            old_instance = Order.objects.get(pk=instance.pk)
            
            if old_instance.order_status != instance.order_status:
                send_order_status_change_email(instance)
                
                if instance.order_status == 'dispatched':
                    send_order_dispatched_email(instance)
        except Order.DoesNotExist:
            pass