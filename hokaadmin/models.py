from django.db import models
from parlour.models import Order, Product

class SalesRecord(models.Model):
    order = models.OneToOneField(Order, on_delete=models.CASCADE)
    total_items = models.PositiveIntegerField()
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    profit_estimate = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    sale_date = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Sales Record #{self.id} - Order #{self.order.id}"
    
    class Meta:
        ordering = ['-sale_date']


class ProductStats(models.Model):
    product = models.OneToOneField(Product, on_delete=models.CASCADE)
    total_sold = models.PositiveIntegerField(default=0)
    total_revenue = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    last_sold_date = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"Stats for {self.product.name}"
    
    class Meta:
        verbose_name_plural = "Product Stats"


class EmailLog(models.Model):
    STATUS_CHOICES = [
        ('sent', 'Sent'),
        ('failed', 'Failed'),
    ]
    
    recipient_email = models.EmailField()
    subject = models.CharField(max_length=255)
    message = models.TextField()
    sent_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    
    def __str__(self):
        return f"{self.subject} to {self.recipient_email} - {self.status}"
    
    class Meta:
        ordering = ['-sent_at']