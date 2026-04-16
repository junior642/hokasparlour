from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Count, Q
from django.utils import timezone
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.views.decorators.http import require_POST

from parlour.models import Store, SellerApplication, Product, Order, OrderItem


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def get_seller_store(user):
    """Return the store owned by this user, or None."""
    try:
        return Store.objects.get(owner=user)
    except Store.DoesNotExist:
        return None


def seller_required(view_func):
    """Decorator: must be logged in AND own an approved store."""
    @login_required
    def wrapper(request, *args, **kwargs):
        store = get_seller_store(request.user)
        if not store:
            messages.error(request, "You don't have a seller account yet.")
            return redirect('seller:seller_apply')
        if store.status == 'pending':
            return render(request, 'sellers/pending.html', {'store': store})
        if store.status == 'suspended':
            return render(request, 'sellers/suspended.html', {'store': store})
        request.store = store
        return view_func(request, *args, **kwargs)
    return wrapper


# ─────────────────────────────────────────────
# APPLICATION
# ─────────────────────────────────────────────

@login_required
def seller_apply(request):
    """Seller application form."""
    store = get_seller_store(request.user)
    if store:
        return redirect('seller:seller_dashboard')

    existing = SellerApplication.objects.filter(user=request.user).first()
    if existing:
        return render(request, 'sellers/apply_pending.html', {'application': existing})

    if request.method == 'POST':
        business_name = request.POST.get('business_name', '').strip()
        phone = request.POST.get('phone', '').strip()
        reason = request.POST.get('reason', '').strip()

        if not business_name or not phone or not reason:
            messages.error(request, 'All fields are required.')
        else:
            SellerApplication.objects.create(
                user=request.user,
                business_name=business_name,
                phone=phone,
                reason=reason,
                status='pending',
            )
            messages.success(request, 'Application submitted! We\'ll review it shortly.')
            return redirect('seller:seller_apply')

    return render(request, 'sellers/apply.html')


# ─────────────────────────────────────────────
# DASHBOARD HOME
# ─────────────────────────────────────────────

@seller_required
def seller_dashboard(request):
    store = request.store
    products = Product.objects.filter(store=store)

    # Summary stats
    total_products = products.count()
    # Consider products with stock > 0 as "active"
    active_products = products.filter(stock_quantity__gt=0).count()  # Changed

    # Orders that contain products from this store
    try:
        store_order_items = OrderItem.objects.filter(product__store=store)
        total_orders = store_order_items.values('order').distinct().count()
        total_revenue = store_order_items.filter(
            order__status__in=['completed', 'delivered']
        ).aggregate(rev=Sum('price'))['rev'] or 0
        recent_orders = (
            store_order_items
            .select_related('order', 'order__user', 'product')
            .order_by('-order__created_at')[:5]
        )
    except Exception:
        total_orders = 0
        total_revenue = 0
        recent_orders = []

    # Low stock - using stock_quantity instead of stock
    low_stock = products.filter(stock_quantity__lte=5, stock_quantity__gt=0)  # Changed

    context = {
        'store': store,
        'total_products': total_products,
        'active_products': active_products,
        'total_orders': total_orders,
        'total_revenue': total_revenue,
        'recent_orders': recent_orders,
        'low_stock': low_stock,
        'page_title': 'Dashboard',
        'active_nav': 'dashboard',
    }
    return render(request, 'sellers/dash.html', context)


# ─────────────────────────────────────────────
# PRODUCTS
# ─────────────────────────────────────────────

@seller_required
def seller_products(request):
    store = request.store
    qs = Product.objects.filter(store=store).order_by('-created_at')

    # Search
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q))

    # Filter - use stock_quantity instead of is_active
    status_filter = request.GET.get('status', '')
    if status_filter == 'active':
        qs = qs.filter(stock_quantity__gt=0)  # Changed
    elif status_filter == 'inactive':
        qs = qs.filter(stock_quantity=0)  # Changed

    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'store': store,
        'page_obj': page_obj,
        'q': q,
        'status_filter': status_filter,
        'page_title': 'My Products',
        'active_nav': 'products',
    }
    return render(request, 'sellers/products.html', context)


