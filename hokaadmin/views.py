from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.db.models import Sum, Count, Avg, F
from django.utils import timezone
from datetime import timedelta
from parlour.models import Order, Product, OrderItem
from .models import SalesRecord, ProductStats, EmailLog
from decimal import Decimal

@login_required
def admin_dashboard(request):
    total_revenue = SalesRecord.objects.aggregate(total=Sum('total_amount'))['total'] or 0
    total_orders = Order.objects.count()
    avg_order_value = SalesRecord.objects.aggregate(avg=Avg('total_amount'))['avg'] or 0
    total_products = Product.objects.count()
    
    context = {
        'total_revenue': total_revenue,
        'total_orders': total_orders,
        'avg_order_value': avg_order_value,
        'total_products': total_products,
    }
    
    return render(request, 'hokaadmin/dashboard.html', context)


@login_required
def sales_summary(request):
    period = request.GET.get('period', 'all')
    now = timezone.now()
    
    if period == 'today':
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        records = SalesRecord.objects.filter(sale_date__gte=start_date)
    elif period == 'week':
        start_date = now - timedelta(days=7)
        records = SalesRecord.objects.filter(sale_date__gte=start_date)
    elif period == 'month':
        start_date = now - timedelta(days=30)
        records = SalesRecord.objects.filter(sale_date__gte=start_date)
    else:
        records = SalesRecord.objects.all()
    
    total_sales = records.aggregate(total=Sum('total_amount'))['total'] or 0
    total_orders = records.count()
    total_items = records.aggregate(total=Sum('total_items'))['total'] or 0
    avg_order = records.aggregate(avg=Avg('total_amount'))['avg'] or 0
    
    data = {
        'period': period,
        'total_sales': float(total_sales),
        'total_orders': total_orders,
        'total_items': total_items,
        'average_order_value': float(avg_order),
    }
    
    return JsonResponse(data)


@login_required
def daily_sales(request):
    days = int(request.GET.get('days', 30))
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
                'date': item['day'].strftime('%Y-%m-%d') if hasattr(item['day'], 'strftime') else str(item['day']),
                'total_sales': float(item['total_sales']),
                'order_count': item['order_count']
            }
            for item in sales_by_day
        ]
    }
    
    return JsonResponse(data)


@login_required
def weekly_sales(request):
    weeks = int(request.GET.get('weeks', 12))
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
                'week': item['week'],
                'total_sales': float(item['total_sales']),
                'order_count': item['order_count']
            }
            for item in sales_by_week
        ]
    }
    
    return JsonResponse(data)


@login_required
def monthly_sales(request):
    months = int(request.GET.get('months', 12))
    start_date = timezone.now() - timedelta(days=months*30)
    
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
                'month': item['month'],
                'total_sales': float(item['total_sales']),
                'order_count': item['order_count']
            }
            for item in sales_by_month
        ]
    }
    
    return JsonResponse(data)


@login_required
def top_products(request):
    limit = int(request.GET.get('limit', 10))
    
    top_products = (
        ProductStats.objects
        .select_related('product')
        .order_by('-total_revenue')[:limit]
    )
    
    data = {
        'top_products': [
            {
                'product_id': stat.product.id,
                'product_name': stat.product.name,
                'total_sold': stat.total_sold,
                'total_revenue': float(stat.total_revenue),
                'last_sold_date': stat.last_sold_date.strftime('%Y-%m-%d %H:%M:%S') if stat.last_sold_date else None
            }
            for stat in top_products
        ]
    }
    
    return JsonResponse(data)


@login_required
def revenue_trends(request):
    period = request.GET.get('period', 'month')
    
    if period == 'day':
        days = 30
        start_date = timezone.now() - timedelta(days=days)
        trends = (
            SalesRecord.objects
            .filter(sale_date__gte=start_date)
            .extra(select={'period': 'date(sale_date)'})
            .values('period')
            .annotate(revenue=Sum('total_amount'))
            .order_by('period')
        )
    elif period == 'week':
        weeks = 12
        start_date = timezone.now() - timedelta(weeks=weeks)
        trends = (
            SalesRecord.objects
            .filter(sale_date__gte=start_date)
            .extra(select={'period': "strftime('%%Y-%%W', sale_date)"})
            .values('period')
            .annotate(revenue=Sum('total_amount'))
            .order_by('period')
        )
    else:
        months = 12
        start_date = timezone.now() - timedelta(days=months*30)
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
                'period': str(item['period']),
                'revenue': float(item['revenue'])
            }
            for item in trends
        ]
    }
    
    return JsonResponse(data)


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
    start_date = timezone.now() - timedelta(days=months*30)
    return (
        SalesRecord.objects
        .filter(sale_date__gte=start_date)
        .extra(select={'month': "strftime('%%Y-%%m', sale_date)"})
        .values('month')
        .annotate(total=Sum('total_amount'), count=Count('id'))
        .order_by('month')
    )