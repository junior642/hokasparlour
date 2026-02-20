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
    pickup_location = models.CharField(max_length=300, default='Hoka\'s Parlour Main Store, 123 Fashion Street')
    pickup_date = models.DateField(default=timezone.now, help_text='Pickup date for all orders')
    pickup_time = models.TimeField(default='22:00:00', help_text='Pickup time (e.g., 10:00 PM)')
    pickup_days_info = models.TextField(default='Monday - Saturday', help_text='Pickup days information')
    store_phone = models.CharField(max_length=20, default='+254 700 000 000')
    store_email = models.EmailField(default='hokasparlour@gmail.com')
    
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
        settings, created = cls.objects.get_or_create(
            id=1,
            defaults={
                'pickup_date': (timezone.now() + timedelta(days=1)).date()
            }
        )
        return settings


class Product(models.Model):
    CATEGORY_CHOICES = [
        ('hoodies', 'Hoodies'),
        ('sweatpants', 'Sweatpants'),
        ('socks', 'Socks'),
        ('shorts', 'Shorts'),
        ('shirts', 'Shirts'),
    ]

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
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    
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
    def get_delivery_type(self):
        if self.stock_type == 'ready':
            return "Next Day Delivery"
        return "Friday Delivery"

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
        return {
            'location': settings.pickup_location,
            'date': settings.pickup_date,
            'time': settings.pickup_time,
            'days': settings.pickup_days_info
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