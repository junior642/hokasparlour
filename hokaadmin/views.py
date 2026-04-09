from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.db.models import Sum, Count, Avg, F, Q
from django.utils import timezone
from datetime import timedelta
from parlour.models import Order, Product, OrderItem
from .models import SalesRecord, ProductStats, EmailLog
from decimal import Decimal


@login_required
def admin_dashboard(request):
    # ── Revenue ───────────────────────────────────────────────────
    total_revenue = SalesRecord.objects.aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
    total_orders  = Order.objects.count()
    avg_order_value = SalesRecord.objects.aggregate(avg=Avg('total_amount'))['avg'] or Decimal('0.00')
    total_products  = Product.objects.count()

    # ── Profit Calculation ────────────────────────────────────────
    # Sum revenue from all delivered order items
    delivered_items = OrderItem.objects.filter(order__order_status='delivered')

    total_profit      = Decimal('0.00')
    total_cost        = Decimal('0.00')
    uncosted_revenue  = Decimal('0.00')  # items with no cost set

    for item in delivered_items.select_related('product'):
        subtotal   = item.get_subtotal()
        cost_total = item.get_cost_total()
        if cost_total is not None:
            total_profit += subtotal - cost_total
            total_cost   += cost_total
        else:
            uncosted_revenue += subtotal

    # ── Stock Breakdown ───────────────────────────────────────────
    ready_products     = Product.objects.filter(stock_type='ready')
    warehouse_products = Product.objects.filter(stock_type='warehouse')
    out_of_stock       = ready_products.filter(stock_quantity=0).count()
    low_stock          = ready_products.filter(stock_quantity__gt=0, stock_quantity__lte=3).count()

    # ── Order Status Counts ───────────────────────────────────────
    order_counts = {
        'all':        total_orders,
        'pending':    Order.objects.filter(order_status='pending').count(),
        'processing': Order.objects.filter(order_status='processing').count(),
        'dispatched': Order.objects.filter(order_status='dispatched').count(),
        'delivered':  Order.objects.filter(order_status='delivered').count(),
    }

    # ── Recent Orders ─────────────────────────────────────────────
    recent_orders = Order.objects.order_by('-created_at')[:5]

    context = {
        'total_revenue':      total_revenue,
        'total_orders':       total_orders,
        'avg_order_value':    avg_order_value,
        'total_products':     total_products,
        'total_profit':       total_profit,
        'total_cost':         total_cost,
        'uncosted_revenue':   uncosted_revenue,
        'ready_count':        ready_products.count(),
        'warehouse_count':    warehouse_products.count(),
        'out_of_stock':       out_of_stock,
        'low_stock':          low_stock,
        'order_counts':       order_counts,
        'recent_orders':      recent_orders,
    }

    return render(request, 'hokaadmin/dashboard.html', context)


@login_required
def sales_summary(request):
    period = request.GET.get('period', 'all')
    now    = timezone.now()

    if period == 'today':
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        records = SalesRecord.objects.filter(sale_date__gte=start_date)
        orders  = Order.objects.filter(created_at__gte=start_date)
    elif period == 'week':
        start_date = now - timedelta(days=7)
        records = SalesRecord.objects.filter(sale_date__gte=start_date)
        orders  = Order.objects.filter(created_at__gte=start_date)
    elif period == 'month':
        start_date = now - timedelta(days=30)
        records = SalesRecord.objects.filter(sale_date__gte=start_date)
        orders  = Order.objects.filter(created_at__gte=start_date)
    else:
        records = SalesRecord.objects.all()
        orders  = Order.objects.all()

    total_sales  = records.aggregate(total=Sum('total_amount'))['total'] or 0
    total_orders = records.count()
    total_items  = records.aggregate(total=Sum('total_items'))['total'] or 0
    avg_order    = records.aggregate(avg=Avg('total_amount'))['avg'] or 0

    # Profit for this period — from delivered orders only
    delivered_items = OrderItem.objects.filter(
        order__order_status='delivered',
        order__in=orders
    ).select_related('product')

    period_profit = Decimal('0.00')
    period_cost   = Decimal('0.00')
    for item in delivered_items:
        subtotal   = item.get_subtotal()
        cost_total = item.get_cost_total()
        if cost_total is not None:
            period_profit += subtotal - cost_total
            period_cost   += cost_total

    # Ready vs Warehouse breakdown for this period
    ready_revenue     = Decimal('0.00')
    warehouse_revenue = Decimal('0.00')
    for item in delivered_items:
        if item.product.stock_type == 'ready':
            ready_revenue += item.get_subtotal()
        else:
            warehouse_revenue += item.get_subtotal()

    data = {
        'period':             period,
        'total_sales':        float(total_sales),
        'total_orders':       total_orders,
        'total_items':        total_items,
        'average_order_value': float(avg_order),
        'total_profit':       float(period_profit),
        'total_cost':         float(period_cost),
        'ready_revenue':      float(ready_revenue),
        'warehouse_revenue':  float(warehouse_revenue),
    }

    return JsonResponse(data)


