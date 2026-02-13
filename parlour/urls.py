from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),

     path('googleb193ab12b0274614/', views.google_v, name='googleb193ab12b0274614'),
    path('product/<int:product_id>/', views.product_detail, name='product_detail'),
    path('add-to-cart/<int:product_id>/', views.add_to_cart, name='add_to_cart'),
    path('cart/', views.cart, name='cart'),
    path('remove-from-cart/<str:cart_key>/', views.remove_from_cart, name='remove_from_cart'),
    path('checkout/', views.checkout, name='checkout'),
    path('mpesa-payment/', views.mpesa_payment, name='mpesa_payment'),
    path('confirm-mpesa-payment/', views.confirm_mpesa_payment, name='confirm_mpesa_payment'),
    path('mpesa-callback/', views.mpesa_callback, name='mpesa_callback'),
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
   
]
