from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from django.core.validators import FileExtensionValidator
from django.db.models.signals import post_save
from django.dispatch import receiver
from datetime import timedelta
from decimal import Decimal
import decimal

class StoreSettings(models.Model):
    # ── Store Info ────────────────────────────────────────────────
    pickup_location = models.CharField(max_length=300, default='Hoka\'s Parlour Main Store, 123 Fashion Street')
    store_phone = models.CharField(max_length=20, default='+254 700 000 000')
    store_email = models.EmailField(default='hokasparlour@gmail.com')

    # ── Ready Stock Delivery (Next Day, Mon-Fri) ──────────────────
    ready_delivery_time = models.TimeField(
        default='10:00:00',
        help_text='What time ready stock orders are delivered the next day'
    )
    ready_delivery_days = models.CharField(
        max_length=100,
        default='Monday,Tuesday,Wednesday,Thursday,Friday',
        help_text='Days next-day delivery is available (comma-separated)'
    )

    # ── Warehouse Stock Delivery (Always Friday) ──────────────────
    warehouse_delivery_time = models.TimeField(
        default='10:00:00',
        help_text='What time warehouse stock orders are delivered on Friday'
    )

    class Meta:
        verbose_name = 'Store Settings'
        verbose_name_plural = 'Store Settings'

    def __str__(self):
        return 'Store Settings'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get_settings(cls):
        settings, created = cls.objects.get_or_create(id=1)
        return settings

    def get_ready_delivery_info(self):
        """Returns next day delivery date and time for ready stock."""
        from datetime import date, timedelta
        today = date.today()
        next_day = today + timedelta(days=1)

        # Skip to Monday if next day falls on weekend
        if next_day.weekday() == 5:  # Saturday
            next_day += timedelta(days=2)
        elif next_day.weekday() == 6:  # Sunday
            next_day += timedelta(days=1)

        return {
            'date': next_day,
            'time': self.ready_delivery_time,
            'label': f"Next Day Delivery — {next_day.strftime('%A, %d %b %Y')} by {self.ready_delivery_time.strftime('%I:%M %p')}",
            'days': self.ready_delivery_days,
        }

    def get_warehouse_delivery_info(self):
        """Returns the next upcoming Friday delivery date and time."""
        from datetime import date, timedelta
        today = date.today()

        # Calculate days until next Friday (weekday 4)
        days_until_friday = (4 - today.weekday()) % 7
        if days_until_friday == 0:
            days_until_friday = 7  # If today is Friday, go to next Friday

        next_friday = today + timedelta(days=days_until_friday)

        return {
            'date': next_friday,
            'time': self.warehouse_delivery_time,
            'label': f"Friday Delivery — {next_friday.strftime('%A, %d %b %Y')} by {self.warehouse_delivery_time.strftime('%I:%M %p')}",
        }



class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True, blank=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)
    
    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name = 'Category'
        verbose_name_plural = 'Categories'
        ordering = ['name']

class Color(models.Model):
    name = models.CharField(max_length=50, unique=True)  # e.g. "Red", "Navy Blue"
    hex_code = models.CharField(
        max_length=7, 
        blank=True, 
        help_text="e.g. #FF0000"
    )
    
    def __str__(self):
        return self.name
    
    class Meta:
        ordering = ['name']
        verbose_name = 'Color'
        verbose_name_plural = 'Colors'

