from django.contrib import admin
from django.db.models import Sum, Count
from django.utils.html import format_html
from .models import SalesRecord, ProductStats, EmailLog

@admin.register(SalesRecord)
class SalesRecordAdmin(admin.ModelAdmin):
    list_display = ('id', 'order', 'total_items', 'total_amount', 'profit_estimate', 'sale_date')
    list_filter = ('sale_date',)
    search_fields = ('order__customer_name', 'order__id')
    readonly_fields = ('sale_date',)
    date_hierarchy = 'sale_date'
    ordering = ('-sale_date',)
    
    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(request, extra_context=extra_context)
        
        try:
            qs = response.context_data['cl'].queryset
        except (AttributeError, KeyError):
            return response
        
        metrics = {
            'total_sales': qs.aggregate(total=Sum('total_amount'))['total'] or 0,
            'total_orders': qs.count(),
            'total_profit': qs.aggregate(total=Sum('profit_estimate'))['total'] or 0,
        }
        
        response.context_data['summary'] = [
            {'label': 'Total Sales', 'value': f"${metrics['total_sales']:.2f}"},
            {'label': 'Total Orders', 'value': metrics['total_orders']},
            {'label': 'Total Profit Estimate', 'value': f"${metrics['total_profit']:.2f}"},
        ]
        
        return response


@admin.register(ProductStats)
class ProductStatsAdmin(admin.ModelAdmin):
    list_display = ('product', 'total_sold', 'total_revenue', 'last_sold_date')
    list_filter = ('last_sold_date',)
    search_fields = ('product__name',)
    readonly_fields = ('total_sold', 'total_revenue', 'last_sold_date')
    ordering = ('-total_revenue',)


@admin.register(EmailLog)
class EmailLogAdmin(admin.ModelAdmin):
    list_display = ('recipient_email', 'subject', 'status', 'sent_at')
    list_filter = ('status', 'sent_at')
    search_fields = ('recipient_email', 'subject')
    readonly_fields = ('sent_at',)
    date_hierarchy = 'sent_at'
    ordering = ('-sent_at',)
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False