from django.shortcuts import render
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.contrib.auth.models import User
from django.views.decorators.http import require_POST
from parlour.models import Order
from whatsapphoka.service import send_whatsapp_message
import json
import logging

logger = logging.getLogger(__name__)


@staff_member_required
def whatsapp_dashboard(request):
    """Main WhatsApp messaging dashboard for staff/admin."""

    # Get all customers who have placed orders (have a phone number)
    customers = (
        Order.objects
        .values('customer_name', 'phone_number', 'email')
        .distinct()
        .order_by('customer_name')
    )

    # Quick stats
    total_customers = customers.count()

    context = {
        'customers': customers,
        'total_customers': total_customers,
        'page_title': 'WhatsApp Messenger',
    }
    return render(request, 'whatsapp/dashboard.html', context)


@staff_member_required
@require_POST
def send_single_message(request):
    """Send a WhatsApp message to a single customer."""
    try:
        data = json.loads(request.body)
        phone = data.get('phone', '').strip()
        message = data.get('message', '').strip()
        customer_name = data.get('customer_name', 'Customer')

        if not phone or not message:
            return JsonResponse({'success': False, 'error': 'Phone and message are required'}, status=400)

        result = send_whatsapp_message(phone, message)

        if result.get('success'):
            logger.info(f"Staff {request.user.username} sent WhatsApp to {phone}")
            return JsonResponse({'success': True, 'message': f'Message sent to {customer_name}'})
        else:
            return JsonResponse({'success': False, 'error': result.get('error', 'Failed to send')}, status=500)

    except Exception as e:
        logger.error(f"Single send error: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@staff_member_required
@require_POST
def send_bulk_message(request):
    """Send a WhatsApp message to all customers."""
    try:
        data = json.loads(request.body)
        message = data.get('message', '').strip()

        if not message:
            return JsonResponse({'success': False, 'error': 'Message is required'}, status=400)

        # Get unique phone numbers from all orders
        customers = (
            Order.objects
            .values('customer_name', 'phone_number')
            .distinct()
        )

        sent = 0
        failed = 0
        errors = []

        for customer in customers:
            phone = customer['phone_number']
            name = customer['customer_name']

            if not phone:
                continue

            # Personalize message with customer name
            personalized = message.replace('{name}', name.split()[0])

            result = send_whatsapp_message(phone, personalized)
            if result.get('success'):
                sent += 1
            else:
                failed += 1
                errors.append(f"{name} ({phone}): {result.get('error', 'unknown error')}")

        logger.info(f"Staff {request.user.username} sent bulk WhatsApp: {sent} sent, {failed} failed")

        return JsonResponse({
            'success': True,
            'sent': sent,
            'failed': failed,
            'errors': errors[:5],  # Return first 5 errors only
        })

    except Exception as e:
        logger.error(f"Bulk send error: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@staff_member_required
def whatsapp_status(request):
    """Check if WhatsApp Node service is online."""
    try:
        import requests
        from django.conf import settings
        url = getattr(settings, 'WHATSAPP_SERVICE_URL', 'http://localhost:3000')
        response = requests.get(f"{url}/status", timeout=5)
        data = response.json()
        return JsonResponse({'online': True, 'ready': data.get('ready', False)})
    except Exception:
        return JsonResponse({'online': False, 'ready': False})