from django.urls import path
from . import views

app_name = 'finance'

urlpatterns = [
    path('',                          views.finance_dashboard,  name='dashboard'),
    path('budget/create/',            views.create_budget,      name='create_budget'),
    path('expense/log/',              views.log_expense,        name='log_expense'),
    path('expense/<int:pk>/delete/',  views.delete_expense,     name='delete_expense'),
    path('capital/log/',              views.log_capital,        name='log_capital'),
    path('categories/',               views.manage_categories,  name='categories'),
    path('categories/<int:pk>/delete/', views.delete_category,  name='delete_category'),
    path('alerts/<int:pk>/dismiss/',  views.dismiss_alert,      name='dismiss_alert'),
    path('summary/',                  views.monthly_summary,    name='monthly_summary'),
]