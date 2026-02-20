from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from decimal import Decimal


class BudgetCategory(models.Model):
    """Custom budget categories — user can create their own."""
    ICON_CHOICES = [
        ('📦', 'Stock/Inventory'),
        ('🚚', 'Transport'),
        ('📦', 'Packaging'),
        ('📣', 'Marketing'),
        ('💡', 'Utilities'),
        ('🧾', 'Tax/Fees'),
        ('🔧', 'Maintenance'),
        ('📱', 'Communication'),
        ('💰', 'Other'),
    ]

    name  = models.CharField(max_length=100, unique=True)
    icon  = models.CharField(max_length=10, default='💰')
    color = models.CharField(max_length=7, default='#c9a84c', help_text='Hex color e.g. #c9a84c')
    is_stock_category = models.BooleanField(
        default=False,
        help_text='Mark this if the category is for buying stock/products'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Budget Category'
        verbose_name_plural = 'Budget Categories'
        ordering = ['name']

    def __str__(self):
        return f"{self.icon} {self.name}"


class MonthlyBudget(models.Model):
    """
    One budget per calendar month.
    Represents the total capital available for that month.
    """
    year  = models.PositiveIntegerField()
    month = models.PositiveIntegerField()  # 1–12
    total_capital = models.DecimalField(
        max_digits=12, decimal_places=2,
        help_text='Total money available this month (KSH)'
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('year', 'month')
        ordering = ['-year', '-month']
        verbose_name = 'Monthly Budget'
        verbose_name_plural = 'Monthly Budgets'

    def __str__(self):
        import calendar
        return f"{calendar.month_name[self.month]} {self.year}"

    def get_month_display(self):
        import calendar
        return f"{calendar.month_name[self.month]} {self.year}"

    def total_allocated(self):
        return self.allocations.aggregate(
            total=models.Sum('allocated_amount')
        )['total'] or Decimal('0.00')

    def total_spent(self):
        return self.allocations.aggregate(
            total=models.Sum('spent_amount')
        )['total'] or Decimal('0.00')

    def unallocated(self):
        return self.total_capital - self.total_allocated()

    def remaining(self):
        return self.total_capital - self.total_spent()

    def utilization_percent(self):
        if self.total_capital > 0:
            return round((float(self.total_spent()) / float(self.total_capital)) * 100, 1)
        return 0


class BudgetAllocation(models.Model):
    """
    How much of the monthly budget is allocated to each category,
    and how much has been spent against it.
    """
    budget           = models.ForeignKey(MonthlyBudget, on_delete=models.CASCADE, related_name='allocations')
    category         = models.ForeignKey(BudgetCategory, on_delete=models.CASCADE)
    allocated_amount = models.DecimalField(max_digits=12, decimal_places=2)
    spent_amount     = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

    class Meta:
        unique_together = ('budget', 'category')
        verbose_name = 'Budget Allocation'

    def __str__(self):
        return f"{self.budget} — {self.category.name}"

    def remaining(self):
        return self.allocated_amount - self.spent_amount

    def percent_used(self):
        if self.allocated_amount > 0:
            return round((float(self.spent_amount) / float(self.allocated_amount)) * 100, 1)
        return 0

    def is_over_budget(self):
        return self.spent_amount > self.allocated_amount


class Expense(models.Model):
    """Individual expense entries logged by the owner."""
    budget      = models.ForeignKey(MonthlyBudget, on_delete=models.CASCADE, related_name='expenses')
    category    = models.ForeignKey(BudgetCategory, on_delete=models.CASCADE)
    amount      = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.CharField(max_length=300)
    date        = models.DateField(default=timezone.now)
    receipt_note = models.TextField(blank=True, help_text='Optional: receipt number or extra notes')
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']
        verbose_name = 'Expense'

    def __str__(self):
        return f"{self.description} — KSH {self.amount} ({self.date})"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Auto-update the allocation's spent_amount
        self._sync_allocation()

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        self._sync_allocation()

    def _sync_allocation(self):
        """Recalculate spent_amount for the matching allocation."""
        try:
            allocation = BudgetAllocation.objects.get(
                budget=self.budget,
                category=self.category
            )
            total = Expense.objects.filter(
                budget=self.budget,
                category=self.category
            ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
            allocation.spent_amount = total
            allocation.save(update_fields=['spent_amount'])
        except BudgetAllocation.DoesNotExist:
            pass


class CapitalEntry(models.Model):
    """
    Track money flowing in or out of the business (not sales revenue).
    e.g. 'Invested KSH 20,000 from savings' or 'Withdrew KSH 5,000 profit'
    """
    ENTRY_TYPES = [
        ('in',  'Capital In'),   # money added to business
        ('out', 'Capital Out'),  # money withdrawn from business
    ]

    budget      = models.ForeignKey(MonthlyBudget, on_delete=models.CASCADE, related_name='capital_entries')
    entry_type  = models.CharField(max_length=5, choices=ENTRY_TYPES)
    amount      = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.CharField(max_length=300)
    date        = models.DateField(default=timezone.now)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']
        verbose_name = 'Capital Entry'
        verbose_name_plural = 'Capital Entries'

    def __str__(self):
        return f"{self.get_entry_type_display()} — KSH {self.amount} ({self.date})"


class RestockAlert(models.Model):
    """
    Auto-generated alert when a ready-stock product falls to ≤ 3.
    Dismissed once the owner restocks or manually clears it.
    """
    from parlour.models import Product  # avoid circular import at module level

    product    = models.ForeignKey('parlour.Product', on_delete=models.CASCADE, related_name='restock_alerts')
    qty_at_alert = models.PositiveIntegerField()
    estimated_restock_cost = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text='Auto-calculated: purchase_cost × restock_qty_needed'
    )
    is_dismissed = models.BooleanField(default=False)
    created_at   = models.DateTimeField(auto_now_add=True)
    dismissed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Restock Alert'

    def __str__(self):
        return f"Restock alert: {self.product.name} (qty: {self.qty_at_alert})"

    def dismiss(self):
        self.is_dismissed = True
        self.dismissed_at = timezone.now()
        self.save(update_fields=['is_dismissed', 'dismissed_at'])