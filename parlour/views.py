from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.conf import settings
from .models import Product, Order, OrderItem, EmailOTP, StoreSettings
from .email_utils import send_order_confirmation_email
import random


def home(request):
    products = Product.objects.all()
    
    # Get filter parameters
    category = request.GET.get('category')
    min_price = request.GET.get('min_price')
    max_price = request.GET.get('max_price')
    
    # Apply category filter
    if category:
        products = products.filter(category=category)
    
    # Apply price filters
    if min_price:
        products = products.filter(price__gte=min_price)
    
    if max_price:
        products = products.filter(price__lte=max_price)
    
    # Get all categories for the filter
    categories = Product.CATEGORY_CHOICES
    
    context = {
        'products': products,
        'categories': categories,
        'selected_category': category,
        'min_price': min_price,
        'max_price': max_price,
    }
    return render(request, 'parlour/home.html', context)


def product_detail(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    sizes = [size.strip() for size in product.available_sizes.split(',')]
    context = {
        'product': product,
        'sizes': sizes
    }
    return render(request, 'parlour/product_detail.html', context)


def add_to_cart(request, product_id):
    if request.method == 'POST':
        product = get_object_or_404(Product, id=product_id)
        quantity = int(request.POST.get('quantity', 1))
        size = request.POST.get('size', '')
        
        cart = request.session.get('cart', {})
        cart_key = f"{product_id}_{size}"
        
        if cart_key in cart:
            cart[cart_key]['quantity'] += quantity
        else:
            cart[cart_key] = {
                'product_id': product_id,
                'name': product.name,
                'price': str(product.price),
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
            'subtotal': subtotal
        })
    
    context = {
        'cart_items': cart_items,
        'total': total
    }
    return render(request, 'parlour/cart.html', context)


