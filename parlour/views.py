from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from django.db import models, transaction
from django.db.models import F
from .models import Product, Order, OrderItem, EmailOTP, StoreSettings, Advertisement, AdImpression, Category, Agent
from .email_utils import send_order_confirmation_email
import random
import logging
from django.contrib.admin.views.decorators import staff_member_required
from .models import Agent, PromoUsage

def home(request):
    from django.db.models import Sum
    import json

    # ── Base product queryset ─────────────────────────────────────
    products = Product.objects.all()

    # Get filter parameters
    category = request.GET.get('category')
    min_price = request.GET.get('min_price')
    max_price = request.GET.get('max_price')

    # Apply filters
    if category:
        products = products.filter(category__id=category)
    if min_price:
        products = products.filter(price__gte=min_price)
    if max_price:
        products = products.filter(price__lte=max_price)

    # Get all categories for the filter sidebar
    categories = Category.objects.all()

    # ── Top selling products ──────────────────────────────────────
    top_selling = Product.objects.filter(
        orderitem__order__isnull=False
    ).annotate(
        total_sold=Sum('orderitem__quantity')
    ).order_by('-total_sold')[:8]

    # ── User promo status ─────────────────────────────────────────
    user_promo = None
    if request.user.is_authenticated:
        try:
            user_promo = request.user.promousage
        except Exception:
            pass

    # ── Active ads helper ─────────────────────────────────────────
    now = timezone.now()

    def get_active_ads(queryset):
        queryset = queryset.filter(
            models.Q(start_date__isnull=True) | models.Q(start_date__lte=now)
        ).filter(
            models.Q(end_date__isnull=True) | models.Q(end_date__gte=now)
        )
        user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
        is_mobile = any(x in user_agent for x in ['mobile', 'android', 'iphone', 'phone'])
        is_tablet = any(x in user_agent for x in ['ipad', 'tablet'])

        result = []
        for ad in queryset:
            if is_mobile and not ad.show_on_mobile:
                continue
            if is_tablet and not ad.show_on_tablet:
                continue
            if not is_mobile and not is_tablet and not ad.show_on_desktop:
                continue
            result.append(ad)
        return result

    # ── Session for impression tracking ──────────────────────────
    session_key = request.session.session_key
    if not session_key:
        request.session.save()
        session_key = request.session.session_key

    def record_impressions(ads_list):
        for ad in ads_list:
            try:
                AdImpression.objects.create(
                    advertisement=ad,
                    session_key=session_key,
                    ip_address=request.META.get('REMOTE_ADDR', ''),
                    user_agent=request.META.get('HTTP_USER_AGENT', '')[:255]
                )
                ad.increment_views()
            except Exception as e:
                print(f"Error recording impression: {e}")

    # ── Main (hero) ads ───────────────────────────────────────────
    main_ads_qs = Advertisement.objects.filter(
        is_active=True,
        ad_category='main',
    ).order_by('order', '-created_at')
    main_ads = get_active_ads(main_ads_qs)
    record_impressions(main_ads)

    # ── Category sections with their own ads ──────────────────────
    category_sections = []

    all_categories = Category.objects.all()
    for cat in all_categories:
        cat_products = products.filter(category=cat)
        if not cat_products.exists():
            continue

        cat_ads_qs = Advertisement.objects.filter(
            is_active=True,
            product_category=cat,
        ).exclude(ad_category='main').order_by('order', '-created_at')

        cat_ads = get_active_ads(cat_ads_qs)
        record_impressions(cat_ads)

        category_sections.append({
            'category': cat,
            'products': cat_products,
            'ads': cat_ads,
        })

    # Uncategorized products
    uncategorized = products.filter(category__isnull=True)
    if uncategorized.exists():
        category_sections.append({
            'category': None,
            'products': uncategorized,
            'ads': [],
        })

    # ── Prepare slideshow data for templates ──────────────────────
    slideshow_data = []
    for ad in main_ads:
        slideshow_data.append({
            'id': ad.id,
            'headline': ad.headline,
            'subheadline': ad.subheadline,
            'button_text': ad.button_text,
            'button_url': ad.get_button_url(),
            'button_color': ad.button_color,
            'image_url': ad.single_image.url if ad.single_image else None,
            'video_url': ad.video.url if ad.video else None,
            'video_poster': ad.video_poster.url if ad.video_poster else None,
            'ad_type': ad.ad_type,
            'background_color': ad.background_color,
            'product_category': ad.product_category.name if ad.product_category else None,
        })

    context = {
        'products': products,
        'categories': categories,
        'selected_category': int(category) if category else None,
        'min_price': min_price,
        'max_price': max_price,
        'ads': main_ads,
        'slideshow_data': json.dumps(slideshow_data),
        'category_sections': category_sections,
        'top_selling': top_selling,
        'user_promo': user_promo,               # ← added
    }
    return render(request, 'parlour/home.html', context)

