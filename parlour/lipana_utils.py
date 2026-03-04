import requests
import os

LIPANA_API_BASE = "https://api.lipana.dev/v1"
LIPANA_SECRET_KEY = os.getenv("LIPANA_SECRET_KEY")


def format_phone(phone: str) -> str:
    phone = phone.strip().replace(" ", "").replace("-", "")
    if phone.startswith('+254'):
        return phone
    elif phone.startswith('254'):
        return '+' + phone
    elif phone.startswith('07') or phone.startswith('01'):
        return '+254' + phone[1:]
    elif phone.startswith('7') or phone.startswith('1'):
        return '+254' + phone
    return phone


def stk_push(phone: str, amount: float, reference: str = None) -> dict:
    url = f"{LIPANA_API_BASE}/transactions/push-stk"
    headers = {
        "x-api-key": LIPANA_SECRET_KEY,
        "Content-Type": "application/json",
    }

    formatted_phone = format_phone(phone)
    payload = {
        "phone": formatted_phone,
        "amount": int(amount),
    }

    print(f"STK Push → phone: {formatted_phone}, amount: {int(amount)}")
    print(f"Using API key: {LIPANA_SECRET_KEY[:20]}..." if LIPANA_SECRET_KEY else "⚠️ NO API KEY FOUND")

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        
        # Print full raw response for debugging
        print(f"Status code: {response.status_code}")
        print(f"Raw response: {response.text}")

        data = response.json()

        if response.status_code in (200, 201) and data.get("success"):
            # Handle both possible response structures
            response_data = data.get("data", {})
            
            checkout_id = (
                response_data.get("checkoutRequestID") or
                response_data.get("CheckoutRequestID") or
                response_data.get("checkout_request_id") or
                data.get("checkoutRequestID") or  # sometimes at root level
                response_data.get("transactionId")  # fallback to transactionId
            )
            
            transaction_id = (
                response_data.get("transactionId") or
                response_data.get("transaction_id") or
                ""
            )

            print(f"checkout_id resolved to: {checkout_id}")

            if not checkout_id:
                print(f"⚠️ Could not find checkoutRequestID in: {data}")
                return {
                    "success": False,
                    "message": f"Unexpected response structure: {data}"
                }

            return {
                "success": True,
                "checkout_request_id": checkout_id,
                "transaction_id": transaction_id,
                "message": data.get("message", "STK push sent"),
            }

        return {
            "success": False,
            "message": data.get("message", "STK push failed")
        }

    except requests.exceptions.Timeout:
        return {"success": False, "message": "Request timed out. Please try again."}
    except requests.exceptions.RequestException as e:
        return {"success": False, "message": f"Network error: {str(e)}"}
    except Exception as e:
        return {"success": False, "message": f"Unexpected error: {str(e)}"}