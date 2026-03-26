from django.urls import path
from . import views

urlpatterns = [
    path('', views.whatsapp_dashboard, name='whatsapp_dashboard'),
    path('send/', views.send_single_message, name='whatsapp_send_single'),
    path('send-bulk/', views.send_bulk_message, name='whatsapp_send_bulk'),
    path('status/', views.whatsapp_status, name='whatsapp_status'),
]