# Form/utils.py
from django.core import signing

FORM_LINK_SALT = "form-share-link"  # برای جدا کردن namespace امضا

def encode_form_token(user_id: int, form_id: int) -> str:
    """
    یک token امن بر اساس user_id و form_id تولید می‌کند.
    """
    data = {"u": user_id, "f": form_id}
    return signing.dumps(data, salt=FORM_LINK_SALT)

def decode_form_token(token: str) -> dict:
    """
    token را decode می‌کند و dict شامل u, f را برمی‌گرداند.
    اگر نامعتبر باشد، exception می‌اندازد.
    """
    return signing.loads(token, salt=FORM_LINK_SALT)
