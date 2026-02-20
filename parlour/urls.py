from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('product/<int:product_id>/', views.product_detail, name='product_detail'),
    path('add-to-cart/<int:product_id>/', views.add_to_cart, name='add_to_cart'),
    path('cart/', views.cart, name='cart'),
    path('remove-from-cart/<str:cart_key>/', views.remove_from_cart, name='remove_from_cart'),
    path('checkout/', views.checkout, name='checkout'),
    path('mpesa-payment/', views.mpesa_payment, name='mpesa_payment'),
    path('confirm-mpesa-payment/', views.confirm_mpesa_payment, name='confirm_mpesa_payment'),
    path('mpesa-callback/', views.mpesa_callback, name='mpesa_callback'),
    path('check-payment-status/', views.check_payment_status, name='check_payment_status'),
    path('process-cash-order/', views.process_cash_order, name='process_cash_order'),
    path('order-confirmation/<int:order_id>/', views.order_confirmation, name='order_confirmation'),
    path('order-tracking/', views.order_tracking, name='order_tracking'),
    path('login/', views.user_login, name='login'),
    path('signup/', views.user_signup, name='signup'),
    path('verify-otp/', views.verify_otp, name='verify_otp'),
    path('logout/', views.user_logout, name='logout'),
    path('profile/', views.profile, name='profile'),
    path('profile/edit/', views.edit_profile, name='edit_profile'),
    path('profile/change-password/', views.change_password, name='change_password'),
    path('profile/orders/', views.order_history, name='order_history'),
    path('profile/save-for-later/', views.save_for_later, name='save_for_later'),
    path('profile/load-saved/', views.load_saved_items, name='load_saved_items'),
    path('about/', views.about, name='about'),
    path('terms/', views.terms, name='terms'),
    path('privacy/', views.privacy, name='privacy'),
    path('contact/', views.contact, name='contact'),
    path('welcome/', views.welcome, name='welcome'),
    path('returns/', views.returns, name='returns'),
    path('shipping/', views.delivery, name='shipping'),
    path('product/<int:product_id>/', views.product_detail, name='product_detail'),
    path('ad/<int:ad_id>/click/', views.ad_click, name='ad_click'),

    path('orders/', views.orders_dashboard, name='orders_dashboard'),
    path('orders/<int:order_id>/', views.order_detail, name='order_detail'),
    path('orders/<int:order_id>/update-status/', views.update_order_status, name='update_order_status'),

    # Advertisement Management URLs
    path('ads/', views.ad_list, name='ad_list'),
    path('ads/create/', views.ad_create, name='ad_create'),
    path('ads/<int:ad_id>/', views.ad_detail, name='ad_detail'),
    path('ads/<int:ad_id>/edit/', views.ad_edit, name='ad_edit'),
    path('ads/<int:ad_id>/delete/', views.ad_delete, name='ad_delete'),
    path('ads/<int:ad_id>/toggle-status/', views.ad_toggle_status, name='ad_toggle_status'),
    path('ads/<int:ad_id>/images/add/', views.ad_image_add, name='ad_image_add'),
    path('ads/images/<int:image_id>/delete/', views.ad_image_delete, name='ad_image_delete'),


    # Product Management (Staff Only)
    path('manage-products/', views.manage_products, name='manage_products'),
    path('add-product/', views.add_product, name='add_product'),
    path('edit-product/<int:product_id>/', views.edit_product, name='edit_product'),
    path('delete-product/<int:product_id>/', views.delete_product, name='delete_product'),
    path('delete-product-image/<int:image_id>/', views.delete_product_image, name='delete_product_image'),
]