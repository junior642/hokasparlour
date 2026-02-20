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
            'id':           stat.product.id,
            'name':         stat.product.name,
            'category':     stat.product.get_category_display(),
            'stock_type':   stat.product.get_stock_type_display(),
            'revenue':      float(stat.total_revenue),
            'sold':         stat.total_sold,
            'price':        float(stat.product.price),
            'cost':         float(stat.product.get_cost()) if stat.product.get_cost() else None,
            'profit_item':  float(profit) if profit else None,
            'margin_pct':   stat.product.get_profit_margin_percent(),
            'url':          f'/admin/parlour/product/{stat.product.id}/change/',
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
        'labels':   ['Ready Stock', 'Warehouse Stock'],
        'revenue':  [float(ready_rev),     float(warehouse_rev)],
        'cost':     [float(ready_cost),    float(wh_cost)],
        'profit':   [float(ready_profit),  float(wh_profit)],
    }

    # ── 7. Stock Levels (ready products) ─────────────────────────
    ready_products = Product.objects.filter(stock_type='ready').order_by('stock_quantity')

    stock_data = [
        {
            'name':  p.name,
            'qty':   p.stock_quantity,
            'url':   f'/admin/parlour/product/{p.id}/change/',
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