@login_required
def daily_sales(request):
    days       = int(request.GET.get('days', 30))
    start_date = timezone.now() - timedelta(days=days)

    sales_by_day = (
        SalesRecord.objects
        .filter(sale_date__gte=start_date)
        .extra(select={'day': 'date(sale_date)'})
        .values('day')
        .annotate(
            total_sales=Sum('total_amount'),
            order_count=Count('id')
        )
        .order_by('day')
    )

    data = {
        'daily_sales': [
            {
                'date':        item['day'].strftime('%Y-%m-%d') if hasattr(item['day'], 'strftime') else str(item['day']),
                'total_sales': float(item['total_sales']),
                'order_count': item['order_count'],
            }
            for item in sales_by_day
        ]
    }

    return JsonResponse(data)


@login_required
def weekly_sales(request):
    weeks      = int(request.GET.get('weeks', 12))
    start_date = timezone.now() - timedelta(weeks=weeks)

    sales_by_week = (
        SalesRecord.objects
        .filter(sale_date__gte=start_date)
        .extra(select={'week': "strftime('%%Y-%%W', sale_date)"})
        .values('week')
        .annotate(
            total_sales=Sum('total_amount'),
            order_count=Count('id')
        )
        .order_by('week')
    )

    data = {
        'weekly_sales': [
            {
                'week':        item['week'],
                'total_sales': float(item['total_sales']),
                'order_count': item['order_count'],
            }
            for item in sales_by_week
        ]
    }

    return JsonResponse(data)


@login_required
def monthly_sales(request):
    months     = int(request.GET.get('months', 12))
    start_date = timezone.now() - timedelta(days=months * 30)

    sales_by_month = (
        SalesRecord.objects
        .filter(sale_date__gte=start_date)
        .extra(select={'month': "strftime('%%Y-%%m', sale_date)"})
        .values('month')
        .annotate(
            total_sales=Sum('total_amount'),
            order_count=Count('id')
        )
        .order_by('month')
    )

    data = {
        'monthly_sales': [
            {
                'month':       item['month'],
                'total_sales': float(item['total_sales']),
                'order_count': item['order_count'],
            }
            for item in sales_by_month
        ]
    }

    return JsonResponse(data)


@login_required
def top_products(request):
    limit = int(request.GET.get('limit', 10))

    top = (
        ProductStats.objects
        .select_related('product')
        .order_by('-total_revenue')[:limit]
    )

    data = {
        'top_products': [
            {
                'product_id':       stat.product.id,
                'product_name':     stat.product.name,
                'stock_type':       stat.product.stock_type,
                'stock_type_label': stat.product.get_stock_type_display(),
                'total_sold':       stat.total_sold,
                'total_revenue':    float(stat.total_revenue),
                'cost_per_item':    float(stat.product.get_cost()) if stat.product.get_cost() else None,
                'profit_per_item':  float(stat.product.get_profit_per_item()) if stat.product.get_profit_per_item() else None,
                'profit_margin_pct': stat.product.get_profit_margin_percent(),
                'last_sold_date':   stat.last_sold_date.strftime('%Y-%m-%d %H:%M:%S') if stat.last_sold_date else None,
            }
            for stat in top
        ]
    }

    return JsonResponse(data)


