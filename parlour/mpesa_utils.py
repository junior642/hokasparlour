import requests
import base64
from datetime import datetime
from django.conf import settings


def get_mpesa_access_token():
    """Get OAuth access token from Safaricom"""
    consumer_key = settings.MPESA_CONSUMER_KEY
    consumer_secret = settings.MPESA_CONSUMER_SECRET
    
    # Encode credentials
    credentials = f"{consumer_key}:{consumer_secret}"
    encoded = base64.b64encode(credentials.encode()).decode()
    
    url = 'https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials'
    
    headers = {
        'Authorization': f'Basic {encoded}',
        'Content-Type': 'application/json'
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json().get('access_token')
    except Exception as e:
        print(f"Error getting access token: {e}")
        return None


def generate_password():
    """Generate M-Pesa API password"""
    shortcode = settings.MPESA_SHORTCODE
    passkey = settings.MPESA_PASSKEY
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    
    raw_string = f"{shortcode}{passkey}{timestamp}"
    encoded = base64.b64encode(raw_string.encode()).decode()
    
    return encoded, timestamp


def stk_push(phone_number, amount, order_id):
    """Initiate STK Push to customer's phone"""
    
    access_token = get_mpesa_access_token()
    
    if not access_token:
        return {'success': False, 'message': 'Could not get access token'}
    
    password, timestamp = generate_password()
    
    # Format phone number (ensure it starts with 254)
    phone = format_phone_number(phone_number)
    
    url = 'https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest'
    
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }
    
    payload = {
        'BusinessShortCode': settings.MPESA_SHORTCODE,
        'Password': password,
        'Timestamp': timestamp,
        'TransactionType': 'CustomerPayBillOnline',
        'Amount': int(amount),
        'PartyA': phone,
        'PartyB': settings.MPESA_SHORTCODE,
        'PhoneNumber': phone,
        'CallBackURL': settings.MPESA_CALLBACK_URL,
        'AccountReference': f'HOKA{order_id}',
        'TransactionDesc': f'Payment for Order #{order_id} - Hokas Parlour'
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        result = response.json()
        
        if result.get('ResponseCode') == '0':
            return {
                'success': True,
                'checkout_request_id': result.get('CheckoutRequestID'),
                'message': 'STK Push sent successfully'
            }
        else:
            return {
                'success': False,
                'message': result.get('ResponseDescription', 'STK Push failed')
            }
    except Exception as e:
        print(f"STK Push error: {e}")
        return {'success': False, 'message': str(e)}


def format_phone_number(phone):
    """Format phone number to 254 format"""
    phone = str(phone).strip().replace(' ', '').replace('-', '')
    
    if phone.startswith('+254'):
        return phone[1:]  # Remove + sign
    elif phone.startswith('0'):
        return '254' + phone[1:]  # Replace leading 0 with 254
    elif phone.startswith('254'):
        return phone
    else:
        return '254' + phone