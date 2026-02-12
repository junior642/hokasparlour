from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from datetime import timedelta

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
        # Ensure only one instance exists
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
    
    name = models.CharField(max_length=200)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    image = models.ImageField(upload_to='products/')
    available_sizes = models.CharField(max_length=100, help_text="Comma-separated sizes (e.g., S,M,L,XL)")
    stock_quantity = models.PositiveIntegerField(default=1, help_text="Number of items available in stock")
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name
    
    def is_in_stock(self):
        return self.stock_quantity > 0
    
    class Meta:
        ordering = ['-created_at']


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
    
    def get_pickup_info(self):
        """Get global pickup information from store settings"""
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
        """Calculate subtotal - ensure it returns a Decimal"""
        from decimal import Decimal
        try:
            # Convert both to Decimal to ensure proper arithmetic
            qty = Decimal(str(self.quantity))
            price = self.price if isinstance(self.price, Decimal) else Decimal(str(self.price))
            return qty * price
        except (TypeError, ValueError, decimal.InvalidOperation):
            return Decimal('0.00')


class EmailOTP(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"OTP for {self.user.username}"
    
    class Meta:
        verbose_name = 'Email OTP'
        verbose_name_plural = 'Email OTPs'


# parlour/models.py - Add this at the end of the file

from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    phone_number = models.CharField(max_length=20, blank=True)
    delivery_address = models.TextField(blank=True)
    default_delivery_location = models.CharField(max_length=200, blank=True)
    profile_picture = models.ImageField(upload_to='profiles/', blank=True, null=True)
    
    # Additional user preferences
    preferred_payment_method = models.CharField(
        max_length=20,
        choices=[
            ('mpesa', 'M-Pesa'),
            ('cash', 'Cash on Delivery'),
        ],
        default='mpesa',
        blank=True
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user.username}'s Profile"
    
    def get_full_address(self):
        """Return full delivery address"""
        return self.delivery_address or 'No address saved'
    
    def has_complete_profile(self):
        """Check if profile has all necessary details"""
        return bool(
            self.phone_number and 
            self.delivery_address
        )
    
    class Meta:
        verbose_name = 'Profile'
        verbose_name_plural = 'Profiles'


# Signal to automatically create/update profile when user is created/updated
@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)
    else:
        # Only create if it doesn't exist, otherwise save
        Profile.objects.get_or_create(user=instance)
        instance.profile.save()


# Order history model (for better tracking)
class OrderHistory(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='order_history')
    order = models.ForeignKey('Order', on_delete=models.CASCADE)
    viewed_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-viewed_at']
        verbose_name = 'Order History'
        verbose_name_plural = 'Order Histories'        