@login_required
def revenue_trends(request):
    period = request.GET.get('period', 'month')

    if period == 'day':
        start_date = timezone.now() - timedelta(days=30)
        trends = (
            SalesRecord.objects
            .filter(sale_date__gte=start_date)
            .extra(select={'period': 'date(sale_date)'})
            .values('period')
            .annotate(revenue=Sum('total_amount'))
            .order_by('period')
        )
    elif period == 'week':
        start_date = timezone.now() - timedelta(weeks=12)
        trends = (
            SalesRecord.objects
            .filter(sale_date__gte=start_date)
            .extra(select={'period': "strftime('%%Y-%%W', sale_date)"})
            .values('period')
            .annotate(revenue=Sum('total_amount'))
            .order_by('period')
        )
    else:
        start_date = timezone.now() - timedelta(days=365)
        trends = (
            SalesRecord.objects
            .filter(sale_date__gte=start_date)
            .extra(select={'period': "strftime('%%Y-%%m', sale_date)"})
            .values('period')
            .annotate(revenue=Sum('total_amount'))
            .order_by('period')
        )

    data = {
        'period_type': period,
        'trends': [
            {
                'period':  str(item['period']),
                'revenue': float(item['revenue']),
            }
            for item in trends
        ]
    }

    return JsonResponse(data)


@login_required
def profit_report(request):
    period = request.GET.get('period', 'all')
    now    = timezone.now()

    if period == 'today':
        orders = Order.objects.filter(created_at__gte=now.replace(hour=0, minute=0, second=0))
    elif period == 'week':
        orders = Order.objects.filter(created_at__gte=now - timedelta(days=7))
    elif period == 'month':
        orders = Order.objects.filter(created_at__gte=now - timedelta(days=30))
    else:
        orders = Order.objects.all()

    delivered_items = OrderItem.objects.filter(
        order__order_status='delivered',
        order__in=orders
    ).select_related('product')

    ready_revenue = ready_cost = ready_profit = Decimal('0.00')
    warehouse_revenue = warehouse_cost = warehouse_profit = Decimal('0.00')
    uncosted = Decimal('0.00')

    for item in delivered_items:
        subtotal   = item.get_subtotal()
        cost_total = item.get_cost_total()
        if item.product.stock_type == 'ready':
            ready_revenue += subtotal
            if cost_total is not None:
                ready_cost   += cost_total
                ready_profit += subtotal - cost_total
            else:
                uncosted += subtotal
        else:
            warehouse_revenue += subtotal
            if cost_total is not None:
                warehouse_cost   += cost_total
                warehouse_profit += subtotal - cost_total
            else:
                uncosted += subtotal

    total_revenue = ready_revenue + warehouse_revenue
    total_cost    = ready_cost + warehouse_cost
    total_profit  = ready_profit + warehouse_profit
    margin_pct    = round((float(total_profit) / float(total_revenue)) * 100, 1) if total_revenue > 0 else 0

    context = {
        'period': period,
        'ready_stock':     {'revenue': ready_revenue,     'cost': ready_cost,     'profit': ready_profit},
        'warehouse_stock': {'revenue': warehouse_revenue, 'cost': warehouse_cost, 'profit': warehouse_profit},
        'totals': {
            'revenue':        total_revenue,
            'cost':           total_cost,
            'profit':         total_profit,
            'margin_percent': margin_pct,
            'uncosted':       uncosted,
        }
    }
    return render(request, 'hokaadmin/profit_report.html', context)


@login_required
def stock_report(request):
    ready_products     = Product.objects.filter(stock_type='ready').order_by('stock_quantity')
    warehouse_products = Product.objects.filter(stock_type='warehouse')

    ready_data = [
        {
            'name':            p.name,
            'category':        p.get_category_display(),
            'price':           p.price,
            'purchase_cost':   p.purchase_cost,
            'profit_per_item': p.get_profit_per_item(),
            'margin_pct':      p.get_profit_margin_percent(),
            'stock_quantity':  p.stock_quantity,
            'status':          'out' if p.stock_quantity == 0 else ('low' if p.stock_quantity <= 3 else 'ok'),
        }
        for p in ready_products
    ]

    warehouse_data = [
        {
            'name':            p.name,
            'category':        p.get_category_display(),
            'price':           p.price,
            'supplier_cost':   p.supplier_cost,
            'profit_per_item': p.get_profit_per_item(),
            'margin_pct':      p.get_profit_margin_percent(),
        }
        for p in warehouse_products
    ]

    context = {
        'ready_stock': {
            'products':     ready_data,
            'total':        ready_products.count(),
            'out_of_stock': ready_products.filter(stock_quantity=0).count(),
            'low_stock':    ready_products.filter(stock_quantity__gt=0, stock_quantity__lte=3).count(),
        },
        'warehouse_stock': {
            'products': warehouse_data,
            'total':    warehouse_products.count(),
        },
    }
    return render(request, 'hokaadmin/stock_report.html', context)