def remove_from_cart(request, cart_key):
    cart = request.session.get('cart', {})
    if cart_key in cart:
        del cart[cart_key]
        request.session['cart'] = cart
        messages.success(request, 'Item removed from cart!')
    return redirect('cart')


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
        
        # Store order details in session for payment processing
        request.session['pending_order'] = {
            'customer_name': customer_name,
            'phone_number': phone_number,
            'email': email,
            'delivery_address': delivery_address,
            'payment_method': payment_method,
            'cart': cart,
            'total': sum(float(item['price']) * item['quantity'] for item in cart.values())
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
            except:
                pass  # Profile doesn't exist or error saving
        
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
        product = Product.objects.get(id=item['product_id'])
        
        # Convert price to Decimal safely
        try:
            price_value = Decimal(str(item['price']))
        except (InvalidOperation, TypeError, ValueError):
            price_value = Decimal('0.00')
            messages.warning(request, f'Invalid price for {product.name}. Using 0.00.')
        
        OrderItem.objects.create(
            order=order,
            product=product,
            quantity=item['quantity'],
            price=price_value,  # Now it's a Decimal, not a string
            size=item['size']
        )
        
        # Reduce stock quantity
        product.stock_quantity -= item['quantity']
        product.save()
    
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


def confirm_mpesa_payment(request):
    """Confirm M-Pesa payment and create order"""
    if request.method == 'POST':
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
            product = Product.objects.get(id=item['product_id'])
            OrderItem.objects.create(
                order=order,
                product=product,
                quantity=item['quantity'],
                price=item['price'],
                size=item['size']
            )
            # Reduce stock quantity
            product.stock_quantity -= item['quantity']
            product.save()
        
        # Send confirmation email
        email_sent = send_order_confirmation_email(order)
        
        if email_sent:
            messages.success(request, 'Payment confirmed! Order placed successfully. Confirmation email sent.')
        else:
            messages.warning(request, 'Payment confirmed! Order placed successfully. But confirmation email could not be sent.')
        
        # Clear session
        request.session['cart'] = {}
        del request.session['pending_order']
        
        return redirect('order_confirmation', order_id=order.id)
    
    return redirect('checkout')


def order_confirmation(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    context = {
        'order': order
    }
    return render(request, 'parlour/order_confirmation.html', context)


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


def generate_otp():
    return str(random.randint(100000, 999999))


def user_signup(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False
            user.save()

            otp = generate_otp()

            EmailOTP.objects.update_or_create(
                user=user,
                defaults={'otp': otp}
            )

            send_mail(
                subject='Your OTP Code - Hoka\'s Parlour',
                message=f'Your OTP code is: {otp}',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )

            request.session['otp_user_id'] = user.id

            messages.success(request, 'An OTP has been sent to your email.')
            return redirect('verify_otp')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = UserCreationForm()

    return render(request, 'parlour/signup.html', {'form': form})


def verify_otp(request):
    user_id = request.session.get('otp_user_id')

    if not user_id:
        messages.error(request, 'Session expired. Please sign up again.')
        return redirect('signup')

    if request.method == 'POST':
        otp_input = request.POST.get('otp')

        try:
            otp_obj = EmailOTP.objects.get(user_id=user_id)

            if otp_obj.otp == otp_input:
                user = otp_obj.user
                user.is_active = True
                user.save()

                otp_obj.delete()
                del request.session['otp_user_id']

                login(request, user)
                messages.success(request, 'Account verified successfully!')
                return redirect('home')
            else:
                messages.error(request, 'Invalid OTP.')
        except EmailOTP.DoesNotExist:
            messages.error(request, 'OTP not found.')

    return render(request, 'parlour/verify_otp.html')


def user_logout(request):
    logout(request)
    messages.success(request, 'You have been logged out.')
    return redirect('home')



from .mpesa_utils import stk_push


def mpesa_payment(request):
    """M-Pesa payment page - initiates STK Push"""
    pending_order = request.session.get('pending_order')
    
    if not pending_order:
        messages.error(request, 'No pending order found.')
        return redirect('cart')
    
    stk_result = None
    stk_error = None
    
    if request.method == 'POST':
        # Trigger STK Push
        phone = pending_order['phone_number']
        amount = pending_order['total']
        
        # Use a temporary order ID for reference
        temp_ref = f"TEMP{request.session.session_key[-6:]}"
        
        result = stk_push(phone, amount, temp_ref)
        
        if result['success']:
            # Save checkout request ID in session
            request.session['checkout_request_id'] = result['checkout_request_id']
            stk_result = result
            messages.success(request, f'STK Push sent to {phone}! Check your phone and enter your M-Pesa PIN.')
        else:
            stk_error = result['message']
            messages.error(request, f'STK Push failed: {result["message"]}')
    
    context = {
        'pending_order': pending_order,
        'stk_result': stk_result,
        'stk_error': stk_error
    }
    return render(request, 'parlour/mpesa_payment.html', context)


from decimal import Decimal

def confirm_mpesa_payment(request):
    """Confirm M-Pesa payment and create order"""
    if request.method == 'POST':
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
            product = Product.objects.get(id=item['product_id'])
            OrderItem.objects.create(
                order=order,
                product=product,
                quantity=item['quantity'],
                price=Decimal(str(item['price'])),  # Convert to Decimal
                size=item['size']
            )
            product.stock_quantity -= item['quantity']
            product.save()
        
        # Send confirmation email
        email_sent = send_order_confirmation_email(order)
        
        if email_sent:
            messages.success(request, 'Payment confirmed! Order placed. Confirmation email sent.')
        else:
            messages.warning(request, 'Payment confirmed! Order placed. But confirmation email could not be sent.')
        
        # Clear session
        request.session['cart'] = {}
        del request.session['pending_order']
        if 'checkout_request_id' in request.session:
            del request.session['checkout_request_id']
        
        return redirect('order_confirmation', order_id=order.id)
    
    return redirect('checkout')

def mpesa_callback(request):
    """Handle M-Pesa payment callback from Safaricom"""
    import json
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            callback = data.get('Body', {}).get('stkCallback', {})
            
            result_code = callback.get('ResultCode')
            result_desc = callback.get('ResultDesc')
            checkout_request_id = callback.get('CheckoutRequestID')
            
            print(f"M-Pesa Callback - ResultCode: {result_code}, Desc: {result_desc}")
            print(f"CheckoutRequestID: {checkout_request_id}")
            
            if result_code == 0:
                # Payment successful
                metadata = callback.get('CallbackMetadata', {}).get('Item', [])
                
                amount = None
                mpesa_code = None
                phone = None
                
                for item in metadata:
                    if item.get('Name') == 'Amount':
                        amount = item.get('Value')
                    elif item.get('Name') == 'MpesaReceiptNumber':
                        mpesa_code = item.get('Value')
                    elif item.get('Name') == 'PhoneNumber':
                        phone = item.get('Value')
                
                print(f"Payment successful - Amount: {amount}, Code: {mpesa_code}, Phone: {phone}")
            else:
                print(f"Payment failed - {result_desc}")
                
        except Exception as e:
            print(f"Callback error: {e}")
    
    from django.http import JsonResponse
    return JsonResponse({'ResultCode': 0, 'ResultDesc': 'Success'})



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


from django.core.mail import send_mail
from django.conf import settings
from django.contrib import messages

def contact(request):
    """Contact Us page with form handling"""
    if request.method == 'POST':
        # Get form data
        full_name = request.POST.get('full_name')
        email = request.POST.get('email')
        phone = request.POST.get('phone', '')
        subject = request.POST.get('subject')
        order_number = request.POST.get('order_number', '')
        message = request.POST.get('message')
        
        # Prepare email content
        email_subject = f"Contact Form: {subject} - {full_name}"
        
        email_message = f"""
        New contact form submission from Hoka's Parlour website:
        
        Name: {full_name}
        Email: {email}
        Phone: {phone}
        Subject: {subject}
        Order Number: {order_number}
        
        Message:
        {message}
        
        ---
        This message was sent from the Hoka's Parlour contact form.
        """
        
        try:
            # Send email to store
            send_mail(
                subject=email_subject,
                message=email_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=['info@hokasparlour.co.ke', 'hokasparlour@gmail.com'],
                fail_silently=False,
            )
            
            # Send auto-reply to customer
            auto_reply_subject = "Thank you for contacting Hoka's Parlour"
            auto_reply_message = f"""
            Dear {full_name},
            
            Thank you for reaching out to Hoka's Parlour. We have received your message and will respond within 24 hours.
            
            Your reference: {subject} - {order_number if order_number else 'General Inquiry'}
            
            For urgent matters, please call us at +254 700 000 000.
            
            Best regards,
            The Hoka's Parlour Team
            🎓 Serving MMU Students Since 2024
            """
            
            send_mail(
                subject=auto_reply_subject,
                message=auto_reply_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                fail_silently=False,
            )
            
            messages.success(request, 'Thank you for contacting us! We will respond within 24 hours.')
            
        except Exception as e:
            messages.error(request, 'Sorry, there was an error sending your message. Please try again or call us directly.')
            print(f"Contact form error: {e}")
        
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


