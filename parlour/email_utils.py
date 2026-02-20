from django.core.mail import EmailMessage
from django.conf import settings
from .models import StoreSettings
import logging

logger = logging.getLogger(__name__)

def send_order_confirmation_email(order):
    """Send styled HTML order confirmation email with product images"""
    
    # Get global store settings
    store_settings = StoreSettings.get_settings()
    pickup_info = order.get_pickup_info()
    
    subject = f'Order Confirmation #{order.id} - Hoka\'s Parlour'
    
    # Get order items
    items = order.orderitem_set.all()
    
    # Build product rows HTML
    product_rows = ""
    for item in items:
        # Get product image URL (full URL needed for email)
        image_url = ""
        if item.product.image:
            image_url = f"{settings.MEDIA_URL}{item.product.image.name}"
        
        product_rows += f"""
        <tr>
            <td style="padding: 15px; border-bottom: 1px solid #eee;">
                <div style="display: flex; align-items: center; gap: 15px;">
                    <img src="{image_url}" alt="{item.product.name}" 
                         style="width: 80px; height: 80px; object-fit: cover; border-radius: 8px; border: 1px solid #ddd;">
                    <div>
                        <strong style="color: #333; font-size: 16px;">{item.product.name}</strong>
                        <p style="color: #666; margin: 5px 0; font-size: 14px;">Size: {item.size}</p>
                    </div>
                </div>
            </td>
            <td style="padding: 15px; border-bottom: 1px solid #eee; text-align: center; color: #666;">
                {item.quantity}
            </td>
            <td style="padding: 15px; border-bottom: 1px solid #eee; text-align: right; color: #666;">
                KSH {item.price}
            </td>
            <td style="padding: 15px; border-bottom: 1px solid #eee; text-align: right; color: #333; font-weight: bold;">
                KSH {item.get_subtotal()}
            </td>
        </tr>
        """
    
    # HTML email template
    html_message = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {{
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                margin: 0;
                padding: 20px;
                line-height: 1.6;
            }}
            .container {{
                max-width: 650px;
                margin: 0 auto;
                background: white;
                border-radius: 16px;
                overflow: hidden;
                box-shadow: 0 20px 60px rgba(0,0,0,0.15);
            }}
            .header {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 40px 30px;
                text-align: center;
            }}
            .logo {{
                font-size: 32px;
                font-weight: 800;
                margin-bottom: 10px;
                font-family: 'Playfair Display', serif;
            }}
            .logo span {{
                color: #ffd700;
            }}
            .success-badge {{
                background: rgba(255,255,255,0.2);
                display: inline-block;
                padding: 8px 20px;
                border-radius: 20px;
                font-size: 14px;
                margin-top: 10px;
            }}
            .content {{
                padding: 40px 30px;
            }}
            .order-id {{
                background: #f8f9fa;
                border-left: 4px solid #667eea;
                padding: 15px 20px;
                margin: 20px 0;
                border-radius: 4px;
            }}
            .order-id strong {{
                color: #667eea;
                font-size: 24px;
            }}
            .section {{
                margin: 30px 0;
            }}
            .section-title {{
                color: #333;
                font-size: 20px;
                font-weight: 700;
                margin-bottom: 15px;
                border-bottom: 2px solid #667eea;
                padding-bottom: 10px;
            }}
            .product-table {{
                width: 100%;
                border-collapse: collapse;
                margin: 20px 0;
            }}
            .product-table th {{
                background: #f8f9fa;
                color: #666;
                text-align: left;
                padding: 12px 15px;
                font-weight: 600;
                font-size: 12px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }}
            .total-row {{
                background: #667eea;
                color: white;
                font-size: 20px;
                font-weight: bold;
            }}
            .total-row td {{
                padding: 20px 15px;
            }}
            .info-box {{
                background: #fff3cd;
                border: 1px solid #ffc107;
                border-radius: 8px;
                padding: 20px;
                margin: 20px 0;
            }}
            .info-box h3 {{
                color: #856404;
                margin: 0 0 15px 0;
                font-size: 18px;
            }}
            .info-grid {{
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 15px;
                margin-top: 15px;
            }}
            .info-item {{
                background: white;
                padding: 12px;
                border-radius: 6px;
            }}
            .info-item strong {{
                display: block;
                color: #666;
                font-size: 11px;
                text-transform: uppercase;
                margin-bottom: 5px;
            }}
            .info-item span {{
                color: #333;
                font-size: 15px;
            }}
            .highlight {{
                background: #e8f5e9;
                border-left: 4px solid #4caf50;
                padding: 15px;
                margin: 20px 0;
                border-radius: 4px;
            }}
            .footer {{
                background: #f8f9fa;
                padding: 30px;
                text-align: center;
                border-top: 1px solid #eee;
            }}
            .footer p {{
                color: #666;
                margin: 5px 0;
                font-size: 14px;
            }}
            .social-links {{
                margin-top: 20px;
            }}
            .social-links a {{
                display: inline-block;
                margin: 0 10px;
                color: #667eea;
                text-decoration: none;
                font-weight: 600;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div class="logo">HOKA'S<span>PARLOUR</span></div>
                <p>Premium Fashion & Streetwear</p>
                <div class="success-badge">✓ Order Confirmed</div>
            </div>
            
            <div class="content">
                <h2 style="color: #333; text-align: center; margin-bottom: 10px;">Thank You for Your Order!</h2>
                <p style="text-align: center; color: #666; margin-bottom: 30px;">
                    Dear <strong>{order.customer_name}</strong>, your order has been successfully placed.
                </p>
                
                <div class="order-id">
                    <div style="color: #666; font-size: 12px; text-transform: uppercase; margin-bottom: 5px;">Order Number</div>
                    <strong>#{order.id}</strong>
                    <div style="color: #666; font-size: 14px; margin-top: 8px;">
                        {order.created_at.strftime('%B %d, %Y at %I:%M %p')}
                    </div>
                </div>
                
                <div class="section">
                    <h3 class="section-title">📦 Items Ordered</h3>
                    <table class="product-table">
                        <thead>
                            <tr>
                                <th>Product</th>
                                <th style="text-align: center;">Qty</th>
                                <th style="text-align: right;">Price</th>
                                <th style="text-align: right;">Subtotal</th>
                            </tr>
                        </thead>
                        <tbody>
                            {product_rows}
                        </tbody>
                        <tfoot>
                            <tr class="total-row">
                                <td colspan="3" style="text-align: right;">TOTAL:</td>
                                <td style="text-align: right;">KSH {order.get_total()}</td>
                            </tr>
                        </tfoot>
                    </table>
                </div>
                
                <div class="info-box">
                    <h3>📍 Pickup Information</h3>
                    <div class="info-grid">
                        <div class="info-item">
                            <strong>Pickup Location</strong>
                            <span>{pickup_info['location']}</span>
                        </div>
                        <div class="info-item">
                            <strong>Pickup Date</strong>
                            <span>{pickup_info['date'].strftime('%B %d, %Y')}</span>
                        </div>
                        <div class="info-item">
                            <strong>Pickup Time</strong>
                            <span>{pickup_info['time'].strftime('%I:%M %p')}</span>
                        </div>
                        <div class="info-item">
                            <strong>Available Days</strong>
                            <span>{pickup_info['days']}</span>
                        </div>
                    </div>
                </div>
                
                <div class="highlight">
                    <strong style="color: #2e7d32; font-size: 16px;">⚠️ Important Reminder:</strong>
                    <p style="color: #1b5e20; margin: 10px 0 0 0;">
                        Please bring your <strong>Order ID #{order.id}</strong> when picking up your order on 
                        <strong>{pickup_info['date'].strftime('%B %d, %Y')}</strong> at 
                        <strong>{pickup_info['time'].strftime('%I:%M %p')}</strong>.
                    </p>
                </div>
                
                <div class="section">
                    <h3 class="section-title">📋 Order Summary</h3>
                    <table style="width: 100%; color: #666; font-size: 14px;">
                        <tr>
                            <td style="padding: 8px 0;"><strong>Status:</strong></td>
                            <td style="text-align: right;">{order.get_order_status_display()}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0;"><strong>Email:</strong></td>
                            <td style="text-align: right;">{order.email}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0;"><strong>Phone:</strong></td>
                            <td style="text-align: right;">{order.phone_number}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0;"><strong>Delivery Address:</strong></td>
                            <td style="text-align: right;">{order.delivery_address}</td>
                        </tr>
                    </table>
                </div>
            </div>
            
            <div class="footer">
                <p style="font-weight: 600; color: #333; font-size: 16px;">Hoka's Parlour</p>
                <p>📍 {pickup_info['location']}</p>
                <p>📧 {store_settings.store_email} | 📞 {store_settings.store_phone}</p>
                
                <div style="margin: 20px 0; padding: 15px; background: white; border-radius: 8px; display: inline-block;">
                    <p style="color: #666; margin: 0; font-size: 13px;">
                        Questions? Contact us at <a href="mailto:{store_settings.store_email}" style="color: #667eea; text-decoration: none;">{store_settings.store_email}</a>
                    </p>
                </div>
                
                <p style="color: #999; font-size: 12px; margin-top: 20px;">
                    © 2026 Hoka's Parlour. All rights reserved.
                </p>
            </div>
        </div>
    </body>
    </html>
    """
    
    # Plain text fallback
    plain_message = f"""
Dear {order.customer_name},

Thank you for your order at Hoka's Parlour!

ORDER NUMBER: #{order.id}
Order Date: {order.created_at.strftime('%B %d, %Y at %I:%M %p')}

ITEMS ORDERED:
"""
    for item in items:
        plain_message += f"\n- {item.product.name} (Size: {item.size})\n"
        plain_message += f"  Quantity: {item.quantity} | Price: KSH {item.price} | Subtotal: KSH {item.get_subtotal()}\n"
    
    plain_message += f"\nTOTAL: KSH {order.get_total()}\n"
    plain_message += f"""
PICKUP INFORMATION:
Location: {pickup_info['location']}
Date: {pickup_info['date'].strftime('%B %d, %Y')}
Time: {pickup_info['time'].strftime('%I:%M %p')}

Please bring Order ID #{order.id} when picking up.

Contact: {store_settings.store_email} | {store_settings.store_phone}

Best regards,
Hoka's Parlour Team
    """
    
    try:
        # Create email with HTML content
        email = EmailMessage(
            subject=subject,
            body=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[order.email],
        )
        email.content_subtype = "html"
        email.body = html_message
        
        # Send email
        sent_count = email.send(fail_silently=False)
        
        logger.info(f"Order confirmation email sent to {order.email}. Result: {sent_count}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send order confirmation to {order.email}: {str(e)}")
        print(f"Error sending email: {e}")
        return False