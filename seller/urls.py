# ✅ seller/urls.py
from django.urls import path
from . import views

app_name = 'seller'

urlpatterns = [
    path('apply/',                        views.seller_apply,          name='seller_apply'),
    path('dashboard/',                    views.seller_dashboard,      name='seller_dashboard'),
    path('products/',                     views.seller_products,       name='seller_products'),
    path('products/add/',                 views.seller_product_add,    name='seller_product_add'),
    path('products/<int:pk>/edit/',       views.seller_product_edit,   name='seller_product_edit'),
    path('products/<int:pk>/delete/',     views.seller_product_delete, name='seller_product_delete'),
    path('products/<int:pk>/toggle/',     views.seller_product_toggle, name='seller_product_toggle'),
    path('orders/',                       views.seller_orders,         name='seller_orders'),
    path('orders/<int:pk>/',              views.seller_order_detail,   name='seller_order_detail'),
    path('settings/',                     views.seller_store_settings, name='seller_store_settings'),
    path('categories/',               views.seller_categories,      name='seller_categories'),
    path('categories/add/',           views.seller_category_add,    name='seller_category_add'),
    path('categories/<int:pk>/edit/', views.seller_category_edit,   name='seller_category_edit'),
    path('categories/<int:pk>/delete/', views.seller_category_delete, name='seller_category_delete'),
]