# ── Helper functions ──────────────────────────────────────────────────────────

def calculate_total_revenue():
    return SalesRecord.objects.aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')


def calculate_total_orders():
    return Order.objects.count()


def calculate_average_order_value():
    return SalesRecord.objects.aggregate(avg=Avg('total_amount'))['avg'] or Decimal('0.00')


def get_best_selling_products(limit=10):
    return ProductStats.objects.select_related('product').order_by('-total_sold')[:limit]


def get_sales_per_day(days=30):
    start_date = timezone.now() - timedelta(days=days)
    return (
        SalesRecord.objects
        .filter(sale_date__gte=start_date)
        .extra(select={'day': 'date(sale_date)'})
        .values('day')
        .annotate(total=Sum('total_amount'), count=Count('id'))
        .order_by('day')
    )


def get_sales_per_week(weeks=12):
    start_date = timezone.now() - timedelta(weeks=weeks)
    return (
        SalesRecord.objects
        .filter(sale_date__gte=start_date)
        .extra(select={'week': "strftime('%%Y-%%W', sale_date)"})
        .values('week')
        .annotate(total=Sum('total_amount'), count=Count('id'))
        .order_by('week')
    )


def get_sales_per_month(months=12):
    start_date = timezone.now() - timedelta(days=months * 30)
    return (
        SalesRecord.objects
        .filter(sale_date__gte=start_date)
        .extra(select={'month': "strftime('%%Y-%%m', sale_date)"})
        .values('month')
        .annotate(total=Sum('total_amount'), count=Count('id'))
        .order_by('month')
    )


def calculate_profit_for_period(start_date=None):
    """
    Utility: calculate total profit for a given period.
    If start_date is None, calculates for all time.
    Only counts delivered orders.
    """
    items = OrderItem.objects.filter(order__order_status='delivered')
    if start_date:
        items = items.filter(order__created_at__gte=start_date)

    items = items.select_related('product')

    total_profit = Decimal('0.00')
    for item in items:
        profit = item.get_profit()
        if profit is not None:
            total_profit += profit

    return total_profit


from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.db.models import Sum, Count
from django.utils import timezone
from datetime import timedelta
from parlour.models import Order, Product, OrderItem
from .models import SalesRecord, ProductStats
from decimal import Decimal
import json