class Product(models.Model):
    

    STOCK_TYPE_CHOICES = [
        ('ready', 'Ready Stock'),
        ('warehouse', 'Warehouse Stock'),
    ]
    
    name = models.CharField(max_length=200)
    description = models.TextField()
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Selling price (what the customer pays)"
    )
    category = models.ForeignKey(
    'Category', 
    on_delete=models.SET_NULL, 
    null=True, 
    blank=True,
    related_name='products'
    )

    colors = models.ManyToManyField(
    'Color',
    blank=True,
    related_name='products',
    help_text="Select all available colors for this product"
    )
    
    stock_type = models.CharField(
        max_length=20,
        choices=STOCK_TYPE_CHOICES,
        default='ready',
        help_text="Ready = you own the stock. Warehouse = source after order."
    )

    # ── Cost Fields ──────────────────────────────────────────────
    purchase_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="[Ready Stock] How much YOU paid to buy this item for resale."
    )

    supplier_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="[Warehouse Stock] How much YOU pay the supplier per item when sourcing."
    )
    # ─────────────────────────────────────────────────────────────

    image = models.ImageField(upload_to='products/', help_text="Main product image")
    available_sizes = models.CharField(
        max_length=100,
        help_text="Comma-separated sizes (e.g., S,M,L,XL)"
    )
    stock_quantity = models.PositiveIntegerField(
        default=1,
        help_text="[Ready Stock] Number of items you currently have. Warehouse stock ignores this."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name

    # ── Stock Logic ───────────────────────────────────────────────
    def is_in_stock(self):
        """
        Warehouse stock is always available (sourced on demand).
        Ready stock depends on quantity on hand.
        """
        if self.stock_type == 'warehouse':
            return True
        return self.stock_quantity > 0

    def reduce_stock(self, quantity):
        """
        Reduce stock when an order is placed.
        Only applies to ready stock — warehouse stock is sourced on demand.
        """
        if self.stock_type == 'ready':
            self.stock_quantity = max(0, self.stock_quantity - quantity)
            self.save(update_fields=['stock_quantity'])
        # Warehouse: do nothing — stock doesn't deplete

    def restore_stock(self, quantity):
        """
        Restore stock if an order is cancelled.
        Only applies to ready stock.
        """
        if self.stock_type == 'ready':
            self.stock_quantity += quantity
            self.save(update_fields=['stock_quantity'])

    # ── Profit Logic ──────────────────────────────────────────────
    def get_cost(self):
        """
        Returns the relevant cost depending on stock type.
        Ready stock  → purchase_cost (what you paid upfront)
        Warehouse    → supplier_cost (what you pay per order)
        """
        if self.stock_type == 'ready':
            return self.purchase_cost
        return self.supplier_cost

    def get_profit_per_item(self):
        """
        Profit = selling price - cost price.
        Returns None if cost is not set.
        """
        cost = self.get_cost()
        if cost is not None:
            return self.price - cost
        return None

    def get_profit_margin_percent(self):
        """
        Profit margin as a percentage of selling price.
        e.g. sell at 2500, cost 1800 → margin = 28%
        """
        profit = self.get_profit_per_item()
        if profit is not None and self.price > 0:
            return round((profit / self.price) * 100, 1)
        return None

    # ── Delivery Logic ────────────────────────────────────────────
    def get_delivery_info(self):
        """Returns delivery info based on stock type."""
        from .models import StoreSettings
        settings = StoreSettings.get_settings()
        if self.stock_type == 'ready':
            return settings.get_ready_delivery_info()
        return settings.get_warehouse_delivery_info()
    # ── Images ───────────────────────────────────────────────────
    def get_all_images(self):
        images = [self.image] if self.image else []
        additional = list(self.additional_images.all())
        return images + [img.image for img in additional]
    
    class Meta:
        ordering = ['-created_at']


class ProductImage(models.Model):
    """Additional images for a product"""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='additional_images')
    image = models.ImageField(upload_to='products/additional/')
    alt_text = models.CharField(max_length=200, blank=True, help_text="Descriptive text for image")
    order = models.PositiveIntegerField(default=0, help_text="Display order (lower numbers show first)")
    
    class Meta:
        ordering = ['order']
        verbose_name = 'Product Image'
        verbose_name_plural = 'Product Images'
    
    def __str__(self):
        return f"Image for {self.product.name}"


