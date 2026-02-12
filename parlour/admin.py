from django.contrib import admin
from django.utils.html import format_html
from .models import Product, Order, OrderItem, StoreSettings

@admin.register(StoreSettings)
class StoreSettingsAdmin(admin.ModelAdmin):
    list_display = ('pickup_location', 'pickup_date', 'pickup_time', 'store_phone')
    
    fieldsets = (
        ('Pickup Information (Applies to ALL Orders)', {
            'fields': ('pickup_location', 'pickup_date', 'pickup_time', 'pickup_days_info'),
            'description': 'This pickup information will be sent to ALL customers in their order confirmation emails. When you change these settings, all future order emails will include the updated information.'
        }),
        ('Contact Information', {
            'fields': ('store_phone', 'store_email')
        }),
    )
    
    def has_add_permission(self, request):
        # Only allow one settings object
        return not StoreSettings.objects.exists()
    
    def has_delete_permission(self, request, obj=None):
        # Don't allow deletion
        return False


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('get_subtotal',)
    
    def get_subtotal(self, obj):
        return obj.get_subtotal()
    get_subtotal.short_description = 'Subtotal'


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'price', 'stock_quantity', 'is_in_stock', 'created_at')
    list_filter = ('category', 'created_at')
    search_fields = ('name', 'description')
    ordering = ('-created_at',)
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'category', 'price', 'stock_quantity')
        }),
        ('Details', {
            'fields': ('description', 'available_sizes', 'image')
        }),
    )
    
    def is_in_stock(self, obj):
        return obj.is_in_stock()
    is_in_stock.boolean = True
    is_in_stock.short_description = 'In Stock'


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer_name', 'phone_number', 'order_status', 'created_at', 'show_pickup_date')
    list_filter = ('order_status', 'created_at')
    search_fields = ('customer_name', 'email', 'phone_number')
    readonly_fields = ('created_at', 'get_total', 'show_pickup_info')
    inlines = [OrderItemInline]
    ordering = ('-created_at',)
    
    fieldsets = (
        ('Customer Information', {
            'fields': ('customer_name', 'phone_number', 'email', 'delivery_address')
        }),
        ('Order Details', {
            'fields': ('order_status', 'created_at', 'get_total')
        }),
        ('Pickup Information (Global - Set in Store Settings)', {
            'fields': ('show_pickup_info',),
            'description': 'Pickup information is managed in Store Settings and applies to all orders. Go to Store Settings to change pickup date, time, and location.'
        }),
        ('Delivery Information (Optional)', {
            'fields': ('expected_delivery_date', 'delivery_location')
        }),
    )
    
    def get_total(self, obj):
        return f"${obj.get_total()}"
    get_total.short_description = 'Total Amount'
    
    def show_pickup_date(self, obj):
        pickup_info = obj.get_pickup_info()
        return pickup_info['date']
    show_pickup_date.short_description = 'Pickup Date'
    
    def show_pickup_info(self, obj):
        pickup_info = obj.get_pickup_info()
        return format_html(
            '<strong>Location:</strong> {}<br>'
            '<strong>Date:</strong> {}<br>'
            '<strong>Time:</strong> {}<br>'
            '<strong>Days:</strong> {}',
            pickup_info['location'],
            pickup_info['date'],
            pickup_info['time'],
            pickup_info['days']
        )
    show_pickup_info.short_description = 'Current Pickup Info (From Store Settings)'


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('order', 'product', 'quantity', 'size', 'price', 'get_subtotal')
    list_filter = ('order__order_status',)
    
    def get_subtotal(self, obj):
        return f"${obj.get_subtotal()}"
    get_subtotal.short_description = 'Subtotal'