def product_detail(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    sizes = [size.strip() for size in product.available_sizes.split(',')]
    
    all_images = []
    if product.image:
        all_images.append({'url': product.image.url, 'is_main': True})
    
    for additional_image in product.additional_images.all():
        all_images.append({
            'url': additional_image.image.url,
            'is_main': False,
            'alt_text': additional_image.alt_text
        })
    
    # Fix: category is now a ForeignKey
    recommended_products = Product.objects.filter(
        category=product.category,  
    ).exclude(
        id=product.id
    ).order_by('-created_at')[:4]

    # ── Pricing info ──────────────────────────────────────────────
    user_promo = None
    if request.user.is_authenticated:
        try:
            user_promo = request.user.promousage
        except Exception:
            pass

    prices = product.get_display_prices(request.user)
    
    context = {
        'product': product,
        'sizes': sizes,
        'all_images': all_images,
        'recommended_products': recommended_products,
        'user_promo': user_promo,       # promo usage object
        'prices': prices,               # dict with price, anchor_price, has_discount, promo_remaining
    }
    return render(request, 'parlour/product_detail.html', context)

from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from .models import Product, ProductImage
from decimal import Decimal

def is_staff_user(user):
    return user.is_staff

@login_required
@user_passes_test(is_staff_user)
def manage_products(request):
    """List all products for management"""
    products = Product.objects.all().order_by('-created_at')
    
    context = {
        'products': products
    }
    return render(request, 'parlour/manage_products.html', context)


@login_required
@user_passes_test(is_staff_user)
def add_product(request):
    """Add new product"""
    if request.method == 'POST':
        try:
            # Get form data
            name = request.POST.get('name')
            description = request.POST.get('description')
            price = request.POST.get('price')
            category = request.POST.get('category')
            available_sizes = request.POST.get('available_sizes')
            stock_type = request.POST.get('stock_type')
            stock_quantity = request.POST.get('stock_quantity', 1)
            purchase_cost = request.POST.get('purchase_cost')
            supplier_cost = request.POST.get('supplier_cost')
            main_image = request.FILES.get('image')

            # Validate required fields
            if not all([name, description, price, category, available_sizes, stock_type]):
                messages.error(request, 'All required fields must be filled in!')
                return redirect('add_product')

            # Warehouse stock doesn't need a quantity
            if stock_type == 'warehouse':
                stock_quantity = 0

            # Create product
            product = Product.objects.create(
                name=name,
                description=description,
                price=Decimal(price),
                category=category,
                stock_type=stock_type,
                available_sizes=available_sizes,
                stock_quantity=int(stock_quantity),
                purchase_cost=Decimal(purchase_cost) if purchase_cost else None,
                supplier_cost=Decimal(supplier_cost) if supplier_cost else None,
                image=main_image if main_image else None,
            )

            # Handle additional images
            additional_images = request.FILES.getlist('additional_images')
            for idx, img_file in enumerate(additional_images):
                ProductImage.objects.create(
                    product=product,
                    image=img_file,
                    order=idx,
                )

            messages.success(request, f'Product "{product.name}" added successfully!')
            return redirect('manage_products')

        except Exception as e:
            messages.error(request, f'Error adding product: {str(e)}')
            return redirect('add_product')

    return render(request, 'parlour/add_product.html')

@login_required
@user_passes_test(is_staff_user)
def edit_product(request, product_id):
    """Edit existing product"""
    product = get_object_or_404(Product, id=product_id)
    
    if request.method == 'POST':
        try:
            # Update product fields
            product.name = request.POST.get('name')
            product.description = request.POST.get('description')
            product.price = Decimal(request.POST.get('price'))
            product.category = request.POST.get('category')
            product.available_sizes = request.POST.get('available_sizes')
            product.stock_quantity = int(request.POST.get('stock_quantity'))
            
            # Update main image if provided
            main_image = request.FILES.get('main_image')
            if main_image:
                product.image = main_image
            
            product.save()
            
            # Handle additional images
            additional_images = request.FILES.getlist('additional_images')
            for idx, img_file in enumerate(additional_images):
                ProductImage.objects.create(
                    product=product,
                    image=img_file,
                    order=product.additional_images.count() + idx
                )
            
            messages.success(request, f'Product "{product.name}" updated successfully!')
            return redirect('manage_products')
            
        except Exception as e:
            messages.error(request, f'Error updating product: {str(e)}')
    
    context = {
        'product': product
    }
    return render(request, 'parlour/edit_product.html', context)


@login_required
@user_passes_test(is_staff_user)
def delete_product(request, product_id):
    """Delete product"""
    product = get_object_or_404(Product, id=product_id)
    
    if request.method == 'POST':
        product_name = product.name
        product.delete()
        messages.success(request, f'Product "{product_name}" deleted successfully!')
        return redirect('manage_products')
    
    context = {
        'product': product
    }
    return render(request, 'parlour/delete_product.html', context)


@login_required
@user_passes_test(is_staff_user)
def delete_product_image(request, image_id):
    """Delete additional product image"""
    image = get_object_or_404(ProductImage, id=image_id)
    product_id = image.product.id
    
    image.delete()
    messages.success(request, 'Image deleted successfully!')
    return redirect('edit_product', product_id=product_id)

def ad_click(request, ad_id):
    """Track ad clicks and redirect"""
    ad = get_object_or_404(Advertisement, id=ad_id)
    ad.increment_clicks()
    
    # Record click in session
    session_key = request.session.session_key
    if session_key:
        AdImpression.objects.filter(
            advertisement=ad,
            session_key=session_key
        ).update(clicked=True)
    
    if ad.button_url:
        return redirect(ad.button_url)
    return redirect('home')

def add_to_cart(request, product_id):
    if request.method == 'POST':
        product = get_object_or_404(Product, id=product_id)
        quantity = int(request.POST.get('quantity', 1))
        size = request.POST.get('size', '')

        # ── Get correct price for this user ──
        price = product.get_price_for_user(request.user)

        cart = request.session.get('cart', {})
        cart_key = f"{product_id}_{size}"

        if cart_key in cart:
            cart[cart_key]['quantity'] += quantity
        else:
            cart[cart_key] = {
                'product_id': product_id,
                'name': product.name,
                'price': str(price),
                'original_price': str(product.price),
                'is_promo_price': price < product.price,
                'quantity': quantity,
                'size': size
            }

        request.session['cart'] = cart
        messages.success(request, f'{product.name} added to cart!')
        return redirect('cart')

    return redirect('home')


def cart(request):
    cart = request.session.get('cart', {})
    cart_items = []
    total = 0

    # Get promo info for display
    promo_info = None
    if request.user.is_authenticated:
        try:
            promo = request.user.promousage
            if promo.is_active:
                promo_info = {
                    'remaining': promo.remaining_promo_purchases(),
                    'count': promo.promo_purchases_count,
                }
        except Exception:
            pass

    for key, item in cart.items():
        product = Product.objects.get(id=item['product_id'])
        subtotal = float(item['price']) * item['quantity']
        total += subtotal

        cart_items.append({
            'key': key,
            'product': product,
            'quantity': item['quantity'],
            'size': item['size'],
            'price': item['price'],
            'original_price': item.get('original_price', item['price']),
            'is_promo_price': item.get('is_promo_price', False),
            'subtotal': subtotal
        })

    context = {
        'cart_items': cart_items,
        'total': total,
        'promo_info': promo_info,
    }
    return render(request, 'parlour/cart.html', context)


def remove_from_cart(request, cart_key):
    cart = request.session.get('cart', {})
    if cart_key in cart:
        del cart[cart_key]
        request.session['cart'] = cart
        messages.success(request, 'Item removed from cart!')
    return redirect('cart')

@login_required

def checkout(request):
    cart = request.session.get('cart', {})
    
    if not cart:
        messages.warning(request, 'Your cart is empty!')
        return redirect('cart')
    
    if request.method == 'POST':
        customer_name = request.POST.get('customer_name')
        phone_number = request.POST.get('phone_number')
        email = request.POST.get('email')
        delivery_address = request.POST.get('delivery_address')
        payment_method = request.POST.get('payment_method')
        
        # Check stock availability
        for key, item in cart.items():
            product = Product.objects.get(id=item['product_id'])
            if product.stock_quantity < item['quantity']:
                messages.error(request, f'Sorry, only {product.stock_quantity} units of {product.name} available in stock.')
                return redirect('cart')
        
                # ── Calculate total using cart prices (already promo-adjusted) ──
        order_total = sum(float(item['price']) * item['quantity'] for item in cart.values())

        # ── Update promo counter if user has active promo ──
        if request.user.is_authenticated:
            try:
                promo = request.user.promousage
                if promo.is_active:
                    # Count total products in this order
                    total_products = sum(item['quantity'] for item in cart.values())
                    promo.use_promo(total_products)
            except Exception:
                pass

        # Store order details in session for payment processing
        request.session['pending_order'] = {
            'customer_name': customer_name,
            'phone_number': phone_number,
            'email': email,
            'delivery_address': delivery_address,
            'payment_method': payment_method,
            'cart': cart,
            'total': order_total
        }
        # If user is authenticated, save the entered details to their profile
        if request.user.is_authenticated:
            try:
                profile = request.user.profile
                profile.phone_number = phone_number
                profile.delivery_address = delivery_address
                if not profile.default_delivery_location and '📍' not in delivery_address:
                    # Simple extraction of location (you can make this more sophisticated)
                    parts = delivery_address.split(',')
                    if len(parts) > 0:
                        profile.default_delivery_location = parts[0].strip()[:200]
                profile.save()
            except Profile.DoesNotExist:
                # If profile doesn't exist, it will be created automatically 
                # by the signal upon user login, so we can pass here.
                pass
        
        # Redirect based on payment method
        if payment_method == 'mpesa':
            return redirect('mpesa_payment')
        else:  # cash on delivery
            return redirect('process_cash_order')
    
    # GET request - prepare the form
    cart_items = []
    total = 0
    
    for key, item in cart.items():
        product = Product.objects.get(id=item['product_id'])
        subtotal = float(item['price']) * item['quantity']
        total += subtotal
        
        cart_items.append({
            'product': product,
            'quantity': item['quantity'],
            'size': item['size'],
            'price': item['price'],
            'subtotal': subtotal
        })
    
    # Check if user is authenticated and has profile data
    profile_data = {
        'customer_name': '',
        'phone_number': '',
        'email': '',
        'delivery_address': '',
        'has_profile': False,
        'profile_complete': False
    }
    
    if request.user.is_authenticated:
        try:
            profile = request.user.profile
            
            # Get customer name from user object
            if request.user.first_name or request.user.last_name:
                customer_name = f"{request.user.first_name} {request.user.last_name}".strip()
            else:
                customer_name = request.user.username
            
            profile_data = {
                'customer_name': customer_name,
                'phone_number': profile.phone_number or '',
                'email': request.user.email or '',
                'delivery_address': profile.delivery_address or '',
                'has_profile': True,
                'profile_complete': bool(profile.phone_number and profile.delivery_address)
            }
        except Profile.DoesNotExist:
            # Profile doesn't exist, create it
            profile = Profile.objects.create(user=request.user)
            profile_data = {
                'customer_name': request.user.username,
                'phone_number': '',
                'email': request.user.email or '',
                'delivery_address': '',
                'has_profile': True,
                'profile_complete': False
            }
    
    context = {
        'cart_items': cart_items,
        'total': total,
        'profile_data': profile_data,
        'is_authenticated': request.user.is_authenticated
    }
    return render(request, 'parlour/checkout.html', context)


from decimal import Decimal, InvalidOperation
from decimal import Decimal

def process_cash_order(request):
    """Process cash on delivery orders"""
    pending_order = request.session.get('pending_order')
    
    if not pending_order:
        messages.error(request, 'No pending order found.')
        return redirect('cart')
    
    # Create order
    order = Order.objects.create(
        customer_name=pending_order['customer_name'],
        phone_number=pending_order['phone_number'],
        email=pending_order['email'],
        delivery_address=pending_order['delivery_address']
    )
    
    # Create order items and reduce stock
    for key, item in pending_order['cart'].items():
        product = get_object_or_404(Product, id=item['product_id'])
        
        OrderItem.objects.create(
            order=order,
            product=product,
            quantity=item['quantity'],
            price=Decimal(str(item['price'])),  # ← use cart price (already promo-adjusted)
            size=item['size']
        )
        
        # Safely reduce stock quantity to prevent race conditions
        if product.stock_type == 'ready':
            product.stock_quantity = F('stock_quantity') - item['quantity']
            product.save(update_fields=['stock_quantity'])
    
    # Send confirmation email
    email_sent = send_order_confirmation_email(order)
    
    if email_sent:
        messages.success(request, 'Order placed successfully! Confirmation email sent.')
    else:
        messages.warning(request, 'Order placed successfully! But confirmation email could not be sent.')
    
    # Clear session
    request.session['cart'] = {}
    del request.session['pending_order']
    
    return redirect('order_confirmation', order_id=order.id)



def mpesa_payment(request):
    """M-Pesa payment page"""
    pending_order = request.session.get('pending_order')
    
    if not pending_order:
        messages.error(request, 'No pending order found.')
        return redirect('cart')
    
    context = {
        'pending_order': pending_order
    }
    return render(request, 'parlour/mpesa_payment.html', context)


def order_confirmation(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    context = {
        'order': order
    }
    return render(request, 'parlour/order_confirmation.html', context)

@login_required
@staff_member_required
def order_tracking(request):
    order = None
    
    if request.method == 'POST':
        order_id = request.POST.get('order_id')
        try:
            order = Order.objects.get(id=order_id)
        except Order.DoesNotExist:
            messages.error(request, 'Order not found!')
    
    context = {
        'order': order
    }
    return render(request, 'parlour/order_tracking.html', context)


def user_login(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                next_url = request.GET.get('next', 'home')
                messages.success(request, f'Welcome back, {username}!')
                return redirect(next_url)
        else:
            messages.error(request, 'Invalid username or password.')
    else:
        form = AuthenticationForm()
    
    return render(request, 'parlour/login.html', {'form': form})


from django.contrib.auth import login
from django.contrib.auth.forms import UserCreationForm
from django.shortcuts import render, redirect
from django.contrib import messages
from django.conf import settings
from django.core.mail import EmailMessage
from django.contrib.auth.models import User
from django.db import IntegrityError
import logging
import random
import string
from .models import EmailOTP
from django import forms

logger = logging.getLogger(__name__)


def generate_otp():
    """Generate a 6-digit OTP"""
    return ''.join(random.choices(string.digits, k=6))


def send_otp_email_to_address(email, username, otp):
    """Send OTP email with error handling and logging"""
    try:
        subject = "Your OTP Verification Code - Hoka's Parlour"

        html_message = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: 'Inter', Arial, sans-serif;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    margin: 0;
                    padding: 20px;
                }}
                .container {{
                    max-width: 600px;
                    margin: 0 auto;
                    background: white;
                    border-radius: 20px;
                    padding: 40px;
                    box-shadow: 0 20px 40px rgba(0,0,0,0.1);
                }}
                .header {{
                    text-align: center;
                    margin-bottom: 30px;
                }}
                .logo {{
                    font-size: 32px;
                    font-weight: 800;
                    color: #333;
                    font-family: 'Playfair Display', serif;
                }}
                .logo span {{
                    color: #7b2eda;
                }}
                .otp-code {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    font-size: 48px;
                    font-weight: bold;
                    padding: 20px;
                    text-align: center;
                    border-radius: 16px;
                    letter-spacing: 10px;
                    margin: 30px 0;
                    font-family: monospace;
                }}
                .footer {{
                    text-align: center;
                    margin-top: 30px;
                    color: #666;
                    font-size: 14px;
                    border-top: 1px solid #eee;
                    padding-top: 20px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <div class="logo">HOKA'S<span>PARLOUR</span></div>
                    <p style="color: #666; margin-top: 10px;">Welcome to Hoka's Parlour!</p>
                </div>

                <h2 style="text-align: center; color: #333;">Email Verification</h2>

                <p style="color: #666; font-size: 16px; line-height: 1.6;">
                    Hello <strong>{username}</strong>,<br><br>
                    Thank you for signing up! Please use the OTP code below to verify your email address:
                </p>

                <div class="otp-code">
                    {otp}
                </div>

                <p style="color: #666; font-size: 16px; line-height: 1.6;">
                    This code will expire in 10 minutes.<br>
                    If you didn't request this, please ignore this email.
                </p>

                <div class="footer">
                    <p>© 2026 Hoka's Parlour. All rights reserved.</p>
                    <p style="color: #999; font-size: 12px;">Rongai, Kajiado County, Kenya</p>
                </div>
            </div>
        </body>
        </html>
        """

        email_msg = EmailMessage(
            subject=subject,
            body=html_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[email],
        )
        email_msg.content_subtype = "html"
        sent_count = email_msg.send(fail_silently=False)

        logger.info(f"Email sent successfully to {email}. Result: {sent_count}")
        return True

    except Exception as e:
        logger.error(f"Failed to send email to {email}: {str(e)}")
        print(f"\n{'='*50}")
        print(f"🔐 OTP for {email}: {otp}")
        print(f"{'='*50}\n")
        raise e


def user_signup(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        form.fields['email'] = forms.EmailField(required=True)

        if form.is_valid():
            email = form.cleaned_data['email']
            username = form.cleaned_data['username']

            # Check if email already exists
            if User.objects.filter(email=email).exists():
                messages.error(request, 'This email is already registered.')
                return render(request, 'parlour/signup.html', {'form': form})

            # Check if username already exists
            if User.objects.filter(username=username).exists():
                messages.error(request, 'This username is already taken.')
                return render(request, 'parlour/signup.html', {'form': form})

            # Generate OTP
            otp = generate_otp()

            # Store signup data in session (no user created yet)
            request.session['pending_signup'] = {
                'username': username,
                'email': email,
                'password': form.cleaned_data['password1'],
                'otp': otp,
            }

            # Send OTP email
            try:
                send_otp_email_to_address(email, username, otp)
                messages.success(request, f'✅ An OTP has been sent to {email}. Please check your inbox (and spam folder).')
            except Exception as e:
                messages.warning(request, f'⚠️ Email sending failed. For development, your OTP is: {otp}')
                logger.error(f"Email sending failed: {e}")

            return redirect('verify_otp')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = UserCreationForm()
        form.fields['email'] = forms.EmailField(required=True)

    return render(request, 'parlour/signup.html', {'form': form})


def verify_otp(request):
    pending = request.session.get('pending_signup')

    if not pending:
        messages.error(request, 'Session expired. Please sign up again.')
        return redirect('signup')

    if request.method == 'POST':
        otp_input = request.POST.get('otp')
        action = request.POST.get('action')

        # Resend OTP
        if action == 'resend':
            new_otp = generate_otp()
            request.session['pending_signup']['otp'] = new_otp
            request.session.modified = True

            try:
                send_otp_email_to_address(pending['email'], pending['username'], new_otp)
                messages.success(request, f"✅ A new OTP has been sent to {pending['email']}")
            except Exception as e:
                messages.warning(request, f'⚠️ New OTP: {new_otp}')

            return redirect('verify_otp')

        # Verify OTP
        if otp_input == pending.get('otp'):
            try:
                # OTP correct — now create the user
                user = User.objects.create_user(
                    username=pending['username'],
                    email=pending['email'],
                    password=pending['password'],
                )
                user.is_active = True
                user.save()

                # Clear pending signup session
                del request.session['pending_signup']

                # Log the user in
                login(request, user)

                # ── Referral code handling ────────────────────────────
                referral_code = request.session.pop('referral_code', None)
                if referral_code:
                    try:
                        agent = Agent.objects.get(referral_code=referral_code, status='approved')
                        PromoUsage.objects.create(
                            user=user,
                            agent=agent,
                            promo_purchases_count=0,
                            is_active=True
                        )
                        # Referral code applied — no need to show popup
                        profile, _ = Profile.objects.get_or_create(user=user)
                        profile.promo_popup_shown = True
                        profile.show_promo_popup = False
                        profile.save(update_fields=['promo_popup_shown', 'show_promo_popup'])
                        messages.success(request, "🎉 Account verified! Promo code applied — enjoy discount pricing on your first 5 products!")
                    except Agent.DoesNotExist:
                        # Invalid referral code — show popup so user can enter manually
                        profile, _ = Profile.objects.get_or_create(user=user)
                        profile.show_promo_popup = True
                        profile.promo_popup_shown = False
                        profile.save(update_fields=['show_promo_popup', 'promo_popup_shown'])
                        messages.success(request, "🎉 Account verified successfully! Welcome to Hoka's Parlour!")
                else:
                    # No referral code — show promo popup on home page
                    profile, _ = Profile.objects.get_or_create(user=user)
                    profile.show_promo_popup = True
                    profile.promo_popup_shown = False
                    profile.save(update_fields=['show_promo_popup', 'promo_popup_shown'])
                    messages.success(request, "🎉 Account verified successfully! Welcome to Hoka's Parlour!")
                # ─────────────────────────────────────────────────────

                return redirect('home')

            except IntegrityError as e:
                logger.error(f"Account creation failed after OTP verification: {e}")
                messages.error(request, 'An error occurred while creating your account. Please sign up again.')
                del request.session['pending_signup']
                return redirect('signup')
        else:
            messages.error(request, '❌ Invalid OTP. Please try again.')

    return render(request, 'parlour/verify_otp.html', {'email': pending.get('email')})
def user_logout(request):
    logout(request)
    messages.success(request, 'You have been logged out.')
    return redirect('home')



from .lipana_utils import stk_push



from decimal import Decimal
from django.http import JsonResponse
from .models import MpesaPayment

def mpesa_payment(request):
    pending_order = request.session.get('pending_order')

    if not pending_order:
        messages.error(request, 'No pending order found.')
        return redirect('cart')

    stk_result = None
    stk_error = None

    # Only block re-submission on GET, not POST
    existing_checkout_id = request.session.get('checkout_request_id')

    if request.method == 'POST':
        # Always allow a fresh POST (user clicked Pay button)
        # Clear any old checkout_request_id first
        if 'checkout_request_id' in request.session:
            del request.session['checkout_request_id']

        phone = pending_order['phone_number']
        amount = pending_order['total']
        temp_ref = f"TEMP{request.session.session_key[-6:]}"
        result = stk_push(phone, amount, temp_ref)

        if result['success']:
            checkout_request_id = result['checkout_request_id']

            MpesaPayment.objects.create(
                checkout_request_id=checkout_request_id,
                phone_number=phone,
                amount=Decimal(str(amount)),
                order_details=pending_order,  # <-- Save order details to the model
                session_key=request.session.session_key,
                status='pending'
            )

            request.session['checkout_request_id'] = checkout_request_id
            
            # Redirect to the new processing page
            return redirect('payment_processing', checkout_id=checkout_request_id)
        else:
            stk_error = result['message']
            messages.error(request, f'STK Push failed: {result["message"]}')

    # For GET request or if STK push fails on POST
    context = {
        'pending_order': pending_order,
        'stk_error': stk_error,
    }
    return render(request, 'parlour/mpesa_payment.html', context)

def check_payment_status(request):
    """
    API endpoint to check payment status.
    This view is now idempotent and resilient to session loss.
    """
    checkout_request_id = request.session.get('checkout_request_id')
    
    if not checkout_request_id:
        return JsonResponse({'status': 'error', 'message': 'No payment session found.'})
    
    try:
        payment = MpesaPayment.objects.get(checkout_request_id=checkout_request_id)
        
        # --- SUCCESS ---
        if payment.status == 'success':
            # If order is already created (by webhook or another poll), just return success
            if payment.order:
                # Ensure session is cleaned up even if order was created by webhook
                if 'pending_order' in request.session: del request.session['pending_order']
                if 'cart' in request.session: request.session['cart'] = {}
                if 'checkout_request_id' in request.session: del request.session['checkout_request_id']
                
                return JsonResponse({
                    'status': 'success',
                    'message': 'Payment confirmed. Order already processed.',
                    'redirect_url': reverse('order_confirmation', args=[payment.order.id])
                })

            # If order does not exist, create it now.
            # This is the primary order creation logic.
            order_data = payment.order_details
            if not order_data:
                return JsonResponse({'status': 'error', 'message': 'Critical: Order details not found in payment record.'})

            # Create the order
            order = Order.objects.create(
                customer_name=order_data['customer_name'],
                phone_number=order_data['phone_number'],
                email=order_data['email'],
                delivery_address=order_data['delivery_address'],
                is_paid=True  # Mark order as paid
            )

            # Link payment to the new order
            payment.order = order
            payment.save(update_fields=['order'])

            # Create order items and reduce stock
            for key, item in order_data['cart'].items():
                try:
                    product = Product.objects.get(id=item['product_id'])
                    OrderItem.objects.create(
                        order=order,
                        product=product,
                        quantity=item['quantity'],
                        price=product.price,  # Use fresh price from DB
                        size=item['size']
                    )
                    # Safely reduce stock for 'ready' items
                    if product.stock_type == 'ready':
                        product.stock_quantity = F('stock_quantity') - item['quantity']
                        product.save(update_fields=['stock_quantity'])
                except Product.DoesNotExist:
                    # Log if a product in the cart doesn't exist anymore
                    logger.warning(f"Product with ID {item['product_id']} not found during order creation for Order #{order.id}.")
                    continue

            # Send confirmation email
            send_order_confirmation_email(order)
            
            # Clear session data *after* successful processing
            if 'pending_order' in request.session: del request.session['pending_order']
            request.session['cart'] = {}
            if 'checkout_request_id' in request.session: del request.session['checkout_request_id']
            
            return JsonResponse({
                'status': 'success',
                'message': 'Payment confirmed and order created.',
                'redirect_url': reverse('order_confirmation', args=[order.id])
            })
        
        # --- FAILED ---
        elif payment.status == 'failed':
            return JsonResponse({
                'status': 'failed',
                'message': payment.result_desc or 'Payment failed at provider.',
                'redirect_url': reverse('payment_failed')
            })
        
        # --- CANCELLED ---
        elif payment.status == 'cancelled':
            return JsonResponse({
                'status': 'cancelled',
                'message': 'Payment was cancelled by the user.',
                'redirect_url': reverse('payment_failed')
            })
        
        # --- PENDING ---
        return JsonResponse({'status': 'pending', 'message': 'Waiting for payment confirmation...'})
        
    except MpesaPayment.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Payment record not found. Please try again.'})


def mpesa_callback(request):
    """Handle M-Pesa payment callback from Safaricom"""
    import json
    from django.utils import timezone
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            callback = data.get('Body', {}).get('stkCallback', {})
            
            result_code = callback.get('ResultCode')
            result_desc = callback.get('ResultDesc')
            checkout_request_id = callback.get('CheckoutRequestID')
            
            print(f"M-Pesa Callback - ResultCode: {result_code}, Desc: {result_desc}")
            print(f"CheckoutRequestID: {checkout_request_id}")
            
            # Find payment record
            try:
                payment = MpesaPayment.objects.get(checkout_request_id=checkout_request_id)
                
                payment.result_code = result_code
                payment.result_desc = result_desc
                
                if result_code == 0:
                    # Payment successful
                    payment.status = 'success'
                    
                    metadata = callback.get('CallbackMetadata', {}).get('Item', [])
                    
                    for item in metadata:
                        if item.get('Name') == 'Amount':
                            payment.amount = Decimal(str(item.get('Value')))
                        elif item.get('Name') == 'MpesaReceiptNumber':
                            payment.mpesa_receipt_number = item.get('Value')
                        elif item.get('Name') == 'TransactionDate':
                            # Format: 20210101120000
                            trans_date_str = str(item.get('Value'))
                            payment.transaction_date = timezone.datetime.strptime(
                                trans_date_str, '%Y%m%d%H%M%S'
                            )
                    
                    print(f"Payment successful - Receipt: {payment.mpesa_receipt_number}")
                    
                elif result_code == 1032:
                    # User cancelled
                    payment.status = 'cancelled'
                    print(f"Payment cancelled by user")
                else:
                    # Payment failed
                    payment.status = 'failed'
                    print(f"Payment failed - {result_desc}")
                
                payment.save()
                
            except MpesaPayment.DoesNotExist:
                print(f"Payment record not found for: {checkout_request_id}")
                
        except Exception as e:
            print(f"Callback error: {e}")
    
    return JsonResponse({'ResultCode': 0, 'ResultDesc': 'Success'})


def confirm_mpesa_payment(request):
    """
    Manual confirmation fallback if auto-processing via webhook/polling fails.
    This is now idempotent and uses the secure order details from the payment model.
    """
    if request.method != 'POST':
        return redirect('checkout')

    checkout_request_id = request.session.get('checkout_request_id')
    if not checkout_request_id:
        messages.error(request, 'Your payment session has expired. Please try checking out again.')
        return redirect('checkout')

    try:
        with transaction.atomic():
            payment = MpesaPayment.objects.select_for_update().get(checkout_request_id=checkout_request_id)

            # Idempotency: If order already exists, don't create another one.
            if payment.order:
                messages.info(request, f'Your order #{payment.order.id} has already been processed.')
                return redirect('order_confirmation', order_id=payment.order.id)

            order_data = payment.order_details
            if not order_data:
                messages.error(request, 'Critical error: Could not find the details for your order. Please contact support.')
                return redirect('checkout')

            # Create order since it doesn't exist
            order = Order.objects.create(
                customer_name=order_data['customer_name'],
                phone_number=order_data['phone_number'],
                email=order_data['email'],
                delivery_address=order_data['delivery_address'],
                is_paid=True  # Manually confirmed as paid
            )

            # Link payment and update its status
            payment.order = order
            payment.status = 'success' # Mark as success since it's a manual confirmation
            payment.result_desc = 'Manually confirmed by user.'
            payment.save()

            # Create order items and reduce stock
            for key, item in order_data['cart'].items():
                try:
                    product = Product.objects.get(id=item['product_id'])
                    OrderItem.objects.create(
                        order=order,
                        product=product,
                        quantity=item['quantity'],
                        price=product.price,  # Use fresh price
                        size=item['size']
                    )
                    if product.stock_type == 'ready':
                        product.stock_quantity = F('stock_quantity') - item['quantity']
                        product.save(update_fields=['stock_quantity'])
                except Product.DoesNotExist:
                    logger.warning(f"Product ID {item['product_id']} not found for manually confirmed Order #{order.id}.")
                    continue
            
            email_sent = send_order_confirmation_email(order)
            if email_sent:
                messages.success(request, 'Payment confirmed! Your order has been placed. A confirmation email has been sent.')
            else:
                messages.warning(request, 'Payment confirmed! Your order has been placed, but the confirmation email could not be sent.')
            
            # Clean up session
            if 'cart' in request.session: request.session['cart'] = {}
            if 'pending_order' in request.session: del request.session['pending_order']
            if 'checkout_request_id' in request.session: del request.session['checkout_request_id']
            
            return redirect('order_confirmation', order_id=order.id)

    except MpesaPayment.DoesNotExist:
        messages.error(request, 'Could not find a matching payment record. Please try the checkout process again.')
        return redirect('checkout')
    except Exception as e:
        logger.error(f"Error in manual confirm_mpesa_payment: {e}")
        messages.error(request, 'An unexpected error occurred. Please contact support.')
        return redirect('checkout')



#===========================================LIPANA.DEV===========================================

import hmac, hashlib, json, os
from decimal import Decimal
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.contrib import messages
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from .models import MpesaPayment, Order, OrderItem, Product
from .email_utils import send_order_confirmation_email

@csrf_exempt
def lipana_webhook(request):
    """
    Handles Lipana payment events.
    Primary, idempotent order creation mechanism for M-Pesa.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    # 1. Verify signature
    signature = request.headers.get('X-Lipana-Signature', '')
    webhook_secret = os.getenv('LIPANA_WEBHOOK_SECRET', '')
    if webhook_secret and signature:
        expected = hmac.new(webhook_secret.encode(), request.body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            logger.warning("Lipana webhook signature verification failed.")
            return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        data = json.loads(request.body)
        logger.info(f"Lipana webhook payload: {json.dumps(data)}")

        event = data.get('event')
        event_data = data.get('data', {})

        checkout_request_id = (
            event_data.get('transaction_id') or
            event_data.get('transactionId') or
            event_data.get('checkoutRequestID') or
            event_data.get('CheckoutRequestID') or
            event_data.get('checkout_request_id') or
            data.get('transactionId')
        )

        if not checkout_request_id:
            logger.error(f"Lipana webhook missing transaction ID. Full payload: {json.dumps(data)}")
            return JsonResponse({'status': 'ok'})

        logger.info(f"Lipana webhook: event={event}, checkout_request_id={checkout_request_id}")

        with transaction.atomic():
            try:
                payment = MpesaPayment.objects.select_for_update().get(checkout_request_id=checkout_request_id)
            except MpesaPayment.DoesNotExist:
                logger.error(f"Lipana webhook: MpesaPayment not found for: {checkout_request_id}")
                return JsonResponse({'status': 'ok'})

            if event == 'transaction.success':
                payment.status = 'success'
                payment.mpesa_receipt_number = event_data.get('transaction_id', '')
                payment.amount = Decimal(str(event_data.get('amount', payment.amount)))
                ts = event_data.get('timestamp')
                if ts:
                    payment.transaction_date = timezone.datetime.fromisoformat(ts.replace('Z', '+00:00'))

                # ── ALWAYS mark linked order as paid first ──
                if payment.order and not payment.order.is_paid:
                    payment.order.is_paid = True
                    payment.order.save(update_fields=['is_paid'])
                    logger.info(f"Webhook: Order #{payment.order.id} marked as paid.")

                # ── Save payment status immediately ──
                payment.save()

                # ── Idempotency: skip order CREATION if order already exists ──
                if payment.order:
                    logger.info(f"Webhook: Order already exists for {checkout_request_id}. Skipping creation.")
                    return JsonResponse({'status': 'ok'})

                # ── No order yet — create from order_details ──
                order_data = payment.order_details
                if not order_data:
                    logger.critical(f"CRITICAL: Payment success for {checkout_request_id} but no order_details found!")
                    return JsonResponse({'status': 'ok'})

                # Create Order
                order = Order.objects.create(
                    customer_name=order_data['customer_name'],
                    phone_number=order_data['phone_number'],
                    email=order_data['email'],
                    delivery_address=order_data['delivery_address'],
                    is_paid=True
                )
                payment.order = order
                payment.save(update_fields=['order'])

                # Create OrderItems and reduce stock
                for key, item in order_data['cart'].items():
                    try:
                        product = Product.objects.get(id=item['product_id'])
                        OrderItem.objects.create(
                            order=order,
                            product=product,
                            quantity=item['quantity'],
                            price=product.price,
                            size=item['size']
                        )
                        if product.stock_type == 'ready':
                            product.stock_quantity = F('stock_quantity') - item['quantity']
                            product.save(update_fields=['stock_quantity'])
                    except Product.DoesNotExist:
                        logger.warning(f"Product ID {item['product_id']} not found for Order #{order.id}.")
                        continue

                send_order_confirmation_email(order)
                logger.info(f"Webhook: Order #{order.id} created for {checkout_request_id}.")

            elif event == 'transaction.failed':
                payment.status = 'failed'
                payment.result_desc = event_data.get('message', 'Payment failed')
                payment.save()

            elif event == 'transaction.cancelled':
                payment.status = 'cancelled'
                payment.result_desc = event_data.get('message', 'Payment cancelled')
                payment.save()

            elif event == 'transaction.pending':
                payment.status = 'pending'
                payment.save()

            else:
                logger.info(f"Lipana webhook: Ignoring unhandled event '{event}'")

    except Exception as e:
        logger.error(f"General error in Lipana webhook: {e}", exc_info=True)

    return JsonResponse({'status': 'ok'})

# parlour/views.py - Add these imports at the top
from django.contrib.auth.decorators import login_required
from django.contrib.auth import update_session_auth_hash
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from .models import Profile, Order, OrderHistory
from .forms import UserUpdateForm, ProfileUpdateForm, ChangePasswordForm

# Profile view - view profile
@login_required
def profile(request):
    """User profile page"""
    user = request.user
    profile = user.profile
    
    # Get user's orders
    orders = Order.objects.filter(email=user.email).order_by('-created_at')[:10]
    
    # Get order history
    order_history = OrderHistory.objects.filter(user=user).select_related('order')[:5]
    
    context = {
        'user': user,
        'profile': profile,
        'orders': orders,
        'order_history': order_history,
        'active_tab': 'profile'
    }
    return render(request, 'parlour/profile.html', context)


# Edit profile
@login_required
def edit_profile(request):
    """Edit user profile"""
    if request.method == 'POST':
        user_form = UserUpdateForm(request.POST, instance=request.user)
        profile_form = ProfileUpdateForm(
            request.POST, 
            request.FILES, 
            instance=request.user.profile
        )
        
        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()
            messages.success(request, 'Your profile has been updated successfully!')
            return redirect('profile')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        user_form = UserUpdateForm(instance=request.user)
        profile_form = ProfileUpdateForm(instance=request.user.profile)
    
    context = {
        'user_form': user_form,
        'profile_form': profile_form,
        'active_tab': 'edit'
    }
    return render(request, 'parlour/edit_profile.html', context)


# Change password
@login_required
def change_password(request):
    """Change user password"""
    if request.method == 'POST':
        form = ChangePasswordForm(request.POST)
        if form.is_valid():
            user = request.user
            old_password = form.cleaned_data.get('old_password')
            new_password = form.cleaned_data.get('new_password')
            
            if user.check_password(old_password):
                user.set_password(new_password)
                user.save()
                update_session_auth_hash(request, user)  # Keep user logged in
                messages.success(request, 'Your password was successfully updated!')
                return redirect('profile')
            else:
                messages.error(request, 'Current password is incorrect.')
    else:
        form = ChangePasswordForm()
    
    context = {
        'form': form,
        'active_tab': 'password'
    }
    return render(request, 'parlour/change_password.html', context)


# Order history
@login_required
def order_history(request):
    """View full order history"""
    user = request.user
    
    # Get orders by email or user association
    orders = Order.objects.filter(email=user.email).order_by('-created_at')
    
    # Record that user viewed these orders
    for order in orders:
        OrderHistory.objects.get_or_create(user=user, order=order)
    
    context = {
        'orders': orders,
        'active_tab': 'orders'
    }
    return render(request, 'parlour/order_history.html', context)


# Save current cart items for later
@login_required
def save_for_later(request):
    """Save cart items to user profile for later purchase"""
    cart = request.session.get('cart', {})
    
    if cart:
        # You could implement a saved items model here
        request.session['saved_cart'] = cart
        request.session['cart'] = {}
        messages.success(request, 'Cart items saved for later!')
    else:
        messages.warning(request, 'Your cart is empty.')
    
    return redirect('cart')


# Load saved items
@login_required
def load_saved_items(request):
    """Load previously saved cart items"""
    saved_cart = request.session.get('saved_cart', {})
    
    if saved_cart:
        request.session['cart'] = saved_cart
        request.session['saved_cart'] = {}
        messages.success(request, 'Saved items loaded to cart!')
    else:
        messages.warning(request, 'No saved items found.')
    
    return redirect('cart')


from django.core.mail import EmailMessage
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

def contact(request):
    """Contact Us page with styled HTML email handling"""
    if request.method == 'POST':
        full_name = request.POST.get('full_name')
        email = request.POST.get('email')
        phone = request.POST.get('phone', '')
        subject = request.POST.get('subject')
        order_number = request.POST.get('order_number', '')
        message = request.POST.get('message')

        # Email to store owner (Notification)
        admin_email_subject = f"New Contact: {subject} - {full_name}"
        
        admin_html_message = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: 'Inter', Arial, sans-serif;
                    background: #f5f5f5;
                    margin: 0;
                    padding: 20px;
                }}
                .container {{
                    max-width: 600px;
                    margin: 0 auto;
                    background: white;
                    border-radius: 12px;
                    overflow: hidden;
                    box-shadow: 0 4px 12px rgba(0,0,0,0.1);
                }}
                .header {{
                    background: linear-gradient(135deg, #dc3545 0%, #c82333 100%);
                    color: white;
                    padding: 30px;
                    text-align: center;
                }}
                .header h1 {{
                    margin: 0;
                    font-size: 24px;
                }}
                .badge {{
                    display: inline-block;
                    background: rgba(255,255,255,0.2);
                    padding: 5px 15px;
                    border-radius: 20px;
                    font-size: 12px;
                    margin-top: 10px;
                }}
                .content {{
                    padding: 30px;
                }}
                .info-grid {{
                    display: grid;
                    grid-template-columns: 1fr 1fr;
                    gap: 15px;
                    margin: 20px 0;
                }}
                .info-item {{
                    background: #f8f9fa;
                    padding: 15px;
                    border-radius: 8px;
                    border-left: 3px solid #dc3545;
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
                .message-box {{
                    background: #fff3cd;
                    border: 1px solid #ffc107;
                    border-radius: 8px;
                    padding: 20px;
                    margin: 20px 0;
                }}
                .message-box h3 {{
                    color: #856404;
                    margin: 0 0 15px 0;
                    font-size: 16px;
                }}
                .footer {{
                    background: #f8f9fa;
                    padding: 20px;
                    text-align: center;
                    color: #666;
                    font-size: 13px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🔔 New Contact Form Submission</h1>
                    <div class="badge">Hoka's Parlour Website</div>
                </div>
                
                <div class="content">
                    <h2 style="color: #333; margin-bottom: 20px;">Contact Details</h2>
                    
                    <div class="info-grid">
                        <div class="info-item">
                            <strong>Full Name</strong>
                            <span>{full_name}</span>
                        </div>
                        <div class="info-item">
                            <strong>Email</strong>
                            <span>{email}</span>
                        </div>
                        <div class="info-item">
                            <strong>Phone</strong>
                            <span>{phone if phone else 'Not provided'}</span>
                        </div>
                        <div class="info-item">
                            <strong>Subject</strong>
                            <span>{subject}</span>
                        </div>
                    </div>
                    
                    {f'''
                    <div style="background: #e8f5e9; border-left: 3px solid #4caf50; padding: 12px 15px; border-radius: 4px; margin: 15px 0;">
                        <strong style="color: #2e7d32; font-size: 13px;">Order Number:</strong>
                        <span style="color: #1b5e20; font-size: 15px; margin-left: 10px;">#{order_number}</span>
                    </div>
                    ''' if order_number else ''}
                    
                    <div class="message-box">
                        <h3>📩 Message</h3>
                        <p style="color: #333; line-height: 1.6; margin: 0; white-space: pre-wrap;">{message}</p>
                    </div>
                    
                    <div style="background: #f8f9fa; padding: 15px; border-radius: 8px; margin-top: 20px;">
                        <p style="margin: 0; color: #666; font-size: 14px;">
                            <strong>Quick Actions:</strong><br>
                            Reply to: <a href="mailto:{email}" style="color: #dc3545; text-decoration: none;">{email}</a>
                            {f'<br>Call: <a href="tel:{phone}" style="color: #dc3545; text-decoration: none;">{phone}</a>' if phone else ''}
                        </p>
                    </div>
                </div>
                
                <div class="footer">
                    <p style="margin: 5px 0;">Hoka's Parlour Admin Panel</p>
                    <p style="margin: 5px 0; color: #999;">This is an automated notification</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Customer auto-reply (Styled)
        customer_html_message = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: 'Inter', Arial, sans-serif;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    margin: 0;
                    padding: 20px;
                }}
                .container {{
                    max-width: 600px;
                    margin: 0 auto;
                    background: white;
                    border-radius: 16px;
                    overflow: hidden;
                    box-shadow: 0 20px 40px rgba(0,0,0,0.15);
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
                .content {{
                    padding: 40px 30px;
                }}
                .success-box {{
                    background: #d4edda;
                    border: 1px solid #c3e6cb;
                    border-left: 4px solid #28a745;
                    padding: 20px;
                    border-radius: 8px;
                    margin: 20px 0;
                    text-align: center;
                }}
                .success-box h2 {{
                    color: #155724;
                    margin: 0 0 10px 0;
                    font-size: 22px;
                }}
                .info-box {{
                    background: #f8f9fa;
                    padding: 20px;
                    border-radius: 8px;
                    margin: 20px 0;
                }}
                .info-box h3 {{
                    color: #333;
                    margin: 0 0 15px 0;
                    font-size: 18px;
                }}
                .detail-row {{
                    display: flex;
                    justify-content: space-between;
                    padding: 10px 0;
                    border-bottom: 1px solid #e0e0e0;
                }}
                .detail-row:last-child {{
                    border-bottom: none;
                }}
                .detail-row strong {{
                    color: #666;
                }}
                .detail-row span {{
                    color: #333;
                    font-weight: 600;
                }}
                .contact-box {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 25px;
                    border-radius: 8px;
                    margin: 20px 0;
                }}
                .contact-box h3 {{
                    margin: 0 0 15px 0;
                    font-size: 18px;
                }}
                .contact-box p {{
                    margin: 8px 0;
                    font-size: 15px;
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
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <div class="logo">HOKA'S<span>PARLOUR</span></div>
                    <p style="margin: 10px 0 0 0; font-size: 16px;">Premium Fashion & Streetwear</p>
                </div>
                
                <div class="content">
                    <div class="success-box">
                        <h2>✓ Message Received!</h2>
                        <p style="color: #155724; margin: 0;">Thank you for contacting us, {full_name}</p>
                    </div>
                    
                    <p style="color: #666; line-height: 1.6; font-size: 16px;">
                        Dear <strong>{full_name}</strong>,<br><br>
                        Thank you for reaching out to Hoka's Parlour! We have successfully received your message and our team will review it shortly.
                    </p>
                    
                    <div class="info-box">
                        <h3>📋 Your Enquiry Details</h3>
                        <div class="detail-row">
                            <strong>Subject:</strong>
                            <span>{subject}</span>
                        </div>
                        <div class="detail-row">
                            <strong>Reference:</strong>
                            <span>{order_number if order_number else 'General Inquiry'}</span>
                        </div>
                        <div class="detail-row">
                            <strong>Expected Response:</strong>
                            <span>Within 24 hours</span>
                        </div>
                    </div>
                    
                    <div style="background: #fff3cd; border: 1px solid #ffc107; border-radius: 8px; padding: 20px; margin: 20px 0;">
                        <p style="color: #856404; margin: 0; line-height: 1.6;">
                            <strong>⏰ Response Time:</strong> Our team typically responds within 24 hours during business days. 
                            For urgent matters, please use the contact information below.
                        </p>
                    </div>
                    
                    <div class="contact-box">
                        <h3>📞 Need Immediate Assistance?</h3>
                        <p><strong>Email:</strong> hokasparlour@gmail.com</p>
                        <p><strong>Business Hours:</strong> Monday - Saturday, 9AM - 6PM</p>
                    </div>
                    
                    <p style="color: #666; text-align: center; font-size: 14px; margin-top: 30px;">
                        We appreciate your patience and look forward to assisting you!
                    </p>
                </div>
                
                <div class="footer">
                    <p style="font-weight: 600; color: #333; font-size: 16px;">Hoka's Parlour</p>
                    <p>Premium Fashion & Streetwear</p>
                    <p style="color: #999; font-size: 12px; margin-top: 15px;">
                        © 2026 Hoka's Parlour. All rights reserved.
                    </p>
                </div>
            </div>
        </body>
        </html>
        """

        try:
            # Send notification to admin
            admin_email = EmailMessage(
                subject=admin_email_subject,
                body=admin_html_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=['hokasparlour@gmail.com'],
            )
            admin_email.content_subtype = "html"
            admin_email.send(fail_silently=False)
            
            # Send auto-reply to customer
            customer_email = EmailMessage(
                subject="Thank you for contacting Hoka's Parlour ✓",
                body=customer_html_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[email],
            )
            customer_email.content_subtype = "html"
            customer_email.send(fail_silently=False)

            messages.success(request, '✓ Thank you! Your message has been sent. We will respond within 24 hours.')
            logger.info(f"Contact form submitted by {full_name} ({email})")

        except Exception as e:
            messages.error(request, 'Sorry, there was an error sending your message. Please try again.')
            logger.error(f"Contact form error: {e}")

        return redirect('contact')

    return render(request, 'details/contact.html')

def about(request):
    """About Us page"""
    return render(request, 'details/about.html')

def terms(request):
    """Terms and Conditions page"""
    return render(request, 'details/t&c.html')

def privacy(request):
    """Privacy Policy page"""
    return render(request, 'details/p&p.html')


def welcome(request):
    """welcome page"""
    return render(request, 'details/welcome.html')

def returns(request):
    """returns page"""
    return render(request, 'details/returns.html')

def delivery(request):
    """delivery page"""
    return render(request, 'details/delivery.html')



def google_v(request):
    """welcome page"""
    return render(request, 'details/googleb193ab12b0274614.html')



from django.http import HttpResponse
from django.views.decorators.http import require_GET

@require_GET
def robots_txt(request):
    lines = [
        "User-agent: *",
        "",
        "# Block admin areas from all crawlers",
        "Disallow: /admin/",
        "Disallow: /admin-dashboard/",
        "",
        "# Block user-specific and sensitive pages",
        "Disallow: /cart/",
        "Disallow: /checkout/",
        "Disallow: /profile/",
        "Disallow: /mpesa-payment/",
        "Disallow: /mpesa-callback/",
        "Disallow: /confirm-mpesa-payment/",
        "Disallow: /verify-otp/",
        "",
        "# Allow everything else",
        "Allow: /",
        "",
        f"Sitemap: https://hokasparlour.adcent.online/sitemap.xml",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain")







# views.py (add these new views)

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Sum
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.db import models
from .models import Product, Advertisement, AdImage, AdImpression
import json

# ... (keep your existing home, product_detail, ad_click views)

@staff_member_required
def ad_list(request):
    """List all advertisements with filters and stats"""
    # Get filter parameters
    status = request.GET.get('status', 'all')
    ad_type = request.GET.get('type', 'all')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    # Base queryset
    ads = Advertisement.objects.all().select_related()
    
    # Apply filters
    if status == 'active':
        ads = ads.filter(is_active=True)
    elif status == 'inactive':
        ads = ads.filter(is_active=False)
    
    if ad_type != 'all':
        ads = ads.filter(ad_type=ad_type)
    
    if date_from:
        ads = ads.filter(created_at__date__gte=date_from)
    if date_to:
        ads = ads.filter(created_at__date__lte=date_to)
    
    # Annotate with stats
    ads = ads.annotate(
        total_impressions=Count('adimpression'),
        total_clicks=Sum('clicks')
    )
    
    # Pagination
    paginator = Paginator(ads, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get stats for the period
    now = timezone.now()
    thirty_days_ago = now - timezone.timedelta(days=30)
    
    recent_impressions = AdImpression.objects.filter(
        viewed_at__gte=thirty_days_ago
    ).count()
    
    recent_clicks = Advertisement.objects.filter(
        updated_at__gte=thirty_days_ago
    ).aggregate(total=Sum('clicks'))['total'] or 0
    
    context = {
        'page_obj': page_obj,
        'status': status,
        'ad_type': ad_type,
        'date_from': date_from,
        'date_to': date_to,
        'ad_types': Advertisement.AD_TYPES,
        'total_ads': Advertisement.objects.count(),
        'active_ads': Advertisement.objects.filter(is_active=True).count(),
        'recent_impressions': recent_impressions,
        'recent_clicks': recent_clicks,
        'total_impressions': AdImpression.objects.count(),
        'total_clicks': Advertisement.objects.aggregate(total=Sum('clicks'))['total'] or 0,
    }
    return render(request, 'parlour/admin/ad_list.html', context)


@staff_member_required
def ad_create(request):
    """Create a new advertisement"""
    if request.method == 'POST':
        ad = Advertisement()
        ad.title = request.POST.get('title')
        ad.ad_type = request.POST.get('ad_type')
        ad.ad_category = request.POST.get('ad_category', 'main')  # ← new
        ad.target_audience = request.POST.get('target_audience', 'all')
        ad.headline = request.POST.get('headline', '')
        ad.subheadline = request.POST.get('subheadline', '')
        ad.button_text = request.POST.get('button_text', 'Shop Now')
        ad.button_color = request.POST.get('button_color', '#667eea')
        ad.order = request.POST.get('order', 0)
        ad.is_active = request.POST.get('is_active') == 'on'
        ad.show_on_mobile = request.POST.get('show_on_mobile') == 'on'
        ad.show_on_tablet = request.POST.get('show_on_tablet') == 'on'
        ad.show_on_desktop = request.POST.get('show_on_desktop') == 'on'
        ad.background_color = request.POST.get('background_color', '')
        ad.text_color = request.POST.get('text_color', '#ffffff')
        ad.overlay_opacity = request.POST.get('overlay_opacity', 0.3)

        # ── Link type (external URL or internal product) ──────────
        ad.link_type = request.POST.get('link_type', 'external')
        if ad.link_type == 'external':
            ad.button_url = request.POST.get('button_url', '')
            ad.linked_product = None
        else:
            ad.button_url = ''
            product_id = request.POST.get('linked_product')
            if product_id:
                try:
                    ad.linked_product = Product.objects.get(id=product_id)
                except Product.DoesNotExist:
                    ad.linked_product = None
            else:
                ad.linked_product = None
        # ─────────────────────────────────────────────────────────

        # ── Product category targeting ────────────────────────────
        product_category_id = request.POST.get('product_category')
        if product_category_id:
            try:
                ad.product_category = Category.objects.get(id=product_category_id)
            except Category.DoesNotExist:
                ad.product_category = None
        else:
            ad.product_category = None
        # ─────────────────────────────────────────────────────────

        # Handle dates
        if request.POST.get('start_date'):
            ad.start_date = request.POST.get('start_date')
        if request.POST.get('end_date'):
            ad.end_date = request.POST.get('end_date')

        # Handle file uploads based on ad type
        if ad.ad_type == 'single_image':
            if 'single_image' in request.FILES:
                ad.single_image = request.FILES['single_image']

        elif ad.ad_type == 'video':
            if 'video' in request.FILES:
                ad.video = request.FILES['video']
            if 'video_poster' in request.FILES:
                ad.video_poster = request.FILES['video_poster']
            ad.autoplay = request.POST.get('autoplay') == 'on'
            ad.loop = request.POST.get('loop') == 'on'

        ad.save()

        # Handle multiple images
        if ad.ad_type == 'multi_image':
            images = request.FILES.getlist('multi_images')
            for index, image in enumerate(images):
                AdImage.objects.create(
                    advertisement=ad,
                    image=image,
                    caption=request.POST.get(f'caption_{index}', ''),
                    order=index
                )

        messages.success(request, f'Advertisement "{ad.title}" created successfully!')
        return redirect('ad_detail', ad_id=ad.id)

    context = {
        'ad_types': Advertisement.AD_TYPES,
        'target_audiences': Advertisement.TARGET_AUDIENCES,
        'ad_categories': Advertisement.AD_CATEGORIES,              # ← new
        'product_categories': Category.objects.all(),              # ← new
        'all_products': Product.objects.order_by('name'),          # ← new
    }
    return render(request, 'parlour/admin/ad_form.html', context)


@staff_member_required
def ad_edit(request, ad_id):
    """Edit an existing advertisement"""
    ad = get_object_or_404(Advertisement, id=ad_id)

    if request.method == 'POST':
        ad.title = request.POST.get('title')
        ad.ad_type = request.POST.get('ad_type')
        ad.ad_category = request.POST.get('ad_category', 'main')  # ← new
        ad.target_audience = request.POST.get('target_audience', 'all')
        ad.headline = request.POST.get('headline', '')
        ad.subheadline = request.POST.get('subheadline', '')
        ad.button_text = request.POST.get('button_text', 'Shop Now')
        ad.button_color = request.POST.get('button_color', '#667eea')
        ad.order = request.POST.get('order', 0)
        ad.is_active = request.POST.get('is_active') == 'on'
        ad.show_on_mobile = request.POST.get('show_on_mobile') == 'on'
        ad.show_on_tablet = request.POST.get('show_on_tablet') == 'on'
        ad.show_on_desktop = request.POST.get('show_on_desktop') == 'on'
        ad.background_color = request.POST.get('background_color', '')
        ad.text_color = request.POST.get('text_color', '#ffffff')
        ad.overlay_opacity = request.POST.get('overlay_opacity', 0.3)

        # ── Link type ─────────────────────────────────────────────
        ad.link_type = request.POST.get('link_type', 'external')
        if ad.link_type == 'external':
            ad.button_url = request.POST.get('button_url', '')
            ad.linked_product = None
        else:
            ad.button_url = ''
            product_id = request.POST.get('linked_product')
            if product_id:
                try:
                    ad.linked_product = Product.objects.get(id=product_id)
                except Product.DoesNotExist:
                    ad.linked_product = None
            else:
                ad.linked_product = None
        # ─────────────────────────────────────────────────────────

        # ── Product category targeting ────────────────────────────
        product_category_id = request.POST.get('product_category')
        if product_category_id:
            try:
                ad.product_category = Category.objects.get(id=product_category_id)
            except Category.DoesNotExist:
                ad.product_category = None
        else:
            ad.product_category = None
        # ─────────────────────────────────────────────────────────

        # Handle dates
        if request.POST.get('start_date'):
            ad.start_date = request.POST.get('start_date')
        else:
            ad.start_date = None

        if request.POST.get('end_date'):
            ad.end_date = request.POST.get('end_date')
        else:
            ad.end_date = None

        # Handle file uploads
        if 'single_image' in request.FILES:
            ad.single_image = request.FILES['single_image']

        if 'video' in request.FILES:
            ad.video = request.FILES['video']

        if 'video_poster' in request.FILES:
            ad.video_poster = request.FILES['video_poster']

        ad.autoplay = request.POST.get('autoplay') == 'on'
        ad.loop = request.POST.get('loop') == 'on'

        ad.save()

        # Handle new multiple images
        if 'multi_images' in request.FILES:
            images = request.FILES.getlist('multi_images')
            for index, image in enumerate(images):
                AdImage.objects.create(
                    advertisement=ad,
                    image=image,
                    caption=request.POST.get(f'new_caption_{index}', ''),
                    order=ad.ad_images.count() + index
                )

        messages.success(request, f'Advertisement "{ad.title}" updated successfully!')
        return redirect('ad_detail', ad_id=ad.id)

    context = {
        'ad': ad,
        'ad_types': Advertisement.AD_TYPES,
        'target_audiences': Advertisement.TARGET_AUDIENCES,
        'ad_categories': Advertisement.AD_CATEGORIES,              # ← new
        'product_categories': Category.objects.all(),              # ← new
        'all_products': Product.objects.order_by('name'),          # ← new
    }
    return render(request, 'parlour/admin/ad_form.html', context)

# views.py - Update the ad_detail function

@staff_member_required
def ad_detail(request, ad_id):
    """View advertisement details and statistics"""
    ad = get_object_or_404(Advertisement, id=ad_id)
    
    # Get impression statistics
    impressions = AdImpression.objects.filter(advertisement=ad)
    
    # Group by date for chart
    last_30_days = timezone.now() - timezone.timedelta(days=30)
    
    # Get daily stats - FIXED VERSION
    daily_stats = []
    
    # Get all impressions in the last 30 days
    recent_impressions = impressions.filter(viewed_at__gte=last_30_days)
    
    # Create a dictionary to aggregate by date
    stats_dict = {}
    
    for impression in recent_impressions:
        # Convert to date string for grouping
        date_str = impression.viewed_at.date().strftime('%Y-%m-%d')
        
        if date_str not in stats_dict:
            stats_dict[date_str] = {
                'date': impression.viewed_at.date(),
                'count': 0,
                'clicks': 0
            }
        
        stats_dict[date_str]['count'] += 1
        if impression.clicked:
            stats_dict[date_str]['clicks'] += 1
    
    # Convert dictionary to sorted list
    daily_stats = sorted(stats_dict.values(), key=lambda x: x['date'])
    
    # Prepare chart data
    dates = []
    views_data = []
    clicks_data = []
    
    # Fill in missing dates to have a continuous 30-day chart
    for i in range(30):
        date = (last_30_days + timezone.timedelta(days=i)).date()
        date_str = date.strftime('%Y-%m-%d')
        
        dates.append(date.strftime('%Y-%m-%d'))
        
        if date_str in stats_dict:
            views_data.append(stats_dict[date_str]['count'])
            clicks_data.append(stats_dict[date_str]['clicks'])
        else:
            views_data.append(0)
            clicks_data.append(0)
    
    chart_data = {
        'dates': dates,
        'views': views_data,
        'clicks': clicks_data
    }
    
    # Get recent impressions
    recent_impressions_list = impressions.order_by('-viewed_at')[:20]
    
    # Calculate click-through rate
    total_impressions = impressions.count()
    click_through_rate = (ad.clicks / total_impressions * 100) if total_impressions > 0 else 0
    
    context = {
        'ad': ad,
        'recent_impressions': recent_impressions_list,
        'total_impressions': total_impressions,
        'click_through_rate': click_through_rate,
        'chart_data': json.dumps(chart_data),
    }
    return render(request, 'parlour/admin/ad_detail.html', context)



@staff_member_required
def ad_delete(request, ad_id):
    """Delete an advertisement"""
    ad = get_object_or_404(Advertisement, id=ad_id)
    
    if request.method == 'POST':
        title = ad.title
        ad.delete()
        messages.success(request, f'Advertisement "{title}" deleted successfully!')
        return redirect('ad_list')
    
    return render(request, 'parlour/admin/ad_confirm_delete.html', {'ad': ad})


@staff_member_required
def ad_toggle_status(request, ad_id):
    """Toggle advertisement active status"""
    ad = get_object_or_404(Advertisement, id=ad_id)
    ad.is_active = not ad.is_active
    ad.save()
    
    status = "activated" if ad.is_active else "deactivated"
    messages.success(request, f'Advertisement "{ad.title}" {status} successfully!')
    
    return redirect(request.META.get('HTTP_REFERER', 'ad_list'))


@staff_member_required
def ad_image_add(request, ad_id):
    """Add an image to a multi-image advertisement"""
    ad = get_object_or_404(Advertisement, id=ad_id)
    
    if request.method == 'POST' and 'image' in request.FILES:
        AdImage.objects.create(
            advertisement=ad,
            image=request.FILES['image'],
            caption=request.POST.get('caption', ''),
            order=ad.ad_images.count()
        )
        messages.success(request, 'Image added successfully!')
    
    return redirect('ad_edit', ad_id=ad.id)


@staff_member_required
def ad_image_delete(request, image_id):
    """Delete an image from a multi-image advertisement"""
    image = get_object_or_404(AdImage, id=image_id)
    ad_id = image.advertisement.id
    
    if request.method == 'POST':
        image.delete()
        messages.success(request, 'Image deleted successfully!')
    
    return redirect('ad_edit', ad_id=ad_id)





from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from .models import Order


@staff_member_required
def orders_dashboard(request):
    status_filter = request.GET.get('status', 'all')
    search_query = request.GET.get('search', '')

    # Base queryset
    orders = Order.objects.all().order_by('-created_at')

    # Count for each tab BEFORE filtering
    counts = {
        'all': orders.count(),
        'pending': orders.filter(order_status='pending').count(),
        'processing': orders.filter(order_status='processing').count(),
        'dispatched': orders.filter(order_status='dispatched').count(),
        'delivered': orders.filter(order_status='delivered').count(),
    }

    # Filter by status
    if status_filter != 'all':
        orders = orders.filter(order_status=status_filter)

    # Search by name, phone, email, or order id
    if search_query:
        orders = orders.filter(
            Q(customer_name__icontains=search_query) |
            Q(phone_number__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(id__icontains=search_query)
        )

    # Pagination — 10 orders per page
    paginator = Paginator(orders, 10)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'counts': counts,
        'status_filter': status_filter,
        'search_query': search_query,
        'status_choices': [
            ('all', 'All Orders'),
            ('pending', 'Pending'),
            ('processing', 'Processing'),
            ('dispatched', 'Dispatched'),
            ('delivered', 'Delivered'),
        ]
    }
    return render(request, 'parlour/admin/orders_dashboard.html', context)


@staff_member_required
def update_order_status(request, order_id):
    order = get_object_or_404(Order, id=order_id)

    if request.method == 'POST':
        new_status = request.POST.get('status')
        valid_statuses = ['pending', 'processing', 'dispatched', 'delivered']

        if new_status in valid_statuses:
            order.order_status = new_status
            order.save()
            messages.success(request, f'Order #{order.id} updated to {order.get_order_status_display()}.')
        else:
            messages.error(request, 'Invalid status.')

    # Redirect back to where they came from
    return redirect(request.META.get('HTTP_REFERER', 'orders_dashboard'))


@staff_member_required
def order_detail(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    items = order.orderitem_set.select_related('product').all()

    context = {
        'order': order,
        'items': items,
        'total': order.get_total(),
        'pickup_info': order.get_pickup_info(),
    }
    return render(request, 'parlour/admin/order_detail.html', context)

def payment_processing(request, checkout_id):
    """
    Page to show while waiting for M-Pesa payment confirmation.
    It polls the check_payment_status endpoint.
    """
    context = {
        'checkout_id': checkout_id
    }
    return render(request, 'parlour/payment_processing.html', context)

def payment_failed(request):
    """Page to show when a payment fails or is cancelled."""
    return render(request, 'parlour/payment_failed.html')




from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.http import require_POST

@staff_member_required
def delivery_dashboard(request):
    orders = Order.objects.filter(
        order_status__in=['pending', 'processing', 'dispatched']
    ).prefetch_related('orderitem_set__product').order_by('-created_at')
    return render(request, 'parlour/delivery_dashboard.html', {'orders': orders})


@staff_member_required
def delivery_detail(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    items = order.orderitem_set.select_related('product').all()
    payment = MpesaPayment.objects.filter(order=order).first()
    return render(request, 'parlour/delivery_detail.html', {
        'order': order,
        'items': items,
        'payment': payment,
    })


@staff_member_required
@require_POST
def delivery_stk_push(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    if order.is_paid:
        messages.error(request, 'Order is already paid.')
        return redirect('delivery_detail', order_id=order_id)

    result = stk_push(order.phone_number, order.get_total(), f"ORDER-{order.id}")
    if result['success']:
        # Create a fresh MpesaPayment linked to this order
        MpesaPayment.objects.create(
            checkout_request_id=result['checkout_request_id'],
            phone_number=order.phone_number,
            amount=order.get_total(),
            status='pending',
            order=order,                          # ← link to order directly
            order_details={},                     # empty since order already exists
            session_key=request.session.session_key or 'delivery',
        )
        messages.success(request, f'✅ STK Push sent to {order.phone_number}. Waiting for payment...')
    else:
        messages.error(request, f'STK Push failed: {result["message"]}')
    return redirect('delivery_detail', order_id=order_id)

@staff_member_required
@require_POST
def mark_delivered(request, order_id):
    order = get_object_or_404(Order, id=order_id)

    def format_phone(phone):
        phone = phone.strip().replace(" ", "").replace("-", "")
        if phone.startswith('+254'):
            return phone
        elif phone.startswith('254'):
            return '+' + phone
        elif phone.startswith('07') or phone.startswith('01'):
            return '+254' + phone[1:]
        elif phone.startswith('7') or phone.startswith('1'):
            return '+254' + phone
        return phone

    if order.is_paid:
        provided_phone = request.POST.get('mpesa_phone', '').strip()
        if not provided_phone:
            messages.error(request, 'Please provide the M-Pesa phone number to confirm identity.')
            return redirect('delivery_detail', order_id=order_id)

        if format_phone(provided_phone) != format_phone(order.phone_number):
            messages.error(request, 'Phone number does not match. Please verify with the customer.')
            return redirect('delivery_detail', order_id=order_id)

        order.order_status = 'delivered'
        order.save(update_fields=['order_status'])
        messages.success(request, f'✅ Order #{order.id} marked as delivered. Identity confirmed.')

    else:
        if request.POST.get('payment_method') == 'cash':
            order.is_paid = True
            order.order_status = 'delivered'
            order.save(update_fields=['is_paid', 'order_status'])
            messages.success(request, f'✅ Order #{order.id} marked as delivered and paid (cash).')
        else:
            messages.error(request, 'Order is not paid. Send STK Push or confirm cash payment.')
            return redirect('delivery_detail', order_id=order_id)

    return redirect('delivery_dashboard')

@staff_member_required
def delivery_payment_status(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    return JsonResponse({'is_paid': order.is_paid})    

@require_POST
def clear_whatsapp_popup(request):
    from django.utils import timezone
    request.session.pop('show_whatsapp_popup', None)

    action = request.POST.get('action', 'dismiss')

    if request.user.is_authenticated:
        profile, _ = Profile.objects.get_or_create(user=request.user)
        if action == 'joined':
            profile.whatsapp_joined = True
            profile.whatsapp_popup_dismissed_at = None
        else:
            profile.whatsapp_popup_dismissed_at = timezone.now()
        profile.save(update_fields=['whatsapp_joined', 'whatsapp_popup_dismissed_at'])

    return JsonResponse({'status': 'ok'})

# ── Referral Landing ──────────────────────────────────────────
def referral_landing(request, referral_code):
    """
    When someone clicks an agent's referral link.
    Save the code in session then redirect to signup.
    """
    try:
        agent = Agent.objects.get(referral_code=referral_code, status='approved')
        request.session['referral_code'] = referral_code
        # Get agent's display name
        if agent.user.first_name or agent.user.last_name:
            referrer_name = f"{agent.user.first_name} {agent.user.last_name}".strip()
        else:
            referrer_name = agent.user.username
        messages.success(request, f'🎉 You were referred by {referrer_name}! Sign up to get your promo discount on your first 5 products.')
    except Agent.DoesNotExist:
        messages.error(request, 'Invalid referral link.')
    return redirect('signup')


# ── Promo Code Popup Actions ──────────────────────────────────
def validate_promo_code(request):
    code = request.POST.get('code', '').strip().upper()
    try:
        agent = Agent.objects.get(referral_code=code, status='approved')
        # Get agent display name
        if agent.user.first_name or agent.user.last_name:
            agent_name = f"{agent.user.first_name} {agent.user.last_name}".strip()
        else:
            agent_name = agent.user.username

        return JsonResponse({
            'valid': True,
            'agent_name': agent_name,
            'message': f'✅ Valid code! You get discount pricing on your first 5 products.'
        })
    except Agent.DoesNotExist:
        return JsonResponse({
            'valid': False,
            'agent_name': '',
            'message': '❌ Invalid promo code. Please check and try again.'
        })

@require_POST
def save_promo_code(request):
    if not request.user.is_authenticated:
        return JsonResponse({'status': 'error', 'message': 'Not logged in'})
    if hasattr(request.user, 'promousage'):
        return JsonResponse({'status': 'error', 'message': 'Promo already applied'})

    code = request.POST.get('code', '').strip().upper()
    try:
        agent = Agent.objects.get(referral_code=code, status='approved')
        PromoUsage.objects.create(
            user=request.user,
            agent=agent,
            promo_purchases_count=0,
            is_active=True
        )
        profile, _ = Profile.objects.get_or_create(user=request.user)
        profile.promo_popup_shown = True
        profile.show_promo_popup = False  # ← clear the flag
        profile.save(update_fields=['promo_popup_shown', 'show_promo_popup'])
        return JsonResponse({
            'status': 'success',
            'message': '🎉 Promo code applied! You get discount pricing on your first 5 products.'
        })
    except Agent.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': '❌ Invalid promo code.'})


@require_POST
def skip_promo_code(request):
    if request.user.is_authenticated:
        profile, _ = Profile.objects.get_or_create(user=request.user)
        profile.promo_popup_shown = True
        profile.show_promo_popup = False  # ← clear the flag
        profile.save(update_fields=['promo_popup_shown', 'show_promo_popup'])
    return JsonResponse({'status': 'ok'})

@login_required
def become_agent(request):
    # Redirect if already an agent
    try:
        agent = request.user.agent
        if agent.status == 'approved':
            return redirect('agent_dashboard')
        # Pending or suspended — show status
        return render(request, 'parlour/become_agent.html', {'agent': agent})
    except Agent.DoesNotExist:
        pass

    if request.method == 'POST':
        phone_number = request.POST.get('phone_number', '').strip()
        mpesa_number = request.POST.get('mpesa_number', '').strip()
        reason = request.POST.get('reason', '').strip()

        if not phone_number or not reason:
            messages.error(request, 'Please fill in all required fields.')
            return render(request, 'parlour/become_agent.html')

        Agent.objects.create(
            user=request.user,
            phone_number=phone_number,
            mpesa_number=mpesa_number,
            reason=reason,
            status='pending'
        )
        messages.success(request, '✅ Application submitted! We will review and get back to you.')
        return redirect('become_agent')

    return render(request, 'parlour/become_agent.html')


@login_required
def agent_dashboard(request):
    try:
        agent = request.user.agent
    except Agent.DoesNotExist:
        return redirect('become_agent')

    if agent.status != 'approved':
        messages.warning(request, 'Your agent account is not approved yet.')
        return redirect('become_agent')

    referrals = PromoUsage.objects.filter(agent=agent).select_related('user').order_by('-created_at')

    context = {
        'agent': agent,
        'referrals': referrals,
        'total_referrals': referrals.count(),
        'active_referrals': referrals.filter(is_active=True).count(),
        'completed_referrals': referrals.filter(is_active=False).count(),
    }
    return render(request, 'parlour/agent_dashboard.html', context)


@login_required
def agent_referrals(request):
    try:
        agent = request.user.agent
    except Agent.DoesNotExist:
        return redirect('become_agent')

    if agent.status != 'approved':
        return redirect('become_agent')

    referrals = PromoUsage.objects.filter(agent=agent).select_related('user').order_by('-created_at')
    return render(request, 'parlour/agent_referrals.html', {'agent': agent, 'referrals': referrals})