@seller_required
def seller_product_add(request):
    store = request.store

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        price = request.POST.get('price', '0')
        anchor_price = request.POST.get('anchor_price', '') or None
        discount_price = request.POST.get('discount_price', '') or None
        purchase_cost = request.POST.get('cost', '') or None  # Changed from 'cost' to 'purchase_cost'
        stock_quantity = request.POST.get('stock', '0')  # Changed from 'stock' to 'stock_quantity'
        image = request.FILES.get('image')

        if not name or not price:
            messages.error(request, 'Name and price are required.')
        else:
            product = Product.objects.create(
                store=store,
                name=name,
                description=description,
                price=price,
                anchor_price=anchor_price,
                discount_price=discount_price,
                purchase_cost=purchase_cost,  # Changed from 'cost'
                stock_quantity=stock_quantity,  # Changed from 'stock'
            )
            if image:
                product.image = image
                product.save()

            messages.success(request, f'"{name}" has been added.')
            return redirect('seller:seller_products')

    context = {
        'store': store,
        'page_title': 'Add Product',
        'active_nav': 'products',
    }
    return render(request, 'sellers/product_form.html', context)


@seller_required
def seller_product_edit(request, pk):
    store = request.store
    product = get_object_or_404(Product, pk=pk, store=store)

    if request.method == 'POST':
        product.name = request.POST.get('name', product.name).strip()
        product.description = request.POST.get('description', product.description).strip()
        product.price = request.POST.get('price', product.price)
        product.anchor_price = request.POST.get('anchor_price') or None
        product.discount_price = request.POST.get('discount_price') or None
        product.purchase_cost = request.POST.get('cost', product.purchase_cost) or None  # Changed
        product.stock_quantity = request.POST.get('stock', product.stock_quantity)  # Changed

        image = request.FILES.get('image')
        if image:
            product.image = image

        product.save()
        messages.success(request, f'"{product.name}" updated.')
        return redirect('seller:seller_products')

    context = {
        'store': store,
        'product': product,
        'page_title': 'Edit Product',
        'active_nav': 'products',
    }
    return render(request, 'sellers/product_form.html', context)

@seller_required
@require_POST
def seller_product_delete(request, pk):
    store = request.store
    product = get_object_or_404(Product, pk=pk, store=store)
    product.delete()
    messages.success(request, f'"{product.name}" deleted.')
    return redirect('seller:seller_products')


@seller_required
@require_POST
def seller_product_toggle(request, pk):
    store = request.store
    product = get_object_or_404(Product, pk=pk, store=store)
    # Toggle between in-stock and out-of-stock
    if product.stock_quantity > 0:
        product.stock_quantity = 0
    else:
        product.stock_quantity = 1  # Set to 1 when toggling back to active
    product.save()
    return JsonResponse({'active': product.stock_quantity > 0})


# ─────────────────────────────────────────────
# ORDERS
# ─────────────────────────────────────────────

@seller_required
def seller_orders(request):
    store = request.store

    try:
        store_order_ids = (
            OrderItem.objects
            .filter(product__store=store)
            .values_list('order_id', flat=True)
            .distinct()
        )
        qs = Order.objects.filter(id__in=store_order_ids).order_by('-created_at')

        status_filter = request.GET.get('status', '')
        if status_filter:
            qs = qs.filter(status=status_filter)

        paginator = Paginator(qs, 20)
        page_obj = paginator.get_page(request.GET.get('page'))
    except Exception:
        page_obj = []
        status_filter = ''

    context = {
        'store': store,
        'page_obj': page_obj,
        'status_filter': status_filter,
        'page_title': 'Orders',
        'active_nav': 'orders',
    }
    return render(request, 'sellers/orders.html', context)


@seller_required
def seller_order_detail(request, pk):
    store = request.store

    try:
        order_item_ids = OrderItem.objects.filter(product__store=store).values_list('order_id', flat=True)
        order = get_object_or_404(Order, pk=pk, id__in=order_item_ids)
        items = order.items.filter(product__store=store).select_related('product')
    except Exception:
        order = None
        items = []

    context = {
        'store': store,
        'order': order,
        'items': items,
        'page_title': f'Order #{pk}',
        'active_nav': 'orders',
    }
    return render(request, 'sellers/order_detail.html', context)


# ─────────────────────────────────────────────
# STORE SETTINGS
# ─────────────────────────────────────────────

@seller_required
def seller_store_settings(request):
    store = request.store

    if request.method == 'POST':
        store.store_name = request.POST.get('store_name', store.store_name).strip()
        store.description = request.POST.get('description', store.description).strip()
        store.phone = request.POST.get('phone', store.phone).strip()
        store.email = request.POST.get('email', store.email).strip()
        store.whatsapp = request.POST.get('whatsapp', store.whatsapp).strip()

        logo = request.FILES.get('logo')
        if logo:
            store.logo = logo

        store.save()
        messages.success(request, 'Store settings updated.')
        return redirect('seller:seller_store_settings')

    context = {
        'store': store,
        'page_title': 'Store Settings',
        'active_nav': 'settings',
    }
    return render(request, 'sellers/store_settings.html', context)