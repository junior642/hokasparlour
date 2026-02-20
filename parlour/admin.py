from django.contrib import admin
from django.utils.html import format_html, mark_safe
from .models import (
    Product, ProductImage, Order, OrderItem, StoreSettings, 
    EmailOTP, Profile, OrderHistory, Advertisement, AdImage, AdImpression
)


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 3
    fields = ('image', 'alt_text', 'order', 'image_preview')
    readonly_fields = ('image_preview',)
    
    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" width="100" height="100" style="object-fit: cover; border-radius: 4px;" />', obj.image.url)
        return "No image"
    image_preview.short_description = 'Preview'


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('get_subtotal',)
    
    def get_subtotal(self, obj):
        return f"KSH {obj.get_subtotal()}"
    get_subtotal.short_description = 'Subtotal'


class AdImageInline(admin.TabularInline):
    model = AdImage
    extra = 2
    fields = ('image', 'caption', 'order', 'image_preview')
    readonly_fields = ('image_preview',)
    
    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" width="100" height="100" style="object-fit: cover;" />', obj.image.url)
        return "No image"
    image_preview.short_description = 'Preview'


@admin.register(StoreSettings)
class StoreSettingsAdmin(admin.ModelAdmin):
    list_display = ('pickup_location', 'pickup_date', 'pickup_time', 'store_phone', 'store_email')
    
    fieldsets = (
        ('Pickup Information (Applies to ALL Orders)', {
            'fields': ('pickup_location', 'pickup_date', 'pickup_time', 'pickup_days_info'),
            'description': 'This pickup information will be sent to ALL customers in their order confirmation emails.'
        }),
        ('Contact Information', {
            'fields': ('store_phone', 'store_email')
        }),
    )
    
    def has_add_permission(self, request):
        return not StoreSettings.objects.exists()
    
    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'category',
        'stock_type',
        'delivery_badge',
        'price',
        'stock_quantity',
        'is_in_stock',
        'image_count',
        'created_at'
    )

    list_filter = ('category', 'stock_type', 'created_at')
    search_fields = ('name', 'description')
    ordering = ('-created_at',)
    inlines = [ProductImageInline]

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'category', 'stock_type', 'price', 'stock_quantity')
        }),
        ('Details', {
            'fields': ('description', 'available_sizes', 'image')
        }),
    )

    def is_in_stock(self, obj):
        return obj.is_in_stock()
    is_in_stock.boolean = True
    is_in_stock.short_description = 'In Stock'

    def image_count(self, obj):
        count = obj.additional_images.count()
        if count > 0:
            return format_html('<span style="color: green;">✓ {} additional</span>', count)
        return mark_safe('<span style="color: gray;">Main only</span>')
    image_count.short_description = 'Images'

    def delivery_badge(self, obj):
        if obj.stock_type == 'ready':
            return mark_safe(
                '<span style="background:#28a745;color:white;padding:4px 10px;'
                'border-radius:12px;font-size:11px;">Next Day</span>'
            )
        return mark_safe(
            '<span style="background:#ffc107;color:black;padding:4px 10px;'
            'border-radius:12px;font-size:11px;">Friday Delivery</span>'
        )
    delivery_badge.short_description = "Delivery Type"


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ('product', 'alt_text', 'order', 'image_preview')
    list_filter = ('product__category',)
    search_fields = ('product__name', 'alt_text')
    ordering = ('product', 'order')
    list_editable = ('order',)
    
    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" width="80" height="80" style="object-fit: cover; border-radius: 4px;" />', obj.image.url)
        return "No image"
    image_preview.short_description = 'Preview'


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer_name', 'phone_number', 'order_status', 'get_total_display', 'created_at')
    list_filter = ('order_status', 'created_at')
    search_fields = ('customer_name', 'email', 'phone_number', 'id')
    readonly_fields = ('created_at', 'get_total_display', 'show_pickup_info')
    inlines = [OrderItemInline]
    ordering = ('-created_at',)
    
    fieldsets = (
        ('Customer Information', {
            'fields': ('customer_name', 'phone_number', 'email', 'delivery_address')
        }),
        ('Order Details', {
            'fields': ('order_status', 'created_at', 'get_total_display')
        }),
        ('Pickup Information (Global - Set in Store Settings)', {
            'fields': ('show_pickup_info',),
            'description': 'Pickup information is managed in Store Settings and applies to all orders.'
        }),
        ('Delivery Information (Optional)', {
            'fields': ('expected_delivery_date', 'delivery_location')
        }),
    )
    
    def get_total_display(self, obj):
        return f"KSH {obj.get_total()}"
    get_total_display.short_description = 'Total Amount'
    
    def show_pickup_info(self, obj):
        pickup_info = obj.get_pickup_info()
        return format_html(
            '<div style="background: #f8f9fa; padding: 15px; border-radius: 8px; border-left: 4px solid #667eea;">'
            '<strong style="color: #333;">Location:</strong> {}<br>'
            '<strong style="color: #333;">Date:</strong> {}<br>'
            '<strong style="color: #333;">Time:</strong> {}<br>'
            '<strong style="color: #333;">Days:</strong> {}'
            '</div>',
            pickup_info['location'],
            pickup_info['date'],
            pickup_info['time'],
            pickup_info['days']
        )
    show_pickup_info.short_description = 'Current Pickup Info'


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('order', 'product', 'quantity', 'size', 'price', 'get_subtotal_display')
    list_filter = ('order__order_status', 'product__category')
    search_fields = ('order__id', 'product__name', 'order__customer_name')
    
    def get_subtotal_display(self, obj):
        return f"KSH {obj.get_subtotal()}"
    get_subtotal_display.short_description = 'Subtotal'


