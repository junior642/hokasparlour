from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.db.models import Sum
from parlour.models import Product, Order, OrderItem
from .models import (
    MonthlyBudget, BudgetCategory, BudgetAllocation,
    Expense, CapitalEntry, RestockAlert
)
from decimal import Decimal
import calendar


# ── Helpers ───────────────────────────────────────────────────────

def get_or_create_restock_alerts():
    """Check all ready stock products and create alerts for low ones."""
    low_products = Product.objects.filter(stock_type='ready', stock_quantity__lte=3)
    for product in low_products:
        # Only create if no active alert exists
        if not RestockAlert.objects.filter(product=product, is_dismissed=False).exists():
            cost = None
            if product.purchase_cost:
                needed = max(10 - product.stock_quantity, 5)  # suggest restocking to at least 10
                cost = product.purchase_cost * needed
            RestockAlert.objects.create(
                product=product,
                qty_at_alert=product.stock_quantity,
                estimated_restock_cost=cost
            )


def get_monthly_revenue(year, month):
    """Revenue from delivered orders in a given month."""
    orders = Order.objects.filter(
        order_status='delivered',
        created_at__year=year,
        created_at__month=month
    )
    total = Decimal('0.00')
    for order in orders:
        total += order.get_total()
    return total


def get_monthly_cogs(year, month):
    """Cost of goods sold in a given month (from delivered orders)."""
    items = OrderItem.objects.filter(
        order__order_status='delivered',
        order__created_at__year=year,
        order__created_at__month=month
    ).select_related('product')

    total = Decimal('0.00')
    for item in items:
        cost = item.get_cost_total()
        if cost:
            total += cost
    return total


# ── Views ─────────────────────────────────────────────────────────

@login_required
def finance_dashboard(request):
    """Main finance overview for the current month."""
    get_or_create_restock_alerts()

    now   = timezone.now()
    year  = int(request.GET.get('year',  now.year))
    month = int(request.GET.get('month', now.month))

    # Get or hint at budget
    budget = MonthlyBudget.objects.filter(year=year, month=month).first()

    # Revenue & COGS from orders
    revenue = get_monthly_revenue(year, month)
    cogs    = get_monthly_cogs(year, month)

    # Expenses logged this month
    expenses_total = Decimal('0.00')
    allocations    = []
    if budget:
        expenses_total = budget.total_spent()
        allocations = budget.allocations.select_related('category').all()

    gross_profit = revenue - cogs
    net_profit   = gross_profit - expenses_total

    # Restock alerts
    active_alerts = RestockAlert.objects.filter(is_dismissed=False).select_related('product')

    # Recent expenses
    recent_expenses = []
    if budget:
        recent_expenses = budget.expenses.select_related('category').order_by('-date')[:8]

    # Capital entries
    capital_in  = Decimal('0.00')
    capital_out = Decimal('0.00')
    if budget:
        capital_in  = budget.capital_entries.filter(entry_type='in').aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
        capital_out = budget.capital_entries.filter(entry_type='out').aggregate(t=Sum('amount'))['t'] or Decimal('0.00')

    # Month navigation
    prev_month = month - 1 if month > 1 else 12
    prev_year  = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year  = year if month < 12 else year + 1

    context = {
        'budget':          budget,
        'year':            year,
        'month':           month,
        'month_name':      calendar.month_name[month],
        'revenue':         revenue,
        'cogs':            cogs,
        'gross_profit':    gross_profit,
        'expenses_total':  expenses_total,
        'net_profit':      net_profit,
        'allocations':     allocations,
        'active_alerts':   active_alerts,
        'recent_expenses': recent_expenses,
        'capital_in':      capital_in,
        'capital_out':     capital_out,
        'prev_month':      prev_month,
        'prev_year':       prev_year,
        'next_month':      next_month,
        'next_year':       next_year,
    }
    return render(request, 'finance/dashboard.html', context)


@login_required
def create_budget(request):
    """Create a monthly budget and its allocations."""
    categories = BudgetCategory.objects.all()

    if request.method == 'POST':
        year          = int(request.POST.get('year'))
        month         = int(request.POST.get('month'))
        total_capital = Decimal(request.POST.get('total_capital', '0'))
        notes         = request.POST.get('notes', '')

        budget, created = MonthlyBudget.objects.get_or_create(
            year=year, month=month,
            defaults={'total_capital': total_capital, 'notes': notes}
        )

        if not created:
            budget.total_capital = total_capital
            budget.notes = notes
            budget.save()

        # Save allocations
        for cat in categories:
            amount_key = f'allocation_{cat.id}'
            amount = request.POST.get(amount_key, '0')
            try:
                amount = Decimal(amount)
            except Exception:
                amount = Decimal('0.00')

            if amount > 0:
                BudgetAllocation.objects.update_or_create(
                    budget=budget, category=cat,
                    defaults={'allocated_amount': amount}
                )

        messages.success(request, f'Budget for {calendar.month_name[month]} {year} saved.')
        return redirect('finance:dashboard')

    now = timezone.now()
    context = {
        'categories': categories,
        'current_year':  now.year,
        'current_month': now.month,
        'month_choices': [(i, calendar.month_name[i]) for i in range(1, 13)],
    }
    return render(request, 'finance/create_budget.html', context)