@login_required
def analytics_charts(request):
    """
    Gathers all chart data and passes it as JSON to the template.
    Charts included:
      1. Daily revenue (last 30 days)
      2. Orders by status (doughnut)
      3. Revenue by category (bar)
      4. Top 8 products by revenue (horizontal bar) — with product links
      5. Ready vs Warehouse revenue split (pie)
      6. Profit vs Cost vs Revenue comparison (grouped bar)
      7. Stock levels for ready products (bar)
      8. Monthly revenue trend (line)
    """
    now = timezone.now()

    # ── 1. Daily Revenue — last 30 days ──────────────────────────
    daily_data = (
        SalesRecord.objects
        .filter(sale_date__gte=now - timedelta(days=30))
        .extra(select={'day': 'date(sale_date)'})
        .values('day')
        .annotate(total=Sum('total_amount'), orders=Count('id'))
        .order_by('day')
    )

    daily_labels  = [str(d['day']) for d in daily_data]
    daily_revenue = [float(d['total']) for d in daily_data]
    daily_orders  = [d['orders'] for d in daily_data]

    # ── 2. Orders by Status ───────────────────────────────────────
    status_counts = {
        'Pending':    Order.objects.filter(order_status='pending').count(),
        'Processing': Order.objects.filter(order_status='processing').count(),
        'Dispatched': Order.objects.filter(order_status='dispatched').count(),
        'Delivered':  Order.objects.filter(order_status='delivered').count(),
    }

    # ── 3. Revenue by Category ────────────────────────────────────
    category_data = (
        OrderItem.objects
        .filter(order__order_status='delivered')
        .values('product__category')
        .annotate(revenue=Sum('price'))
        .order_by('-revenue')
    )

    CATEGORY_LABELS = {
        'hoodies': 'Hoodies', 'sweatpants': 'Sweatpants',
        'socks': 'Socks', 'shorts': 'Shorts', 'shirts': 'Shirts',
    }

    cat_labels  = [CATEGORY_LABELS.get(d['product__category'], d['product__category']) for d in category_data]
    cat_revenue = [float(d['revenue']) for d in category_data]

    # ── 4. Top 8 Products by Revenue (with links) ─────────────────
    top_products_qs = (
        ProductStats.objects
        .select_related('product')
        .order_by('-total_revenue')[:8]
    )

    top_products = []
    for stat in top_products_qs:
        profit = stat.product.get_profit_per_item()
        top_products.append({
            'id':          stat.product.id,
            'name':        stat.product.name,
            'category':    CATEGORY_LABELS.get(stat.product.category, stat.product.category or 'Uncategorized'),
            'stock_type':  stat.product.get_stock_type_display(),
            'revenue':     float(stat.total_revenue),
            'sold':        stat.total_sold,
            'price':       float(stat.product.price),
            'cost':        float(stat.product.get_cost()) if stat.product.get_cost() else None,
            'profit_item': float(profit) if profit else None,
            'margin_pct':  stat.product.get_profit_margin_percent(),
            'url':         f'/admin/parlour/product/{stat.product.id}/change/',
        })

    top_labels  = [p['name'] for p in top_products]
    top_revenue = [p['revenue'] for p in top_products]
    top_sold    = [p['sold'] for p in top_products]

    # ── 5. Ready vs Warehouse Revenue ────────────────────────────
    delivered_items = OrderItem.objects.filter(
        order__order_status='delivered'
    ).select_related('product')

    ready_rev     = Decimal('0.00')
    warehouse_rev = Decimal('0.00')
    ready_profit  = Decimal('0.00')
    wh_profit     = Decimal('0.00')
    ready_cost    = Decimal('0.00')
    wh_cost       = Decimal('0.00')

    for item in delivered_items:
        sub  = item.get_subtotal()
        cost = item.get_cost_total()
        if item.product.stock_type == 'ready':
            ready_rev += sub
            if cost:
                ready_cost   += cost
                ready_profit += sub - cost
        else:
            warehouse_rev += sub
            if cost:
                wh_cost   += cost
                wh_profit += sub - cost

    # ── 6. Revenue / Cost / Profit per stock type (grouped bar) ──
    grouped_bar = {
        'labels':  ['Ready Stock', 'Warehouse Stock'],
        'revenue': [float(ready_rev),    float(warehouse_rev)],
        'cost':    [float(ready_cost),   float(wh_cost)],
        'profit':  [float(ready_profit), float(wh_profit)],
    }

    # ── 7. Stock Levels (ready products) ─────────────────────────
    ready_products = Product.objects.filter(stock_type='ready').order_by('stock_quantity')

    stock_data = [
        {
            'name':   p.name,
            'qty':    p.stock_quantity,
            'url':    f'/admin/parlour/product/{p.id}/change/',
            'status': 'out' if p.stock_quantity == 0 else ('low' if p.stock_quantity <= 3 else 'ok'),
        }
        for p in ready_products
    ]

    stock_labels = [p['name'] for p in stock_data]
    stock_qty    = [p['qty']  for p in stock_data]
    stock_colors = [
        '#c1121f' if p['status'] == 'out' else
        '#e07b39' if p['status'] == 'low' else
        '#2d6a4f'
        for p in stock_data
    ]

    # ── 8. Monthly Revenue Trend (last 12 months) ─────────────────
    monthly_data = (
        SalesRecord.objects
        .filter(sale_date__gte=now - timedelta(days=365))
        .extra(select={'month': "strftime('%%Y-%%m', sale_date)"})
        .values('month')
        .annotate(total=Sum('total_amount'))
        .order_by('month')
    )

    monthly_labels  = [d['month'] for d in monthly_data]
    monthly_revenue = [float(d['total']) for d in monthly_data]

    context = {
        # raw data for template loops
        'top_products': top_products,
        'stock_data':   stock_data,

        # JSON blobs for Chart.js
        'chart_data': json.dumps({
            'daily': {
                'labels':  daily_labels,
                'revenue': daily_revenue,
                'orders':  daily_orders,
            },
            'status': {
                'labels': list(status_counts.keys()),
                'counts': list(status_counts.values()),
            },
            'category': {
                'labels':  cat_labels,
                'revenue': cat_revenue,
            },
            'top_products': {
                'labels':  top_labels,
                'revenue': top_revenue,
                'sold':    top_sold,
            },
            'stock_split': {
                'labels':  ['Ready Stock', 'Warehouse Stock'],
                'revenue': [float(ready_rev), float(warehouse_rev)],
            },
            'grouped': grouped_bar,
            'stock_levels': {
                'labels': stock_labels,
                'qty':    stock_qty,
                'colors': stock_colors,
            },
            'monthly': {
                'labels':  monthly_labels,
                'revenue': monthly_revenue,
            },
        }),
    }

    return render(request, 'hokaadmin/analytics_charts.html', context)


