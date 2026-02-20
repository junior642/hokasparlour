from django.urls import path
from . import views

app_name = 'hokaadmin'

urlpatterns = [
    path('', views.admin_dashboard, name='dashboard'),
    path('sales-summary/', views.sales_summary, name='sales_summary'),
    path('daily-sales/', views.daily_sales, name='daily_sales'),
    path('weekly-sales/', views.weekly_sales, name='weekly_sales'),
    path('monthly-sales/', views.monthly_sales, name='monthly_sales'),
    path('top-products/', views.top_products, name='top_products'),
    path('revenue-trends/', views.revenue_trends, name='revenue_trends'),
    path('profit-report/', views.profit_report, name='profit_report'),
    path('stock-report/',  views.stock_report,  name='stock_report'),
    path('analytics/', views.analytics_charts, name='analytics_charts'),
]