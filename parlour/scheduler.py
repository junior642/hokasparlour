import logging
from django.utils import timezone
from django.core.mail import EmailMessage
from django.conf import settings
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from django_apscheduler.jobstores import DjangoJobStore

logger = logging.getLogger(__name__)


def send_daily_orders_email():
    from .models import Order, OrderItem

    today = timezone.now().date()
    orders = Order.objects.filter(created_at__date=today).prefetch_related('orderitem_set__product').order_by('-created_at')

    total_orders = orders.count()
    total_revenue = sum(o.get_total() for o in orders)
    paid_orders = orders.filter(is_paid=True).count()

    if total_orders == 0:
        orders_html = '''
        <div style="text-align:center; padding:40px; color:#999;">
            <p style="font-size:18px;">No orders were placed today.</p>
        </div>
        '''
    else:
        rows = ""
        for order in orders:
            items_list = ", ".join(
                f"{item.product.name} x{item.quantity} ({item.size})"
                for item in order.orderitem_set.all()
            )
            paid_badge = (
                '<span style="background:#28a745;color:white;padding:3px 10px;border-radius:12px;font-size:11px;">Paid</span>'
                if order.is_paid else
                '<span style="background:#dc3545;color:white;padding:3px 10px;border-radius:12px;font-size:11px;">Not Paid</span>'
            )
            rows += f"""
            <tr style="border-bottom:1px solid #eee;">
                <td style="padding:12px 8px;color:#333;">#{order.id}</td>
                <td style="padding:12px 8px;color:#333;">{order.customer_name}</td>
                <td style="padding:12px 8px;color:#333;">{order.phone_number}</td>
                <td style="padding:12px 8px;color:#333;">{items_list}</td>
                <td style="padding:12px 8px;color:#333;">KSH {order.get_total()}</td>
                <td style="padding:12px 8px;">{paid_badge}</td>
                <td style="padding:12px 8px;color:#333;">{order.order_status.title()}</td>
                <td style="padding:12px 8px;color:#999;font-size:12px;">{order.created_at.strftime('%I:%M %p')}</td>
            </tr>
            """

        orders_html = f"""
        <table style="width:100%;border-collapse:collapse;font-size:14px;">
            <thead>
                <tr style="background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:white;">
                    <th style="padding:12px 8px;text-align:left;">#</th>
                    <th style="padding:12px 8px;text-align:left;">Customer</th>
                    <th style="padding:12px 8px;text-align:left;">Phone</th>
                    <th style="padding:12px 8px;text-align:left;">Items</th>
                    <th style="padding:12px 8px;text-align:left;">Total</th>
                    <th style="padding:12px 8px;text-align:left;">Payment</th>
                    <th style="padding:12px 8px;text-align:left;">Status</th>
                    <th style="padding:12px 8px;text-align:left;">Time</th>
                </tr>
            </thead>
            <tbody>
                {rows}
            </tbody>
        </table>
        """

    html = f"""
    <!DOCTYPE html>
    <html>
    <head></head>
    <body style="font-family:Arial,sans-serif;background:#f5f5f5;margin:0;padding:20px;">
        <div style="max-width:900px;margin:0 auto;background:white;border-radius:16px;overflow:hidden;box-shadow:0 4px 12px rgba(0,0,0,0.1);">
            
            <div style="background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:white;padding:40px 30px;text-align:center;">
                <div style="font-size:32px;font-weight:800;margin-bottom:10px;">Qunimart<span style="color:#ffd700;">PARLOUR</span></div>
                <h1 style="margin:0;font-size:22px;">📦 Daily Orders Report</h1>
                <p style="margin:10px 0 0 0;opacity:0.9;">{today.strftime('%A, %B %d, %Y')}</p>
            </div>

            <div style="padding:30px;">

                <div style="display:flex;gap:15px;margin-bottom:30px;flex-wrap:wrap;">
                    <div style="flex:1;min-width:150px;background:#f8f9fa;padding:20px;border-radius:12px;border-left:4px solid #667eea;text-align:center;">
                        <div style="font-size:32px;font-weight:800;color:#667eea;">{total_orders}</div>
                        <div style="color:#666;font-size:14px;">Total Orders</div>
                    </div>
                    <div style="flex:1;min-width:150px;background:#f8f9fa;padding:20px;border-radius:12px;border-left:4px solid #28a745;text-align:center;">
                        <div style="font-size:32px;font-weight:800;color:#28a745;">{paid_orders}</div>
                        <div style="color:#666;font-size:14px;">Paid Orders</div>
                    </div>
                    <div style="flex:1;min-width:150px;background:#f8f9fa;padding:20px;border-radius:12px;border-left:4px solid #ffc107;text-align:center;">
                        <div style="font-size:28px;font-weight:800;color:#ffc107;">KSH {total_revenue}</div>
                        <div style="color:#666;font-size:14px;">Total Revenue</div>
                    </div>
                </div>

                <h2 style="color:#333;border-bottom:2px solid #667eea;padding-bottom:10px;">Order Details</h2>
                {orders_html}

            </div>

            <div style="background:#f8f9fa;padding:20px;text-align:center;border-top:1px solid #eee;">
                <p style="color:#666;margin:5px 0;font-size:14px;">Qunimart — Automated Daily Report</p>
                <p style="color:#999;margin:5px 0;font-size:12px;">© 2026 Qunimart. All rights reserved.</p>
            </div>
        </div>
    </body>
    </html>
    """

    email = EmailMessage(
        subject=f"📦 Daily Orders Report — {today.strftime('%B %d, %Y')} ({total_orders} orders)",
        body=html,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=['hokasparlour@gmail.com'],
    )
    email.content_subtype = "html"
    email.send(fail_silently=False)
    logger.info(f"Daily orders email sent: {total_orders} orders, KSH {total_revenue}")


def start():
    scheduler = BackgroundScheduler(timezone=str(timezone.get_current_timezone()))
    scheduler.add_jobstore(DjangoJobStore(), "default")

    scheduler.add_job(
        send_daily_orders_email,
        trigger=CronTrigger(hour=19, minute=0),  # 7:00 PM daily
        id="daily_orders_email",
        name="Send daily orders report at 7PM",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler started — daily orders email at 7:00 PM")