from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.models import User
from django.db.models import Count, Sum, Q, Prefetch, Max, Min
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from parlour.models import (
    Profile, Order, OrderItem, OrderHistory,
    PromoUsage, Agent, Wishlist, ProductView,
    UserPreference
)


@login_required
def user_profiles(request):
    """
    Admin user profiles page with:
    - Search by name/email/phone
    - Filters: join date, promo usage, purchase count, gender, agent status
    - Sort: join date, total spent, order count, promo purchases
    - Summary stats at top
    """

    # ── Base queryset ─────────────────────────────────────────────
    users = User.objects.select_related(
        'profile', 'agent'
    ).prefetch_related(
        'order_history', 'promousage'
    ).filter(is_staff=False)

    # ── Search ────────────────────────────────────────────────────
    search_query = request.GET.get('q', '').strip()
    if search_query:
        users = users.filter(
            Q(username__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(profile__phone_number__icontains=search_query)
        )

    # ── Filters ───────────────────────────────────────────────────
    # Join date filter
    join_filter = request.GET.get('joined', 'all')
    now = timezone.now()
    if join_filter == 'today':
        users = users.filter(date_joined__date=now.date())
    elif join_filter == 'week':
        users = users.filter(date_joined__gte=now - timedelta(days=7))
    elif join_filter == 'month':
        users = users.filter(date_joined__gte=now - timedelta(days=30))
    elif join_filter == '3months':
        users = users.filter(date_joined__gte=now - timedelta(days=90))
    elif join_filter == '6months':
        users = users.filter(date_joined__gte=now - timedelta(days=180))

    # Promo usage filter
    promo_filter = request.GET.get('promo', 'all')
    if promo_filter == 'active':
        users = users.filter(promousage__is_active=True)
    elif promo_filter == 'used_up':
        users = users.filter(promousage__is_active=False, promousage__promo_purchases_count__gte=5)
    elif promo_filter == 'none':
        users = users.filter(promousage__isnull=True)
    elif promo_filter == 'has_any':
        users = users.filter(promousage__isnull=False)

    # Gender filter
    gender_filter = request.GET.get('gender', 'all')
    if gender_filter in ('M', 'F', 'U'):
        users = users.filter(profile__gender=gender_filter)

    # Agent status filter
    agent_filter = request.GET.get('agent', 'all')
    if agent_filter == 'yes':
        users = users.filter(agent__status='approved')
    elif agent_filter == 'pending':
        users = users.filter(agent__status='pending')
    elif agent_filter == 'no':
        users = users.filter(agent__isnull=True)

    # Whatsapp filter
    wa_filter = request.GET.get('whatsapp', 'all')
    if wa_filter == 'yes':
        users = users.filter(profile__whatsapp_joined=True)
    elif wa_filter == 'no':
        users = users.filter(profile__whatsapp_joined=False)

    # ── Annotate with order stats ─────────────────────────────────
    # We build order data in Python for flexibility
    all_user_ids = list(users.values_list('id', flat=True))

    # Map user_id -> order stats
    order_stats = {}
    for uid in all_user_ids:
        order_stats[uid] = {
            'total_orders': 0,
            'total_spent': Decimal('0.00'),
            'last_order_date': None,
        }

    # Get orders linked via OrderHistory
    histories = (
        OrderHistory.objects
        .filter(user_id__in=all_user_ids)
        .select_related('order')
        .order_by('user_id', '-viewed_at')
    )
    seen = set()
    for h in histories:
        uid = h.user_id
        oid = h.order_id
        key = (uid, oid)
        if key not in seen:
            seen.add(key)
            stats = order_stats[uid]
            stats['total_orders'] += 1
            stats['total_spent'] += h.order.get_total()
            if stats['last_order_date'] is None:
                stats['last_order_date'] = h.order.created_at

    # ── Sort ──────────────────────────────────────────────────────
    sort_by = request.GET.get('sort', 'newest')

    users_list = list(users.distinct())

    def sort_key(u):
        stats = order_stats.get(u.id, {})
        if sort_by == 'oldest':
            return u.date_joined
        elif sort_by == 'total_spent_desc':
            return -stats.get('total_spent', Decimal('0.00'))
        elif sort_by == 'total_spent_asc':
            return stats.get('total_spent', Decimal('0.00'))
        elif sort_by == 'orders_desc':
            return -stats.get('total_orders', 0)
        elif sort_by == 'orders_asc':
            return stats.get('total_orders', 0)
        elif sort_by == 'promo_desc':
            try:
                return -(u.promousage.promo_purchases_count if hasattr(u, 'promousage') else 0)
            except Exception:
                return 0
        else:  # newest
            return -u.date_joined.timestamp()

    users_list.sort(key=sort_key)

    # ── Purchase count filter (applied after annotation) ──────────
    purchase_filter = request.GET.get('purchases', 'all')
    if purchase_filter == 'zero':
        users_list = [u for u in users_list if order_stats[u.id]['total_orders'] == 0]
    elif purchase_filter == '1to3':
        users_list = [u for u in users_list if 1 <= order_stats[u.id]['total_orders'] <= 3]
    elif purchase_filter == '4plus':
        users_list = [u for u in users_list if order_stats[u.id]['total_orders'] >= 4]
    elif purchase_filter == '10plus':
        users_list = [u for u in users_list if order_stats[u.id]['total_orders'] >= 10]

    # ── Build enriched user data ───────────────────────────────────
    enriched_users = []
    for u in users_list:
        stats = order_stats.get(u.id, {})
        profile = getattr(u, 'profile', None)
        agent = getattr(u, 'agent', None)
        try:
            promo = u.promousage
        except Exception:
            promo = None

        enriched_users.append({
            'user': u,
            'profile': profile,
            'agent': agent,
            'promo': promo,
            'total_orders': stats.get('total_orders', 0),
            'total_spent': stats.get('total_spent', Decimal('0.00')),
            'last_order_date': stats.get('last_order_date'),
        })

    # ── Summary Stats ─────────────────────────────────────────────
    all_users_base = User.objects.filter(is_staff=False)
    total_users = all_users_base.count()
    new_this_week = all_users_base.filter(date_joined__gte=now - timedelta(days=7)).count()
    promo_active = PromoUsage.objects.filter(is_active=True).count()
    agents_approved = Agent.objects.filter(status='approved').count()
    wa_joined = Profile.objects.filter(whatsapp_joined=True).count()
    new_today = all_users_base.filter(date_joined__date=now.date()).count()

    context = {
        'enriched_users': enriched_users,
        'total_count': len(enriched_users),
        'search_query': search_query,
        'filters': {
            'joined': join_filter,
            'promo': promo_filter,
            'gender': gender_filter,
            'agent': agent_filter,
            'whatsapp': wa_filter,
            'purchases': purchase_filter,
            'sort': sort_by,
        },
        'stats': {
            'total_users': total_users,
            'new_this_week': new_this_week,
            'new_today': new_today,
            'promo_active': promo_active,
            'agents_approved': agents_approved,
            'wa_joined': wa_joined,
        }
    }

    return render(request, 'hokaadmin/user_profiles.html', context)


@login_required
def user_profile_detail(request, user_id):
    """Detailed view for a single user."""
    u = get_object_or_404(User, id=user_id)
    profile = getattr(u, 'profile', None)
    agent = getattr(u, 'agent', None)
    try:
        promo = u.promousage
    except Exception:
        promo = None
    try:
        preferences = u.preferences
    except Exception:
        preferences = None

    # Order history
    order_history = (
        OrderHistory.objects
        .filter(user=u)
        .select_related('order')
        .order_by('-viewed_at')[:20]
    )

    # Wishlist
    wishlist = Wishlist.objects.filter(user=u).select_related('product')[:10]

    # Recent product views
    recent_views = ProductView.objects.filter(user=u).select_related('product')[:10]

    # Totals
    total_spent = sum(h.order.get_total() for h in order_history)

    context = {
        'u': u,
        'profile': profile,
        'agent': agent,
        'promo': promo,
        'preferences': preferences,
        'order_history': order_history,
        'wishlist': wishlist,
        'recent_views': recent_views,
        'total_spent': total_spent,
    }
    return render(request, 'hokaadmin/user_profile_detail.html', context)   


from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.db.models import Q, Count
from django.utils import timezone
from datetime import timedelta
from parlour.models import ContactMessage


@login_required
def contact_messages(request):
    """Admin inbox for all contact form submissions."""

    messages_qs = ContactMessage.objects.select_related('user')

    # ── Search ─────────────────────────────────────────────────────
    search = request.GET.get('q', '').strip()
    if search:
        messages_qs = messages_qs.filter(
            Q(full_name__icontains=search) |
            Q(email__icontains=search) |
            Q(message__icontains=search) |
            Q(order_number__icontains=search) |
            Q(phone__icontains=search)
        )

    # ── Filters ────────────────────────────────────────────────────
    status_filter  = request.GET.get('status', 'all')
    subject_filter = request.GET.get('subject', 'all')
    date_filter    = request.GET.get('date', 'all')

    if status_filter != 'all':
        messages_qs = messages_qs.filter(status=status_filter)

    if subject_filter != 'all':
        messages_qs = messages_qs.filter(subject=subject_filter)

    now = timezone.now()
    if date_filter == 'today':
        messages_qs = messages_qs.filter(created_at__date=now.date())
    elif date_filter == 'week':
        messages_qs = messages_qs.filter(created_at__gte=now - timedelta(days=7))
    elif date_filter == 'month':
        messages_qs = messages_qs.filter(created_at__gte=now - timedelta(days=30))

    # ── Summary counts (always from full set, not filtered) ────────
    all_msgs = ContactMessage.objects
    stats = {
        'total':    all_msgs.count(),
        'unread':   all_msgs.filter(status='unread').count(),
        'read':     all_msgs.filter(status='read').count(),
        'replied':  all_msgs.filter(status='replied').count(),
        'archived': all_msgs.filter(status='archived').count(),
        'today':    all_msgs.filter(created_at__date=now.date()).count(),
    }

    context = {
        'messages_qs':    messages_qs,
        'total_count':    messages_qs.count(),
        'search':         search,
        'status_filter':  status_filter,
        'subject_filter': subject_filter,
        'date_filter':    date_filter,
        'stats':          stats,
        'subject_choices': ContactMessage.SUBJECT_CHOICES,
        'status_choices':  ContactMessage.STATUS_CHOICES,
    }
    return render(request, 'hokaadmin/contact_messages.html', context)


@login_required
def contact_message_detail(request, msg_id):
    """View a single message and update its status."""
    msg = get_object_or_404(ContactMessage, id=msg_id)

    # Auto-mark as read when opened
    if msg.status == 'unread':
        msg.status = 'read'
        msg.save(update_fields=['status'])

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'update_status':
            new_status = request.POST.get('status')
            if new_status in dict(ContactMessage.STATUS_CHOICES):
                msg.status = new_status
                msg.save(update_fields=['status', 'updated_at'])
        elif action == 'save_notes':
            msg.admin_notes = request.POST.get('admin_notes', '')
            msg.save(update_fields=['admin_notes', 'updated_at'])
        return redirect('hokaadmin:contact_message_detail', msg_id=msg.id)

    # Previous / next for navigation
    prev_msg = ContactMessage.objects.filter(created_at__gt=msg.created_at).order_by('created_at').first()
    next_msg = ContactMessage.objects.filter(created_at__lt=msg.created_at).order_by('-created_at').first()

    context = {
        'msg':      msg,
        'prev_msg': prev_msg,
        'next_msg': next_msg,
        'status_choices': ContactMessage.STATUS_CHOICES,
    }
    return render(request, 'hokaadmin/contact_message_detail.html', context)


@login_required
def contact_message_update_status(request, msg_id):
    """AJAX endpoint — quick status update from the inbox list."""
    if request.method == 'POST':
        msg = get_object_or_404(ContactMessage, id=msg_id)
        new_status = request.POST.get('status')
        if new_status in dict(ContactMessage.STATUS_CHOICES):
            msg.status = new_status
            msg.save(update_fields=['status', 'updated_at'])
            return JsonResponse({'ok': True, 'status': msg.status, 'label': msg.get_status_display()})
    return JsonResponse({'ok': False}, status=400)