@admin.register(EmailOTP)
class EmailOTPAdmin(admin.ModelAdmin):
    list_display = ('user', 'otp', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('user__username', 'user__email', 'otp')
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'phone_number', 'preferred_payment_method', 'has_complete_profile', 'created_at')
    list_filter = ('preferred_payment_method', 'created_at')
    search_fields = ('user__username', 'user__email', 'phone_number')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('User Information', {
            'fields': ('user', 'profile_picture')
        }),
        ('Contact & Delivery', {
            'fields': ('phone_number', 'delivery_address', 'default_delivery_location')
        }),
        ('Preferences', {
            'fields': ('preferred_payment_method',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def has_complete_profile(self, obj):
        return obj.has_complete_profile()
    has_complete_profile.boolean = True
    has_complete_profile.short_description = 'Complete'


@admin.register(OrderHistory)
class OrderHistoryAdmin(admin.ModelAdmin):
    list_display = ('user', 'order', 'viewed_at')
    list_filter = ('viewed_at',)
    search_fields = ('user__username', 'order__id', 'order__customer_name')
    readonly_fields = ('viewed_at',)
    ordering = ('-viewed_at',)


@admin.register(Advertisement)
class AdvertisementAdmin(admin.ModelAdmin):
    list_display = ('title', 'ad_type', 'is_active', 'order', 'views', 'clicks', 'ctr', 'status_badge')
    list_filter = ('ad_type', 'is_active', 'target_audience', 'created_at')
    search_fields = ('title', 'headline', 'subheadline')
    ordering = ('order', '-created_at')
    list_editable = ('order', 'is_active')
    inlines = [AdImageInline]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'ad_type', 'target_audience', 'order', 'is_active')
        }),
        ('Single Image Ad', {
            'fields': ('single_image',),
            'classes': ('collapse',)
        }),
        ('Video Ad', {
            'fields': ('video', 'video_poster', 'autoplay', 'loop'),
            'classes': ('collapse',)
        }),
        ('Ad Content', {
            'fields': ('headline', 'subheadline', 'button_text', 'button_url', 'button_color')
        }),
        ('Display Settings', {
            'fields': ('show_on_mobile', 'show_on_tablet', 'show_on_desktop')
        }),
        ('Styling', {
            'fields': ('background_color', 'text_color', 'overlay_opacity'),
            'classes': ('collapse',)
        }),
        ('Scheduling', {
            'fields': ('start_date', 'end_date'),
            'classes': ('collapse',)
        }),
        ('Statistics', {
            'fields': ('views', 'clicks'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ('views', 'clicks')
    
    def ctr(self, obj):
        if obj.views > 0:
            rate = (obj.clicks / obj.views) * 100
            color = 'green' if rate > 5 else 'orange' if rate > 2 else 'red'
            return format_html('<span style="color: {};">{:.2f}%</span>', color, rate)
        return mark_safe('<span>0%</span>')
    ctr.short_description = 'CTR'
    
    def status_badge(self, obj):
        if not obj.is_active:
            return mark_safe(
                '<span style="background: #dc3545; color: white; padding: 3px 10px; '
                'border-radius: 12px; font-size: 11px;">Inactive</span>'
            )
        
        from django.utils import timezone
        now = timezone.now()
        
        if obj.start_date and now < obj.start_date:
            return mark_safe(
                '<span style="background: #ffc107; color: white; padding: 3px 10px; '
                'border-radius: 12px; font-size: 11px;">Scheduled</span>'
            )
        
        if obj.end_date and now > obj.end_date:
            return mark_safe(
                '<span style="background: #6c757d; color: white; padding: 3px 10px; '
                'border-radius: 12px; font-size: 11px;">Expired</span>'
            )
        
        return mark_safe(
            '<span style="background: #28a745; color: white; padding: 3px 10px; '
            'border-radius: 12px; font-size: 11px;">Active</span>'
        )
    status_badge.short_description = 'Status'


@admin.register(AdImage)
class AdImageAdmin(admin.ModelAdmin):
    list_display = ('advertisement', 'caption', 'order', 'image_preview')
    list_filter = ('advertisement__ad_type',)
    search_fields = ('advertisement__title', 'caption')
    ordering = ('advertisement', 'order')
    list_editable = ('order',)
    
    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" width="80" height="80" style="object-fit: cover; border-radius: 4px;" />', obj.image.url)
        return "No image"
    image_preview.short_description = 'Preview'


@admin.register(AdImpression)
class AdImpressionAdmin(admin.ModelAdmin):
    list_display = ('advertisement', 'session_key', 'ip_address', 'clicked', 'viewed_at')
    list_filter = ('clicked', 'viewed_at', 'advertisement')
    search_fields = ('session_key', 'ip_address', 'advertisement__title')
    readonly_fields = ('advertisement', 'session_key', 'ip_address', 'user_agent', 'viewed_at', 'clicked')
    ordering = ('-viewed_at',)
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False