class Order(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('dispatched', 'Dispatched'),
        ('delivered', 'Delivered'),
    ]
    
    customer_name = models.CharField(max_length=200)
    phone_number = models.CharField(max_length=20)
    email = models.EmailField()
    delivery_address = models.TextField()
    order_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    expected_delivery_date = models.DateField(null=True, blank=True)
    delivery_location = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Order #{self.id} - {self.customer_name}"
    
    def get_total(self):
        return sum(item.get_subtotal() for item in self.orderitem_set.all())

    def get_total_cost(self):
        """Total supplier/purchase cost across all items in this order."""
        return sum(
            item.get_cost_total()
            for item in self.orderitem_set.all()
            if item.get_cost_total() is not None
        )

    def get_total_profit(self):
        """Total profit for this order."""
        total = self.get_total()
        cost = self.get_total_cost()
        if cost is not None:
            return total - cost
        return None

    def get_pickup_info(self):
        settings = StoreSettings.get_settings()
        
        # Check if any order items are warehouse stock
        has_warehouse = self.orderitem_set.filter(product__stock_type='warehouse').exists()
        
        if has_warehouse:
            delivery = settings.get_warehouse_delivery_info()
        else:
            delivery = settings.get_ready_delivery_info()
        
        return {
            'location': settings.pickup_location,
            'date': delivery['date'],
            'time': delivery['time'],
            'label': delivery['label'],
            'days': delivery.get('days', 'Every Friday'),
        }
    
    class Meta:
        ordering = ['-created_at']


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    size = models.CharField(max_length=10, blank=True)
    
    def __str__(self):
        return f"{self.quantity} x {self.product.name}"
    
    def get_subtotal(self):
        """Revenue: what the customer paid for this line."""
        try:
            qty = Decimal(str(self.quantity))
            price = self.price if isinstance(self.price, Decimal) else Decimal(str(self.price))
            return qty * price
        except (TypeError, ValueError, decimal.InvalidOperation):
            return Decimal('0.00')

    def get_cost_total(self):
        """Cost: what you paid/will pay for this line."""
        cost = self.product.get_cost()
        if cost is not None:
            try:
                qty = Decimal(str(self.quantity))
                cost = cost if isinstance(cost, Decimal) else Decimal(str(cost))
                return qty * cost
            except (TypeError, ValueError, decimal.InvalidOperation):
                return None
        return None

    def get_profit(self):
        """Profit for this line item."""
        subtotal = self.get_subtotal()
        cost_total = self.get_cost_total()
        if cost_total is not None:
            return subtotal - cost_total
        return None


class EmailOTP(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"OTP for {self.user.username}"
    
    class Meta:
        verbose_name = 'Email OTP'
        verbose_name_plural = 'Email OTPs'


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    phone_number = models.CharField(max_length=20, blank=True)
    delivery_address = models.TextField(blank=True)
    default_delivery_location = models.CharField(max_length=200, blank=True)
    profile_picture = models.ImageField(upload_to='profiles/', blank=True, null=True)
    
    preferred_payment_method = models.CharField(
        max_length=20,
        choices=[
            ('mpesa', 'M-Pesa'),
            ('cash', 'Cash on Delivery'),
        ],
        default='mpesa',
        blank=True
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user.username}'s Profile"
    
    def get_full_address(self):
        return self.delivery_address or 'No address saved'
    
    def has_complete_profile(self):
        return bool(self.phone_number and self.delivery_address)
    
    class Meta:
        verbose_name = 'Profile'
        verbose_name_plural = 'Profiles'


@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)
    else:
        Profile.objects.get_or_create(user=instance)
        instance.profile.save()


class OrderHistory(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='order_history')
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    viewed_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-viewed_at']
        verbose_name = 'Order History'
        verbose_name_plural = 'Order Histories'