@login_required
def log_expense(request):
    """Log a new expense against the current month's budget."""
    now    = timezone.now()
    year   = int(request.GET.get('year',  now.year))
    month  = int(request.GET.get('month', now.month))
    budget = MonthlyBudget.objects.filter(year=year, month=month).first()

    if not budget:
        messages.warning(request, f'No budget found for {calendar.month_name[month]} {year}. Please create one first.')
        return redirect('finance:create_budget')

    categories = BudgetCategory.objects.all()

    if request.method == 'POST':
        category_id = request.POST.get('category')
        amount      = Decimal(request.POST.get('amount', '0'))
        description = request.POST.get('description', '')
        date        = request.POST.get('date', str(now.date()))
        receipt     = request.POST.get('receipt_note', '')

        category = get_object_or_404(BudgetCategory, id=category_id)

        Expense.objects.create(
            budget=budget,
            category=category,
            amount=amount,
            description=description,
            date=date,
            receipt_note=receipt
        )

        messages.success(request, f'Expense of KSH {amount} logged under {category.name}.')
        return redirect('finance:dashboard')

    context = {
        'budget':     budget,
        'categories': categories,
        'today':      now.date(),
    }
    return render(request, 'finance/log_expense.html', context)


@login_required
def log_capital(request):
    """Log capital in or out."""
    now    = timezone.now()
    year   = int(request.GET.get('year',  now.year))
    month  = int(request.GET.get('month', now.month))
    budget = MonthlyBudget.objects.filter(year=year, month=month).first()

    if not budget:
        messages.warning(request, 'No budget found for this month. Create one first.')
        return redirect('finance:create_budget')

    if request.method == 'POST':
        entry_type  = request.POST.get('entry_type')
        amount      = Decimal(request.POST.get('amount', '0'))
        description = request.POST.get('description', '')
        date        = request.POST.get('date', str(now.date()))

        CapitalEntry.objects.create(
            budget=budget,
            entry_type=entry_type,
            amount=amount,
            description=description,
            date=date
        )

        label = 'added to' if entry_type == 'in' else 'withdrawn from'
        messages.success(request, f'KSH {amount} {label} business capital.')
        return redirect('finance:dashboard')

    context = {
        'budget': budget,
        'today':  now.date(),
    }
    return render(request, 'finance/log_capital.html', context)


@login_required
def manage_categories(request):
    """Create and view budget categories."""
    if request.method == 'POST':
        name  = request.POST.get('name', '').strip()
        icon  = request.POST.get('icon', '💰')
        color = request.POST.get('color', '#c9a84c')
        is_stock = request.POST.get('is_stock_category') == 'on'

        if name:
            BudgetCategory.objects.get_or_create(
                name=name,
                defaults={'icon': icon, 'color': color, 'is_stock_category': is_stock}
            )
            messages.success(request, f'Category "{name}" created.')
        return redirect('finance:categories')

    categories = BudgetCategory.objects.all()
    context = {'categories': categories}
    return render(request, 'finance/categories.html', context)


@login_required
def delete_category(request, pk):
    category = get_object_or_404(BudgetCategory, pk=pk)
    if request.method == 'POST':
        category.delete()
        messages.success(request, 'Category deleted.')
    return redirect('finance:categories')


@login_required
def delete_expense(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    if request.method == 'POST':
        expense.delete()
        messages.success(request, 'Expense deleted.')
    return redirect('finance:dashboard')


@login_required
def dismiss_alert(request, pk):
    alert = get_object_or_404(RestockAlert, pk=pk)
    if request.method == 'POST':
        alert.dismiss()
        messages.success(request, f'Alert for {alert.product.name} dismissed.')
    return redirect('finance:dashboard')


@login_required
def monthly_summary(request):
    """Full P&L summary for a selected month."""
    now   = timezone.now()
    year  = int(request.GET.get('year',  now.year))
    month = int(request.GET.get('month', now.month))

    budget   = MonthlyBudget.objects.filter(year=year, month=month).first()
    revenue  = get_monthly_revenue(year, month)
    cogs     = get_monthly_cogs(year, month)
    expenses = Decimal('0.00')
    if budget:
        expenses = budget.total_spent()

    gross_profit = revenue - cogs
    net_profit   = gross_profit - expenses

    # Expense breakdown by category
    expense_breakdown = []
    if budget:
        for alloc in budget.allocations.select_related('category').all():
            expense_breakdown.append({
                'category':  alloc.category,
                'allocated': alloc.allocated_amount,
                'spent':     alloc.spent_amount,
                'remaining': alloc.remaining(),
                'pct':       alloc.percent_used(),
                'over':      alloc.is_over_budget(),
            })

    # All expenses list
    all_expenses = []
    if budget:
        all_expenses = budget.expenses.select_related('category').order_by('-date')

    # Capital
    capital_in  = Decimal('0.00')
    capital_out = Decimal('0.00')
    if budget:
        capital_in  = budget.capital_entries.filter(entry_type='in').aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
        capital_out = budget.capital_entries.filter(entry_type='out').aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
        capital_entries = budget.capital_entries.order_by('-date')
    else:
        capital_entries = []

    context = {
        'budget':             budget,
        'year':               year,
        'month':              month,
        'month_name':         calendar.month_name[month],
        'revenue':            revenue,
        'cogs':               cogs,
        'gross_profit':       gross_profit,
        'expenses':           expenses,
        'net_profit':         net_profit,
        'expense_breakdown':  expense_breakdown,
        'all_expenses':       all_expenses,
        'capital_in':         capital_in,
        'capital_out':        capital_out,
        'capital_entries':    capital_entries,
        'month_choices':      [(i, calendar.month_name[i]) for i in range(1, 13)],
        'current_year':       now.year,
    }
    return render(request, 'finance/monthly_summary.html', context)