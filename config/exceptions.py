from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status

def custom_exception_handler(exc, context):
    """
    Kengaytirilgan xato formati (BOSQICH A: XATO FORMATI):
    Har xato {"detail": "tushunarli matn", "code": "qisqa_kod", "errors": {maydon: [xabarlar]}} shaklida bo'ladi.
    """
    response = exception_handler(exc, context)

    if response is not None:
        custom_response_data = {
            "detail": "Nimadir xato ketdi.",
            "code": "error",
            "errors": None
        }

        if hasattr(exc, 'get_codes'):
            codes = exc.get_codes()
            if isinstance(codes, dict):
                custom_response_data["code"] = "validation_error"
            elif isinstance(codes, list) and codes:
                custom_response_data["code"] = codes[0]
            elif isinstance(codes, str):
                custom_response_data["code"] = codes

        if isinstance(response.data, dict):
            if "detail" in response.data:
                custom_response_data["detail"] = response.data["detail"]
                if "code" in response.data:
                    custom_response_data["code"] = response.data["code"]
            else:
                custom_response_data["detail"] = "Kiritilgan ma'lumotlarda xatolik bor."
                custom_response_data["errors"] = response.data
        elif isinstance(response.data, list):
            custom_response_data["detail"] = response.data[0] if response.data else "Xatolik"

        response.data = custom_response_data

    return response