class Advertisement(models.Model):
    AD_TYPES = [
        ('single_image', 'Single Image'),
        ('multi_image', 'Multiple Images (Carousel)'),
        ('video', 'Video'),
    ]
    
    TARGET_AUDIENCES = [
        ('all', 'All Visitors'),
        ('new', 'New Visitors Only'),
        ('returning', 'Returning Visitors'),
    ]
    
    title = models.CharField(max_length=200, help_text="Internal name for the ad")
    ad_type = models.CharField(max_length=20, choices=AD_TYPES, default='single_image')
    target_audience = models.CharField(max_length=20, choices=TARGET_AUDIENCES, default='all')
    
    single_image = models.ImageField(upload_to='ads/single/', blank=True, null=True)
    video = models.FileField(
        upload_to='ads/videos/',
        blank=True,
        null=True,
        validators=[FileExtensionValidator(allowed_extensions=['mp4', 'webm', 'ogg'])]
    )
    video_poster = models.ImageField(upload_to='ads/posters/', blank=True, null=True)
    autoplay = models.BooleanField(default=False)
    loop = models.BooleanField(default=True)
    
    headline = models.CharField(max_length=200, blank=True)
    subheadline = models.CharField(max_length=300, blank=True)
    button_text = models.CharField(max_length=50, blank=True, default="Shop Now")
    button_url = models.URLField(blank=True)
    button_color = models.CharField(max_length=20, default="#667eea")
    
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    show_on_mobile = models.BooleanField(default=True)
    show_on_tablet = models.BooleanField(default=True)
    show_on_desktop = models.BooleanField(default=True)
    
    background_color = models.CharField(max_length=20, blank=True)
    text_color = models.CharField(max_length=20, default="#ffffff")
    overlay_opacity = models.FloatField(default=0.3)
    
    start_date = models.DateTimeField(null=True, blank=True)
    end_date = models.DateTimeField(null=True, blank=True)
    
    views = models.PositiveIntegerField(default=0, editable=False)
    clicks = models.PositiveIntegerField(default=0, editable=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['order', '-created_at']
        verbose_name = "Advertisement"
        verbose_name_plural = "Advertisements"
    
    def __str__(self):
        return f"{self.title} ({self.get_ad_type_display()})"
    
    def increment_views(self):
        self.views += 1
        self.save(update_fields=['views'])
    
    def increment_clicks(self):
        self.clicks += 1
        self.save(update_fields=['clicks'])
    
    def get_images(self):
        return self.ad_images.all().order_by('order')


class AdImage(models.Model):
    advertisement = models.ForeignKey(Advertisement, on_delete=models.CASCADE, related_name='ad_images')
    image = models.ImageField(upload_to='ads/multi/')
    caption = models.CharField(max_length=200, blank=True)
    order = models.PositiveIntegerField(default=0)
    
    class Meta:
        ordering = ['order']
        verbose_name = "Ad Image"
        verbose_name_plural = "Ad Images"
    
    def __str__(self):
        return f"Image for {self.advertisement.title}"


class AdImpression(models.Model):
    advertisement = models.ForeignKey(Advertisement, on_delete=models.CASCADE)
    session_key = models.CharField(max_length=40)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    viewed_at = models.DateTimeField(auto_now_add=True)
    clicked = models.BooleanField(default=False)
    
    class Meta:
        indexes = [
            models.Index(fields=['session_key', 'advertisement']),
        ]
    
    def __str__(self):
        return f"Impression for {self.advertisement.title} at {self.viewed_at}"


class MpesaPayment(models.Model):
    checkout_request_id = models.CharField(max_length=100, unique=True)
    phone_number = models.CharField(max_length=20)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    mpesa_receipt_number = models.CharField(max_length=50, blank=True, null=True)
    transaction_date = models.DateTimeField(null=True, blank=True)
    result_code = models.IntegerField(null=True, blank=True)
    result_desc = models.CharField(max_length=200, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('success', 'Success'),
            ('failed', 'Failed'),
            ('cancelled', 'Cancelled'),
        ],
        default='pending'
    )
    session_key = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.checkout_request_id} - {self.status}"